"""
Agentic SOP Review Workflow — CrewAI 多役割エージェントによる SOP 最終レビュー

SOP 草稿を「校正担当」と「技術担当」の 2 エージェントに分担させてレビューし、
最後に Gemini で統合する。エージェント実行中の思考ログを Query で公開し、
Signal でヒントを注入できる。

Agents (CrewAI):
    proofreader  : 校正担当 — 文法・表記・論理的一貫性を検証
    tech_reviewer: 技術担当 — コード例・API 使用法・手順の完全性を検証

Signals:
    inject_hint(hint: str)
        次フェーズ開始時に Agent の Task Description へ注入される。
        校正担当の実行中に送った場合 → 技術担当に渡される。

Queries:
    get_agent_status() -> dict
        current_phase / status / agent_log (Inner Monologue) / pending_hints
"""

from datetime import timedelta

from temporalio import workflow

from core.models import AgentReviewRequest, AgentResult, LLMResult
from core.retry_policy import LLM_RETRY_POLICY

with workflow.unsafe.imports_passed_through():
    from activities.crew_activity import run_agent_activity, merge_reviews_activity

PHASE_LABELS = {
    "proofreader":  "Phase 1: 校正担当エージェント",
    "tech_reviewer": "Phase 2: 技術担当エージェント",
    "merging":      "Phase 3: レビュー統合（Gemini）",
    "completed":    "完了",
}


@workflow.defn
class agentic_review_workflow:

    def __init__(self) -> None:
        # Signal キュー: Agent 実行中に届いたヒントも取りこぼさない
        self._pending_hints: list[str] = []

        # Inner Monologue ログ: 各 Agent の出力を蓄積
        self._agent_log: list[dict] = []

        # Workflow state
        self._current_phase: str = "initializing"
        self._status: str = "initializing"
        self._draft: str = ""

    # ─── Signal Handlers ─────────────────────────────────────────────────────

    @workflow.signal
    def inject_hint(self, hint: str) -> None:
        """
        ヒントを注入する。次フェーズ開始時に Agent の Task Description へ組み込まれる。
        校正担当の実行中に送れば、技術担当フェーズへのヒントになる。
        """
        self._pending_hints.append(hint)

    # ─── Query Handlers ──────────────────────────────────────────────────────

    @workflow.query
    def get_agent_status(self) -> dict:
        """
        現在のエージェント状態と Inner Monologue を返す。
        agent_log の各エントリに thoughts（Agent の中間出力）が含まれる。
        """
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "phase_label": PHASE_LABELS.get(self._current_phase, self._current_phase),
            "pending_hints": list(self._pending_hints),
            "pending_hints_count": len(self._pending_hints),
            "agent_log": [
                {
                    "agent": e["agent"],
                    "tokens": e["tokens"],
                    "latency_ms": e["latency_ms"],
                    "thoughts_count": len(e["thoughts"]),
                    # 最新の思考スニペット（最大 300 文字）
                    "latest_thought": e["thoughts"][-1][:300] if e["thoughts"] else "",
                    "output_snippet": e["output"][:300],
                }
                for e in self._agent_log
            ],
        }

    @workflow.query
    def get_full_log(self) -> list:
        """完全な Agent ログ（output 全文 + 全 thoughts）を返す。"""
        return list(self._agent_log)

    # ─── Main ────────────────────────────────────────────────────────────────

    @workflow.run
    async def run(self, draft: str) -> dict:
        self._draft = draft

        # ── Phase 1: 校正担当エージェント ─────────────────────────────────────
        self._current_phase = "proofreader"
        self._status = "running"

        # 開始時点のヒントを Phase 1 に渡し、その分だけクリアする。
        # Activity 実行中に届いたヒントは _pending_hints に残り、Phase 2 で使われる。
        hints_for_phase1 = list(self._pending_hints)
        self._pending_hints = self._pending_hints[len(hints_for_phase1):]

        proofreader_result: AgentResult = await self._run_agent(AgentReviewRequest(
            draft=draft,
            agent_role="proofreader",
            hints=hints_for_phase1,
        ))
        # Activity 実行中に届いたヒントが _pending_hints に溜まっている

        self._agent_log.append({
            "agent": "proofreader",
            "agent_label": "校正担当",
            "output": proofreader_result.output,
            "thoughts": proofreader_result.thoughts,
            "tokens": proofreader_result.tokens,
            "latency_ms": proofreader_result.latency_ms,
        })

        # ── Phase 2: 技術担当エージェント ─────────────────────────────────────
        # Phase 1 実行中に inject_hint で届いたヒントがここに入っている
        self._current_phase = "tech_reviewer"

        hints_for_phase2 = list(self._pending_hints)
        self._pending_hints = self._pending_hints[len(hints_for_phase2):]

        tech_result: AgentResult = await self._run_agent(AgentReviewRequest(
            draft=draft,
            agent_role="tech_reviewer",
            hints=hints_for_phase2,
            proofreader_output=proofreader_result.output,
        ))

        self._agent_log.append({
            "agent": "tech_reviewer",
            "agent_label": "技術担当",
            "hints_received": hints_for_phase2,   # ← inject_hint で注入されたヒント
            "output": tech_result.output,
            "thoughts": tech_result.thoughts,
            "tokens": tech_result.tokens,
            "latency_ms": tech_result.latency_ms,
        })

        # ── Phase 3: レビュー統合 ──────────────────────────────────────────────
        self._current_phase = "merging"

        merge_result: LLMResult = await workflow.execute_activity(
            merge_reviews_activity,
            args=[proofreader_result.output, tech_result.output, draft],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=LLM_RETRY_POLICY,
        )

        self._status = "completed"
        self._current_phase = "completed"

        total_tokens = (
            proofreader_result.tokens
            + tech_result.tokens
            + merge_result.total_tokens
        )

        return {
            "final_review": merge_result.text,
            "agent_log": self._agent_log,
            "total_tokens": total_tokens,
            "total_latency_ms": round(
                proofreader_result.latency_ms
                + tech_result.latency_ms
                + merge_result.latency_ms
            ),
        }

    async def _run_agent(self, request: AgentReviewRequest) -> AgentResult:
        return await workflow.execute_activity(
            run_agent_activity,
            request,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=LLM_RETRY_POLICY,
        )
