# Temporal × CrewAI: Durable Multi-Agent Workflows with Strict Human Governance

*A reference implementation for running multi-agent LLM systems under hard human-approval gates — built on Temporal for durable state and explicit retry policy.*

---

## Why This Exists

「AIエージェント」demoの多くは、プロセス内メモリで状態を保持し、人間承認を任意のUI装飾として扱い、深夜のLLM APIタイムアウトに対する answer を持たない。実運用では、承認待ちは数日単位で継続し、LLM呼び出しはレート制限や一時障害で日常的に失敗し、Human-in-the-Loopはポーリングで代替できるものではない。本リポジトリは、**プロセス死・デプロイ・クラッシュを跨いで状態を保持し、明示的なリトライポリシーで失敗を処理し、人間の判断を無期限にブロックできる**アーキテクチャの参照実装である。

---

## Design Patterns Demonstrated

以下4パターンは `workflows/sop_workflow.py` / `activities/fix_sop_activity.py` に実装済み。詳細な設計判断は [技術記事](technical-article-temporal-crewai-hitl.md) を参照。

### 1. Determinism & Replay
Temporal WorkflowはWorker再起動時にEvent Historyから*リプレイ*される。決定論を壊す依存（CrewAI）はWorkflowモジュール直下でimportしない。

```python
# workflows/sop_workflow.py:35-43 (一部省略)
with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
    ...
    from activities.fix_sop_activity import (
        fix_sop_with_crew_activity,
        writer_task_activity,
        reviewer_task_activity,
    )
    ...
```

### 2. Push-based Human-in-the-Loop
ポーリングではなく`Signal` + `wait_condition`によるブロッキング待機。Activity実行中に届いたSignalも取りこぼさない。

```python
# workflows/sop_workflow.py:209
await workflow.wait_condition(lambda: self._signal_received)
```

### 3. Activity-grained Multi-Agent Execution
CrewAIのWriter/Reviewerを単一`Crew.kickoff()`に束ねず、別Activityに分解。Reviewerが失敗してもWriterの出力は再実行・再課金されない。

```python
# activities/fix_sop_activity.py:253 / :348
async def writer_task_activity(...) -> LLMResult: ...
async def reviewer_task_activity(...) -> LLMResult: ...
```

### 4. Zero-Downtime Versioning
稼働中のワークフローを壊さずにコードパスを切り替える`workflow.patched()`。実際にWriter/Reviewer分割リファクタ（コミット `f79ddfc`）で使用した。

```python
# workflows/sop_workflow.py:382-389
if workflow.patched("split-writer-reviewer"):
    return await self._call_fix_decomposed(sop_text, failures, human_feedback)
return await workflow.execute_activity(
    fix_sop_with_crew_activity,
    args=[sop_text, failures, human_feedback, self._fix_attempt],
    start_to_close_timeout=timedelta(minutes=7),
    retry_policy=LLM_RETRY_POLICY,
)
```

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
| Grafana Dashboard | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| Worker Metrics | http://localhost:8000/metrics |

---

## Reference Implementation: SOP Auto-Improvement Pipeline

`workflows/sop_workflow.py` (`sop_generation_workflow`) が実装するドメインは付随的で、パターンそのものが本体である。LLMが3フェーズでSOPドラフトを生成し、各フェーズで人間が承認/差し戻しを行い、CrewAI（Writer/Reviewer）が自律的にバリデーション失敗を修正し、最終的にGitHub PRの作成にも人間承認ゲートがかかる。

```
Phase 1-3: outline → draft → review   （各フェーズごとに承認 Signal 待ち）
Phase 4:   autonomous_fix              （バリデーション → CrewAI修正、最大3回）
Phase 5:   github_pr                   （require_approval=True 時、承認 Signal 待ち）
```

4つの人間判断ゲートはすべて `@workflow.signal` によるハードゲートであり、advisory（任意）ではない。

## Immortal AI Agent Demo Architecture

上記SOPパイプラインとは別の、よりシンプルなdemo（`ai_agent_workflow`）も同梱している。Gemini呼び出しの障害耐性とコスト可視化の最小構成を確認したい場合はこちら。

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

---

## Deep Dive

- **設計思想の詳細解説**: [technical-article-temporal-crewai-hitl.md](technical-article-temporal-crewai-hitl.md)
- **アーキテクチャ設計書**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **コスト設計・単価管理**: [docs/costs.md](docs/costs.md)

## Live Demo

- **Reference Architecture & Demo Video**: https://project-sy5bk-qyr66bsfr-obataka123.vercel.app/lp.html
