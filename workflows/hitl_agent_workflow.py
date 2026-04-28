"""
Human-in-the-Loop Agent Workflow

人間が Signal でフィードバックを与えるたびに LLM が再生成を行い、
「承認」Signal が来るまでループし続けるワークフロー。

Signals:
    provide_feedback(feedback: str)  -- 修正指示。即座に再生成が始まる。
    approve()                        -- 現在の回答を承認して終了。

Queries:
    get_status() -> dict             -- retry_count / last_feedback / current_answer
    get_history() -> list            -- 全試行の比較ログ
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ActivityError

from core.models import LLMRequest, LLMResult
from core.retry_policy import LLM_RETRY_POLICY

with workflow.unsafe.imports_passed_through():
    from activities.llm_activity import call_llm_with_context_activity


@workflow.defn
class hitl_agent_workflow:

    def __init__(self) -> None:
        # Signal キュー: Activity 実行中に届いた feedback も取りこぼさない
        self._pending_feedbacks: list[str] = []
        self._approve_requested: bool = False

        # 状態
        self._task: str = ""
        self._current_answer: str | None = None
        self._retry_count: int = 0
        self._last_feedback: str = ""
        self._status: str = "initializing"

        # 履歴: [{attempt, feedback, answer, tokens, latency_ms}]
        self._history: list[dict] = []

    # ─── Signal Handlers ─────────────────────────────────────────────────────

    @workflow.signal
    def provide_feedback(self, feedback: str) -> None:
        """修正指示を送る。実行中でも即受理され、次のループで反映される。"""
        self._pending_feedbacks.append(feedback)

    @workflow.signal
    def approve(self) -> None:
        """現在の回答を承認してワークフローを終了させる。"""
        self._approve_requested = True

    # ─── Query Handlers ──────────────────────────────────────────────────────

    @workflow.query
    def get_status(self) -> dict:
        return {
            "status": self._status,
            "retry_count": self._retry_count,
            "last_feedback": self._last_feedback,
            "current_answer": self._current_answer,
            "approved": self._approve_requested,
            "pending_feedbacks": len(self._pending_feedbacks),
        }

    @workflow.query
    def get_history(self) -> list:
        """全試行の履歴。初期回答 vs フィードバック反映後の比較ログに使う。"""
        return list(self._history)

    # ─── Main ────────────────────────────────────────────────────────────────

    @workflow.run
    async def run(self, task: str) -> dict:
        self._task = task

        # ── 初回生成 ──────────────────────────────────────────────────────────
        self._status = "generating"
        result = await self._call_llm(LLMRequest(user_message=task, attempt=0))
        self._current_answer = result.text
        self._history.append({
            "attempt": 0,
            "feedback": None,
            "answer": result.text,
            "tokens": result.total_tokens,
            "latency_ms": result.latency_ms,
        })
        self._status = "awaiting_feedback"

        # ── Human-in-the-Loop フィードバックループ ────────────────────────────
        while not self._approve_requested:
            # キューが空で承認も来ていなければ待機
            await workflow.wait_condition(
                lambda: bool(self._pending_feedbacks) or self._approve_requested
            )

            if self._approve_requested:
                break

            # フィードバックを1件取り出して処理
            feedback = self._pending_feedbacks.pop(0)
            self._last_feedback = feedback
            self._retry_count += 1
            self._status = "regenerating"

            request = LLMRequest(
                user_message=task,
                attempt=self._retry_count,
                previous_answer=self._current_answer,
                feedback=feedback,
            )
            result = await self._call_llm(request)
            self._current_answer = result.text
            self._history.append({
                "attempt": self._retry_count,
                "feedback": feedback,
                "answer": result.text,
                "tokens": result.total_tokens,
                "latency_ms": result.latency_ms,
            })
            self._status = "awaiting_feedback"

        self._status = "approved"
        return {
            "final_answer": self._current_answer,
            "total_attempts": self._retry_count + 1,
            "history": self._history,
        }

    async def _call_llm(self, request: LLMRequest) -> LLMResult:
        return await workflow.execute_activity(
            call_llm_with_context_activity,
            request,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=LLM_RETRY_POLICY,
        )
