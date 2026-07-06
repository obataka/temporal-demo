# Temporal AI Agent — アーキテクチャ設計書

## 1. 実装した主要な機能とクラス構成

### システム全体図

```
run_workflow.py (CLI)
     │
     │ gRPC :7233
     ▼
┌─────────────────────────────────────────┐
│         Temporal Server (Docker)         │
│  状態永続化 / タスクキュー / リトライ制御  │
└───────────────────┬─────────────────────┘
                    │ タスク配送
                    ▼
┌─────────────────────────────────────────┐
│         Worker (Docker コンテナ)          │
│                                          │
│  workflows/ai_agent_workflow.py          │
│    └─ activities/llm_activity.py         │
│    └─ activities/mock_activity.py        │
│         └─ core/observability.py         │
│              ├─ structlog (JSON ログ)    │
│              └─ prometheus_client        │
│                   └─ :8000/metrics ──────┼──▶ Prometheus ──▶ Grafana
└─────────────────────────────────────────┘       :9090          :3001
```

### ファイル・クラス構成

| ファイル | 主要クラス / 関数 | 責務 |
|---|---|---|
| `core/models.py` | `LLMResult` (dataclass) | LLM 呼び出し結果の型定義。Temporal Sandbox-safe |
| `core/observability.py` | `log_llm_interaction` (context manager) | LLM 呼び出しを計測・JSON ログ出力 |
| `core/retry_policy.py` | `LLM_RETRY_POLICY` | リトライ設定の一元管理 |
| `activities/llm_activity.py` | `call_llm_activity` | Gemini 2.5 Flash 呼び出し |
| `activities/mock_activity.py` | `call_mock_llm_activity` | API キー不要のモック推論 |
| `workflows/ai_agent_workflow.py` | `ai_agent_workflow` | Workflow 定義・Search Attributes 更新 |
| `worker.py` | — | Worker 起動・メトリクス HTTP サーバー起動（:8000） |
| `run_workflow.py` | — | ワークフロー発火 CLI（`--mock` オプション対応） |
| `core/observability.py` | `llm_tokens_total`, `llm_inference_latency_seconds` | Prometheus メトリクス定義・更新 |
| `prometheus.yml` | — | Prometheus スクレイプ設定 |
| `monitoring/grafana/provisioning/` | — | Grafana 自動プロビジョニング設定 |
| `monitoring/grafana/dashboards/llm-metrics.json` | — | ダッシュボード定義（Git 管理） |

### Activity の返り値 `LLMResult`

```python
@dataclass
class LLMResult:
    text: str           # LLM の応答テキスト
    model: str          # 使用モデル名
    input_tokens: int   # 入力トークン数
    output_tokens: int  # 出力トークン数
    total_tokens: int   # 合計トークン数
    latency_ms: float   # 呼び出し所要時間（ミリ秒）
```

---

## 2. 採用したデザインパターンとその理由

### Sidecar Pattern — Observability の分離

LLM 呼び出しのコアロジックと「ログを取る」という横断的関心事を、
コンテキストマネージャ `log_llm_interaction` で分離した。

```python
# Activity 本体はビジネスロジックだけに集中できる
with log_llm_interaction(model, prompt) as result_box:
    response = client.models.generate_content(...)
    result_box.append(result)  # ← ここだけ追加すれば計測完了
```

**理由:** LLM を Gemini から別プロバイダに変えても、ログ機構を触らずに済む。

---

### Sandbox Isolation — Workflow と Activity の完全分離

Temporal の Workflow Sandbox はデシジョン（実行順序）を決定論的に保つため、
`os.environ` や外部ライブラリへのアクセスを制限する。

```
Workflow  ← core/models.py のみ参照（structlog に非依存）
Activity  ← core/observability.py を参照（structlog 使用可）
```

`core/models.py` を structlog から独立させることで、
Sandbox エラーを発生させずにデータ型を共有した。

**理由:** Temporal の設計原則（Workflow は純粋な状態機械）に従い、
副作用は全て Activity 側に閉じ込める。

---

### Strategy Pattern — 実行モードの切り替え

`use_mock` フラグ一つで Gemini / Mock を切り替えられる。

```python
activity_fn = call_mock_llm_activity if use_mock else call_llm_activity
```

**理由:** CI 環境や API キーが不要なデモ用途で、同一の Workflow コードを
変更なしに動作させるため。

---

### Retry Policy の一元管理

```python
# core/retry_policy.py
LLM_RETRY_POLICY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
)
```

**理由:** 複数の Activity が同じポリシーを使う場合に、変更箇所を一か所に限定するため。

---

## 3. ガバナンス / Observability で特に配慮した点

### 構造化ログによる分析可能性

`structlog` で全 LLM 呼び出しを JSON 化し、`docker-compose logs` で視認可能にした。
ELK Stack / Datadog / BigQuery などの分析基盤へそのまま流し込める設計。

```json
{
  "status": "success",
  "model": "gemini-2.5-flash",
  "prompt_summary": "Temporal というワークフローエンジンの…",
  "input_tokens": 243,
  "output_tokens": 258,
  "total_tokens": 501,
  "latency_ms": 1103.09,
  "timestamp": "2026-04-17T05:39:35Z"
}
```

### Temporal Search Attributes によるコスト追跡

ワークフロー単位でトークン消費量を記録し、Temporal UI 上でフィルタリング可能。

| Search Attribute | 型 | 用途 |
|---|---|---|
| `LLM_Model` | Keyword | モデル別の実行コスト比較 |
| `Total_Tokens` | Int | トークン消費量の一覧・合計 |
| `LLM_Status` | Keyword | Running / Success / Failed の状態追跡 |

### 失敗の可視化

`LLM_Status` は `Running` → `Success` / `Failed` と推移し、
リトライ中のワークフローが UI 上で `Running` のまま留まる。
「いつ、どのワークフローが何回リトライしたか」が履歴として不滅に残る。

### デバッグモードによる耐障害性の検証

`DEBUG_FAIL=1` で Activity を意図的に失敗させ、
Temporal のリトライ動作を本番コードの変更なしに検証できる。

### Prometheus メトリクスによるリアルタイム監視

`core/observability.py` に2種類のメトリクスを定義し、LLM 推論成功時に自動更新する。

```python
# Counter — トークン消費の累積カウント（model / type ラベル付き）
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total number of LLM tokens consumed",
    ["model", "type"],  # type: input | output
)

# Histogram — 推論レイテンシの分布（バケット単位で集計）
llm_inference_latency_seconds = Histogram(
    "llm_inference_latency_seconds",
    "LLM inference latency in seconds",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
```

Worker の `:8000/metrics` エンドポイントを Prometheus が 15秒ごとにスクレイプし、
Grafana でリアルタイム可視化する。

### Grafana ダッシュボードの自動プロビジョニング

`docker compose up` だけで以下が再現される。手動設定不要。

```
monitoring/grafana/
├── provisioning/
│   ├── datasources/prometheus.yml   ← データソース自動登録
│   └── dashboards/default.yml       ← ダッシュボード読み込み先を指定
└── dashboards/
    └── llm-metrics.json             ← パネル定義（Git 管理可能）
```

| パネル名 | 種別 | PromQL |
|---|---|---|
| Total Tokens Consumed | Stat | `sum(llm_tokens_total)` |
| Average Latency (5m) | Time series | `rate(...sum[5m]) / rate(...count[5m])` |
| Token Rate (per minute) | Time series | `rate(llm_tokens_total[5m]) * 60` |

---

## 4. 課題と設計判断（Gemini レビュー済み）

### 課題①: Search Attributes の自動登録 ✅ 解決策確定

**現状の問題:** Worker 起動時の SDK 経由登録が失敗（`Namespace is not set on req`）。
現在は `docker exec` による手動登録で対応中。

**Gemini の回答 — 推奨: Init Container パターン**

SDK からの動的登録は権限・名前空間の制約で難易度が高い。
`temporalio/admin-tools` イメージを使った冪等な Init Service が最も堅牢。

```yaml
# docker-compose.yaml に追加予定
temporal-init:
  image: temporalio/admin-tools
  depends_on:
    - temporal
  command: >
    sh -c "
      until temporal operator search-attribute list --address temporal:7233 > /dev/null 2>&1; do
        sleep 2;
      done &&
      temporal operator search-attribute create
        --address temporal:7233
        --name LLM_Model --type Keyword
        --name Total_Tokens --type Int
        --name LLM_Status --type Keyword
    "
```

**利点:** アプリケーションコード（Worker）に管理権限を持たせずインフラとして完結する。

---

### 課題②: コスト集計の外部基盤連携 ✅ 実装済み

**解決策:** `prometheus_client` を Activity 内に直接組み込み、Grafana で可視化。

```
Worker (:8000/metrics)
    │
    ▼ Prometheus スクレイプ（15秒間隔）
    ├──▶ llm_tokens_total{model, type}         ← 累積トークン数
    ├──▶ llm_inference_latency_seconds         ← レイテンシ分布
    └──▶ Grafana ダッシュボード                 ← リアルタイム可視化
```

**将来の拡張（長期コスト集計が必要になったとき）:**
```
Worker stdout (JSON) → Fluent Bit / Vector → BigQuery / Snowflake
```

> 「顧客専用のコストダッシュボード」を Grafana でサクッと見せるだけで、
> プロジェクトの信頼感は爆上がりする。 — Gemini

---

### 課題③: Workflow / Activity 間のデータ型共有 ✅ 移行路線確定

**現状:** `dataclass` を `core/models.py` に分離して Sandbox 問題を解決。

**Gemini の回答 — フェーズ別推奨**

| フェーズ | 推奨型 | 理由 |
|---|---|---|
| 現状（小規模）| `dataclass` ✅ | 最適。現行のまま維持 |
| 次フェーズ | **Pydantic** | Temporal SDK v1.4.0+ がネイティブ対応。型安全・バリデーション付き |
| 多言語展開時 | **Protobuf** | Go / TypeScript Worker との混在（ポリグロット）には唯一無二の正解 |

**次のアクション:** `core/models.py` の `LLMResult` を Pydantic `BaseModel` に置き換える。

---

### 課題④: Worker の水平スケーリング ✅ 方針確定

**現状:** Worker コンテナ1台。LLM 呼び出しの高レイテンシが並列リクエスト時のボトルネック。

**Gemini の回答 — `--scale` は有効。ただし2点注意**

Temporal は Pull 方式でタスクを配分するため、Worker を増やしても競合・重複実行は起きない。

**注意点1 — Worker キャパシティ設定:**
```python
# worker.py で非同期 IO を活かした同時実行数を設定
Worker(
    client,
    task_queue=TASK_QUEUE,
    max_concurrent_activity_task_pollers=10,  # LLM待機中にスレッドが枯渇しないよう調整
    ...
)
```

**注意点2 — Graceful Shutdown:**
`--scale` でコンテナを削減する際、実行中 Activity が中断されると Temporal はタイムアウトと判断し別 Worker でリトライする。これは安全だが **LLM API 費用が二重にかかる**リスクがある。
`SIGTERM` 受信後、実行中 Activity の完了を待ってから停止する設定が望ましい。
