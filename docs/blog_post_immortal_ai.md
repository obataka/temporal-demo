# AIエージェントに「不滅の命」と「透明な家計簿」を授ける方法

**Temporal × Prometheus × Grafana で作る、壊れないLLMワークフロー**

---

## はじめに：2つの「見えない恐怖」

AI エージェントを本番環境で運用しようとしたとき、エンジニアは必ず2つの壁にぶつかる。

**恐怖① 「またエラーが出た」**

```
temporalio.exceptions.ApplicationError:
  503 UNAVAILABLE. This model is currently experiencing high demand.
```

深夜2時。Gemini API がタイムアウトした。ワークフローは中断した。
顧客向けのレポート生成パイプラインが止まっている。誰かが起きて手動再実行しなければならない。

**恐怖② 「今月いくら使った？」**

月末にクラウドの請求書が届く。LLM API 費用の内訳は「API calls: $847.23」という1行だけ。
どのジョブがいくら使ったのか、どのモデルが費用対効果が高いのか、まったくわからない。

この記事では、この2つの恐怖を同時に解決するアーキテクチャを実装した過程を紹介する。

---

## 解決策の全体像

```
run_workflow.py ──gRPC──▶ Temporal Server（不滅の記憶）
                                │
                         Pull 型タスク配送
                                │
                         Worker コンテナ
                    ┌─── Workflow（司令塔）
                    │         └── Activity（LLM 呼び出し）──▶ Gemini API
                    └─── Observability（家計簿係）
                              ├── structlog  → JSON ログ
                              └── prometheus_client
                                       │
                              :8000/metrics ──▶ Prometheus ──▶ Grafana
```

アーキテクチャの詳細な Mermaid 図解は [`architecture_diagram.md`](architecture_diagram.md) に収録している。
以下の4種類の図で全体像を把握できる：

- **System Component Diagram** — 全サービスの接続関係
- **Workflow Execution Sequence** — リトライ分岐を含む詳細フロー
- **Comparison Workflow Sequence** — Mock/Gemini 並列実行の流れ
- **Observability Data Flow** — メトリクスが Counter → Grafana に流れる経路

---

## 解決策①：Temporal による「不滅の命」

### LLM ワークフローが壊れる理由

LLM API 呼び出しは本質的に脆弱だ。

| 障害パターン | 発生頻度 | 通常の対処 |
|---|---|---|
| Rate limit (429) | 高 | sleep & retry を手書き |
| Timeout | 中 | try/except でログだけ |
| Network error | 低 | 諦めて手動再実行 |
| 503 高負荷 | 中 | 運次第 |

この「手書きリトライ」は必ず壊れる。冪等性の考慮漏れ、retry 中の状態消失、複数ワーカーでの重複実行……。

### Temporal が解決すること

Temporal はワークフローの「状態」を **イベント履歴（Event History）** としてデータベースに永続化する。

```python
# core/retry_policy.py
LLM_RETRY_POLICY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,    # 2秒 → 4秒 → 8秒
    maximum_interval=timedelta(seconds=30),
)
```

```python
# workflows/ai_agent_workflow.py
result = await workflow.execute_activity(
    call_llm_activity,
    prompt,
    start_to_close_timeout=timedelta(seconds=60),
    retry_policy=LLM_RETRY_POLICY,
)
```

これだけで Temporal は「このアクティビティは3回まで自動リトライ。失敗したら指数バックオフ」を保証する。
**アプリケーションコードにリトライロジックを書く必要がない。**

さらに、ワーカーがクラッシュしても Temporal は別のワーカーで処理を再開する。
ワークフロー自体は「不滅」だ。

### Workflow Sandbox という制約

Temporal の Workflow コードには厳格な制約がある。`os.environ` や `datetime.now()` を直接呼ぶと即座に怒られる：

```
RestrictedWorkflowAccessError: Cannot access os.environ.get
```

これは Temporal が Workflow の実行を「決定論的」に保つための安全装置だ。
同じ Event History を再生すれば必ず同じ結果になる必要があるため、
環境変数や現在時刻のような「実行ごとに変わる値」はワークフロー内で読んではいけない。

解決策は **Dataclass の分離**。

```python
# core/models.py — Sandbox-safe（structlog に非依存）
@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
```

Workflow は `LLMResult` だけを知っていればよい。ログや Prometheus は Activity 側に閉じ込める。

---

## 解決策②：Prometheus + Grafana による「透明な家計簿」

### なぜ LLM コストは見えにくいのか

LLM API は「推論のたびに課金」されるが、使用量はアプリケーション内部に閉じている。
外部の課金ダッシュボード（Google AI Studio 等）は月次集計しか見せてくれない。

**「今この瞬間、どのモデルが予算をどれだけ消費しているか」がリアルタイムでわからない。**

### Interceptor パターンによるメトリクス収集

すべての LLM 呼び出しを `log_llm_interaction` コンテキストマネージャでラップする。

```python
# core/observability.py

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total number of LLM tokens consumed",
    ["model", "type"],   # input / output 別に集計
)

llm_inference_latency_seconds = Histogram(
    "llm_inference_latency_seconds",
    "LLM inference latency in seconds",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

@contextmanager
def log_llm_interaction(model: str, prompt: str):
    start = time.monotonic()
    result_box = []
    try:
        yield result_box
        r = result_box[0]
        # Prometheus カウンターを更新
        llm_tokens_total.labels(model=r.model, type="input").inc(r.input_tokens)
        llm_tokens_total.labels(model=r.model, type="output").inc(r.output_tokens)
        llm_inference_latency_seconds.labels(model=r.model).observe(latency_ms / 1000)
        # JSON ログ出力
        logger.info("llm_interaction", status="success", ...)
    except Exception as exc:
        logger.error("llm_interaction", status="error", ...)
        raise
```

Activity から呼ぶ側はこれだけ：

```python
with log_llm_interaction(model, prompt) as result_box:
    response = client.models.generate_content(...)
    result_box.append(result)   # ← 1行追加するだけで計測完了
```

**LLM を Gemini から別プロバイダに変えても、観測ロジックを一切触らなくていい。**
これがインターセプターパターンの力だ。

### 単価 Gauge による PromQL コスト計算

課金単価はコードに直書きせず、Prometheus の **Gauge メトリクス** として管理する。

```python
# モデル別単価テーブル（USD / 1M tokens）
_MODEL_PRICES_USD_PER_MILLION = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10,  "output": 0.40},
    "mock-llm-v1":      {"input": 0.10,  "output": 0.10},
}

llm_price_per_million_tokens = Gauge(
    "llm_price_per_million_tokens",
    "Price per million tokens in USD",
    ["model", "type"],
)
```

PromQL 側では `group_left()` を使って「トークン数 × 単価」のリアルタイム join が可能になる：

```promql
# モデル別累積コスト（USD）
sum by(model) (
  llm_tokens_total * on(model, type) group_left() llm_price_per_million_tokens
) / 1000000
```

**単価改定時はコード1箇所を変えて Worker を再起動するだけ。PromQL は変更不要。**

### Grafana ダッシュボードの構成

`docker compose up` だけで以下のダッシュボードが自動プロビジョニングされる：

| パネル | 種別 | 用途 |
|---|---|---|
| Cumulative Token Consumption | Stat | 累積トークン消費量の一目把握 |
| Real-time Operational Expenditures (OpEx) | Stat | 変数で単価を上書き可能なコスト表示 |
| OpEx by Model — Cost Attribution | Pie Chart (Donut) | モデル別コスト比率（Google カラー） |
| Inference Latency — 5-Minute Rolling Average | Time Series | レイテンシ異常の検出 |
| Cumulative OpEx Over Time | Time Series | コストの増加傾向の把握 |
| Token Throughput | Time Series | クォータ残量の予測 |

ダッシュボード上部の **Variables**（テキストボックス）で単価をブラウザ上で即時変更でき、
「もし gemini-2.0-flash に切り替えたら費用はどう変わるか」をシミュレートできる。

---

## 比較デモ：Mock vs Gemini を並列実行

`comparison_workflow` は Mock と Gemini を同一ワークフロー内で**並列実行**し、
コスト・レイテンシ・トークン数をリアルタイムに比較する。

```bash
python run_comparison.py "信頼性の高いシステム設計について"
```

```
┌──────────────────────┬──────────────┬──────────────┐
│ Metric               │     Mock     │ Gemini Flash │
├──────────────────────┼──────────────┼──────────────┤
│ Input tokens         │     233      │      7       │
│ Output tokens        │     158      │    1,845     │
│ Latency (ms)         │    517.0     │   29057.7    │
│ Cost (USD)           │ $0.00003910  │ $0.00055402  │
└──────────────────────┴──────────────┴──────────────┘
```

この実行後、Grafana の Pie Chart には `gemini-2.5-flash: 86.3% / mock-llm-v1: 13.7%` が即座に反映される。

---

## まとめ：信頼性と説明責任のパッケージ

| 課題 | 解決策 | 効果 |
|---|---|---|
| LLM API 障害で処理が止まる | Temporal RetryPolicy | 自動リトライ、夜間対応ゼロ |
| コストが見えない | Prometheus Counter + Gauge join | モデル別コストのリアルタイム把握 |
| プロバイダ変更が怖い | Interceptor パターン | ロジック変更なしで切り替え可能 |
| Workflow コードが壊れる | Dataclass 分離 (core/models.py) | Sandbox エラーを構造的に排除 |
| インフラ設定が手動 | Init Container + Grafana Provisioning | `docker compose up` 一発で完結 |

AIエージェントを「動けばいい」から「壊れない・説明できる」に昇華させることが、
これからのエンタープライズ AI 開発で求められる水準だと考えている。

---

## 参考リンク・ファイル構成

```
temporal-demo/
├── README.md                          ← クイックスタート + Business Value
├── ARCHITECTURE.md                    ← 設計思想・パターン解説（日本語）
├── docker-compose.yaml                ← 全スタック定義
├── core/
│   ├── models.py                      ← Sandbox-safe dataclass
│   ├── observability.py               ← Prometheus + structlog
│   └── retry_policy.py                ← リトライ設定の一元管理
├── workflows/
│   ├── ai_agent_workflow.py           ← メインワークフロー
│   └── comparison_workflow.py         ← Mock vs Gemini 比較デモ
├── activities/
│   ├── llm_activity.py                ← Gemini 呼び出し
│   └── mock_activity.py               ← テスト用モック
├── monitoring/grafana/dashboards/
│   └── llm-metrics.json               ← ダッシュボード定義（Git管理）
└── docs/
    ├── costs.md                       ← 単価テーブルと管理手順
    └── architecture_diagram.md        ← Mermaid 図解 × 4
```

**使用技術:** Python 3.13 / Temporal Python SDK / Google Gemini API (gemini-2.5-flash) / Prometheus / Grafana / Docker Compose / structlog / prometheus_client
