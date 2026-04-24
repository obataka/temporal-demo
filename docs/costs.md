# LLM Cost Assumptions

このドキュメントは、Grafana ダッシュボードのコスト推計に使用している単価の根拠と管理方法を記述する。

---

## 単価テーブル（USD / 1M tokens）

| モデル | Input | Output | 出典 |
|---|---|---|---|
| `gemini-2.5-flash` | $0.075 | $0.300 | [Google AI Pricing](https://ai.google.dev/pricing) |
| `gemini-2.0-flash` | $0.100 | $0.400 | [Google AI Pricing](https://ai.google.dev/pricing) |
| `mock-llm-v1`      | $0.100 | $0.100 | デモ用仮単価（実際の課金なし）|

---

## 単価の管理場所

単価は **2か所** で管理されている。用途に応じて使い分ける。

### 1. `core/observability.py` — Prometheus Gauge

```python
_MODEL_PRICES_USD_PER_MILLION: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10,  "output": 0.40},
    "mock-llm-v1":      {"input": 0.10,  "output": 0.10},
}
```

Worker 起動時に `llm_price_per_million_tokens{model, type}` Gauge に書き込まれ、
PromQL の `group_left()` join でトークン数と掛け合わせることでコストを算出する。

**用途:** モデルを動的に追加しても PromQL を変更不要。時系列パネル・Pie Chart はこちらを使用。

```promql
# 例: モデル別累積コスト
sum by(model) (
  llm_tokens_total * on(model, type) group_left() llm_price_per_million_tokens
) / 1000000
```

### 2. Grafana Dashboard Variables — テキストボックス

ダッシュボード上部に4つの変数が定義されており、ブラウザ上で即座に単価を上書きできる。

| 変数名 | デフォルト値 | 対応モデル |
|---|---|---|
| `price_gemini_flash_in`  | 0.075 | gemini-2.5-flash / input  |
| `price_gemini_flash_out` | 0.300 | gemini-2.5-flash / output |
| `price_mock_in`          | 0.100 | mock-llm-v1 / input       |
| `price_mock_out`         | 0.100 | mock-llm-v1 / output      |

**用途:** "Estimated Cost (USD)" Stat パネルがこの変数を使用。  
価格改訂時や「もし単価が〇〇なら？」というシミュレーション用に使う。

```promql
# 例: Stat パネルのクエリ（変数使用）
(
  sum(llm_tokens_total{model="gemini-2.5-flash", type="input"})  * ${price_gemini_flash_in} +
  sum(llm_tokens_total{model="gemini-2.5-flash", type="output"}) * ${price_gemini_flash_out} +
  sum(llm_tokens_total{model="mock-llm-v1",       type="input"})  * ${price_mock_in} +
  sum(llm_tokens_total{model="mock-llm-v1",       type="output"}) * ${price_mock_out}
) / 1000000
```

---

## 価格改定時の手順

1. **`core/observability.py`** の `_MODEL_PRICES_USD_PER_MILLION` を更新する
2. **Worker を再起動**（`docker compose restart worker`）して Gauge 値を更新する
3. **Grafana Variables のデフォルト値** を `llm-metrics.json` の `templating.list[].query` で合わせて更新する
4. `docs/costs.md`（このファイル）の単価テーブルを更新する

> **Note:** Worker 再起動前後で Gauge 値が変わるため、過去の時系列コストグラフは再起動前の単価で計算されたまま保持される。Prometheus はスクレイプ済みのデータを書き換えない。

---

## Free Tier について（`mock-llm-v1`）

`mock-llm-v1` は実際の API を呼び出さないモック実装で、課金は発生しない。  
デモ・CI 環境での動作確認用。`run_workflow.py --mock` で起動する。

```
python run_workflow.py "テストプロンプト" --mock
```
