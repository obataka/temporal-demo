"""
Immortal Agent Workflow — Signal/Query を備えた長期稼働型エージェント。

外部から Signal でタスク追加・優先度変更・フィードバック注入を行い、
Query でリアルタイム状態と統計を取得できる。
Temporal のイベントソーシングにより、クラッシュ後も Signal の効果が保持される。

Signals:
    add_task(task: str)                  -- タスクキューに追加
    update_task_priority(priority: int)  -- 優先度を 1〜10 で更新
    inject_human_feedback(feedback: str) -- 次のプロンプトに注入するフィードバック
    stop_agent()                         -- グレースフルシャットダウン

Queries:
    get_status() -> dict                 -- 現在の実行状態
    get_live_stats() -> dict             -- 累積統計（DB書き込み前のリアルタイム値）
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ActivityError

from core.models import AgentStats, LLMResult
from core.retry_policy import LLM_RETRY_POLICY

with workflow.unsafe.imports_passed_through():
    from activities.llm_activity import call_llm_activity
    from activities.mock_activity import call_mock_llm_activity


@workflow.defn
class immortal_agent_workflow:

    def __init__(self) -> None:
        self._task_queue: list[str] = []
        self._priority: int = 5          # 1(低)〜10(高)
        self._human_feedback: str | None = None
        self._stop_requested: bool = False
        self._stats = AgentStats()
        self._current_task: str | None = None
        self._status: str = "idle"

    # ─── Signal Handlers ─────────────────────────────────────────────────────
    # Temporal のイベント履歴に記録される → クラッシュ後も replay で復元される

    @workflow.signal
    def add_task(self, task: str) -> None:
        """タスクキューにタスクを追加する。実行中でも即時受付。"""
        self._task_queue.append(task)

    @workflow.signal
    def update_task_priority(self, priority: int) -> None:
        """エージェントの処理優先度を変更する（1=低, 10=高）。"""
        self._priority = max(1, min(10, priority))

    @workflow.signal
    def inject_human_feedback(self, feedback: str) -> None:
        """次のタスク実行時にプロンプト先頭へ注入する人間フィードバック。
        一度使われると消費される（one-shot）。"""
        self._human_feedback = feedback

    @workflow.signal
    def stop_agent(self) -> None:
        """現在のタスク完了後にエージェントをグレースフルに停止する。"""
        self._stop_requested = True

    # ─── Query Handlers ──────────────────────────────────────────────────────
    # 副作用なし・同期。Worker が生きている間はリアルタイムで応答する。

    @workflow.query
    def get_status(self) -> dict:
        """エージェントの現在状態を返す。"""
        return {
            "status": self._status,
            "current_task": self._current_task,
            "queue_size": len(self._task_queue),
            "queued_tasks": list(self._task_queue),
            "priority": self._priority,
            "human_feedback_pending": self._human_feedback is not None,
            "stop_requested": self._stop_requested,
        }

    @workflow.query
    def get_live_stats(self) -> dict:
        """DB に書き込まれる前の最新統計をリアルタイムで返す。"""
        return {
            "tasks_completed": self._stats.tasks_completed,
            "tasks_failed": self._stats.tasks_failed,
            "total_input_tokens": self._stats.total_input_tokens,
            "total_output_tokens": self._stats.total_output_tokens,
            "total_tokens": self._stats.total_input_tokens + self._stats.total_output_tokens,
            "average_latency_ms": self._stats.average_latency_ms,
            "recent_results": self._stats.results[-3:],  # 直近3件
        }

    # ─── Main Loop ───────────────────────────────────────────────────────────

    @workflow.run
    async def run(
        self,
        initial_tasks: list[str],
        use_mock: bool = False,
        task_interval_seconds: float = 0.0,
    ) -> dict:
        """
        タスクが来るまで待機し、来たら処理するループ。
        stop_agent() シグナルを受け取るまで永続稼働する。
        """
        self._task_queue.extend(initial_tasks)
        activity_fn = call_mock_llm_activity if use_mock else call_llm_activity

        workflow.upsert_search_attributes({"LLM_Status": ["Running"]})

        while not self._stop_requested:
            # タスクが来るか、停止指示が来るまでブロック
            await workflow.wait_condition(
                lambda: bool(self._task_queue) or self._stop_requested
            )

            if self._stop_requested:
                break

            task = self._task_queue.pop(0)
            self._current_task = task
            self._status = "processing"

            # human_feedback があれば先頭に注入し、消費する（one-shot）
            prompt = task
            if self._human_feedback:
                prompt = f"[Human Guidance / Priority={self._priority}]\n{self._human_feedback}\n\n---\n\n{task}"
                self._human_feedback = None

            workflow.upsert_search_attributes({
                "LLM_Status": ["Running"],
                "Total_Tokens": [
                    self._stats.total_input_tokens + self._stats.total_output_tokens
                ],
            })

            try:
                result: LLMResult = await workflow.execute_activity(
                    activity_fn,
                    prompt,
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=LLM_RETRY_POLICY,
                )
                self._stats.record_success(result)

                workflow.upsert_search_attributes({
                    "LLM_Model": [result.model],
                    "Total_Tokens": [
                        self._stats.total_input_tokens + self._stats.total_output_tokens
                    ],
                    "LLM_Status": ["Running"],
                })

            except ActivityError:
                self._stats.record_failure()
                self._status = "error"
                workflow.upsert_search_attributes({"LLM_Status": ["Error"]})

            self._current_task = None
            self._status = "idle"

            # タスク間インターバル（デモ用：Signal を送る時間を確保）
            if task_interval_seconds > 0 and (self._task_queue or not self._stop_requested):
                self._status = "waiting_interval"
                await workflow.sleep(timedelta(seconds=task_interval_seconds))
                self._status = "idle"

        self._status = "stopped"
        workflow.upsert_search_attributes({"LLM_Status": ["Stopped"]})

        return {
            "tasks_completed": self._stats.tasks_completed,
            "tasks_failed": self._stats.tasks_failed,
            "total_tokens": self._stats.total_input_tokens + self._stats.total_output_tokens,
            "average_latency_ms": self._stats.average_latency_ms,
        }
