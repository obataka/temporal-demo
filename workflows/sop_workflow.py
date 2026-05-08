"""
SOP Generation Workflow — Step-by-Step Approval with Dynamic Refinement

3フェーズを順番に実行し、各フェーズ完了後に人間の承認を待つ。
フィードバックがあれば同フェーズを再生成（Dynamic Refinement）する。

Phases:
    1. outline : 章立て提案
    2. draft   : 詳細執筆
    3. review  : 最終レビュー

Signals:
    approve_step(feedback: str)
        "" (空文字)  → 現フェーズを承認して次フェーズへ進む
        非空文字    → フィードバックとして同フェーズを再生成

Queries:
    get_status() -> dict    current_phase / status / attempt / current_output
    get_history() -> list   全フェーズ・全試行の比較ログ（人間介入の Evidence）
"""

from datetime import timedelta

from temporalio import workflow

from core.models import SOPRequest, LLMResult
from core.retry_policy import LLM_RETRY_POLICY

with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity

PHASES = ["outline", "draft", "review"]

PHASE_LABELS = {
    "outline": "フェーズ1: 章立て提案",
    "draft":   "フェーズ2: 詳細執筆",
    "review":  "フェーズ3: 最終レビュー",
}


@workflow.defn
class sop_generation_workflow:

    def __init__(self) -> None:
        # Signal state — Activity 実行中に届いても取りこぼさない
        self._signal_received: bool = False
        self._step_feedback: str = ""

        # Workflow state
        self._topic: str = ""
        self._current_phase: str = "initializing"
        self._current_output: str | None = None
        self._attempt_in_phase: int = 0
        self._status: str = "initializing"

        # フェーズごとの承認済み出力
        self._approved: dict[str, str] = {}

        # Evidence log: 全試行の比較ログ
        self._history: list[dict] = []

    # ─── Signal Handlers ─────────────────────────────────────────────────────

    @workflow.signal
    def approve_step(self, feedback: str) -> None:
        """
        "" (空文字): 現フェーズを承認して次フェーズへ進む。
        非空文字:   フィードバックとして同フェーズを再生成する。
        """
        self._step_feedback = feedback
        self._signal_received = True

    # ─── Query Handlers ──────────────────────────────────────────────────────

    @workflow.query
    def get_status(self) -> dict:
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "phase_label": PHASE_LABELS.get(self._current_phase, self._current_phase),
            "attempt_in_phase": self._attempt_in_phase,
            "current_output": self._current_output,
            "approved_phases": list(self._approved.keys()),
        }

    @workflow.query
    def get_history(self) -> list:
        """全フェーズ・全試行の比較ログ。人間介入の Evidence として使用する。"""
        return list(self._history)

    # ─── Main ────────────────────────────────────────────────────────────────

    @workflow.run
    async def run(self, topic: str, source_code: str) -> dict:
        self._topic = topic

        for phase in PHASES:
            self._current_phase = phase
            self._attempt_in_phase = 0
            last_feedback: str | None = None

            while True:
                self._status = "generating"

                # Activity 実行前にシグナル受信フラグをリセット
                # （Activity 実行中に届いたシグナルは wait_condition で即座に検出される）
                self._signal_received = False

                request = SOPRequest(
                    topic=topic,
                    source_code=source_code,
                    phase=phase,
                    attempt=self._attempt_in_phase,
                    previous_output=self._current_output if self._attempt_in_phase > 0 else None,
                    outline=self._approved.get("outline"),
                    draft=self._approved.get("draft"),
                    feedback=last_feedback,
                )
                result = await self._call_llm(request)
                self._current_output = result.text

                self._history.append({
                    "phase": phase,
                    "phase_label": PHASE_LABELS[phase],
                    "attempt": self._attempt_in_phase,
                    "feedback": last_feedback,
                    "output": result.text,
                    "tokens": result.total_tokens,
                    "latency_ms": result.latency_ms,
                    "approved": False,
                })

                self._status = "awaiting_approval"

                # シグナルを待つ（Activity 実行中に届いた場合は即座に返る）
                await workflow.wait_condition(lambda: self._signal_received)

                feedback = self._step_feedback
                self._step_feedback = ""
                self._signal_received = False

                if not feedback:
                    # 承認 → 次フェーズへ
                    self._history[-1]["approved"] = True
                    self._approved[phase] = self._current_output
                    break
                else:
                    # フィードバック → 同フェーズを再生成
                    last_feedback = feedback
                    self._attempt_in_phase += 1

        self._status = "completed"
        self._current_phase = "completed"

        return {
            "topic": topic,
            "outline": self._approved.get("outline", ""),
            "draft": self._approved.get("draft", ""),
            "review": self._approved.get("review", ""),
            "history": self._history,
        }

    async def _call_llm(self, request: SOPRequest) -> LLMResult:
        return await workflow.execute_activity(
            generate_sop_phase_activity,
            request,
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=LLM_RETRY_POLICY,
        )
