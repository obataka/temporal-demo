# The Immortal AI Agent

Temporal ワークフローエンジンと LLM (Google Gemini) を組み合わせた、
**障害に強く・コスト可視化済みの AI エージェント**プロトタイプ。

```
docker compose up --build
```

これだけで全スタックが起動する。

---

## Quick Start

```bash
# 環境変数を設定
echo "GEMINI_API_KEY=your_key_here" > .env

# 全スタック起動（Temporal + Worker + Prometheus + Grafana）
docker compose up --build -d

# Gemini ワークフローを実行
python run_workflow.py "AIエージェントの設計原則を3つ教えてください"

# モックモード（API キー不要）
python run_workflow.py --mock "任意のプロンプト"

# Mock vs Gemini 比較デモ
python run_comparison.py "信頼性の高いシステム設計について教えてください"
```

## Endpoints

| Service | URL |
|---|---|
| Temporal UI | http://localhost:8080 |
| Grafana Dashboard | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Worker Metrics | http://localhost:8000/metrics |

---

## Architecture

```
run_workflow.py ──gRPC──▶ Temporal Server
                               │
                        Task dispatch (Pull)
                               │
                               ▼
                         Worker Container
                    ┌─── ai_agent_workflow
                    │         └── call_llm_activity ──▶ Gemini API
                    │         └── call_mock_llm_activity
                    └─── observability.py
                              ├── structlog (JSON logs)
                              └── prometheus_client
                                       │
                              :8000/metrics ──▶ Prometheus ──▶ Grafana
```

詳細な構成図（Mermaid）: [`docs/architecture_diagram.md`](docs/architecture_diagram.md)

---

## Business Value

**なぜこの構成が企業のコスト削減・信頼性向上に寄与するか:**

- **LLM 障害を無害化するゼロオペレーション・リカバリ**
  Temporal の Event History により、LLM API の一時障害（レート制限・タイムアウト・ネットワーク断）が発生しても、ワークフローは自動でリトライし最終的に完了する。インフラエンジニアの夜間対応や手動再実行が不要になり、運用コストを大幅に削減する。

- **リアルタイムの LLM コスト可視化によるベンダーロックイン回避**
  Prometheus + Grafana によるモデル別コスト追跡（`OpEx by Model` パネル）により、どのモデルが予算をどれだけ消費しているかを秒単位で把握できる。モデル切り替えのコスト影響をダッシュボード上でシミュレートでき、ベンダー交渉や LLM プロバイダ乗り換えの意思決定を定量的に行える。

- **再現性のある観測可能なシステムで監査・コンプライアンスに対応**
  全 LLM 呼び出しが structlog で JSON ログ化され、Temporal UI でワークフロー単位のトークン消費量（`Total_Tokens` Search Attribute）が永続記録される。「いつ・どのモデルで・何トークン使ったか」の完全な監査ログが `docker compose logs` と Temporal UI の2系統で確保され、コスト配賦・セキュリティ監査・SLA 証明に対応できる。

---

## Key Design Decisions

| Pattern | Implementation | Reason |
|---|---|---|
| Interceptor | `log_llm_interaction` context manager | LLM ロジックと観測を分離 |
| Sandbox Isolation | `core/models.py` を structlog 非依存に | Temporal Workflow の決定論的実行を保証 |
| Strategy | `use_mock` フラグで Gemini ↔ Mock 切り替え | CI/デモ環境でも同一コードを動作 |
| Init Container | `temporalio/admin-tools` で Search Attribute 自動登録 | `docker compose up` だけで完結 |
| Gauge for pricing | `llm_price_per_million_tokens` Gauge + PromQL join | 単価改定時に PromQL を変更不要 |

詳細: [`ARCHITECTURE.md`](ARCHITECTURE.md) / コスト設計: [`docs/costs.md`](docs/costs.md)
