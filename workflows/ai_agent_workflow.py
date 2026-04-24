"""
AI Agent Workflow — LLM Activity を Temporal で包んだ「不滅ワークフロー」。

Search Attributes (LLM_Model / Total_Tokens / LLM_Status) を動的に更新し、
Temporal UI 上でフィルタリング・一覧表示を可能にする。

Note: Workflow Sandbox のため、os/structlog に依存するモジュールはインポートしない。
      LLMResult は sandbox-safe な core.models から取得する。
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ActivityError

# Sandbox-safe なインポート（os/structlog に依存しない）
from core.models import LLMResult
from core.retry_policy import LLM_RETRY_POLICY

# Activity はトップレベルでインポート（run メソッド内での動的 import を避ける）
with workflow.unsafe.imports_passed_through():
    from activities.llm_activity import call_llm_activity
    from activities.mock_activity import call_mock_llm_activity


@workflow.defn
class ai_agent_workflow:

    @workflow.run
    async def run(self, prompt: str, use_mock: bool = False) -> str:
        workflow.upsert_search_attributes({"LLM_Status": ["Running"]})

        activity_fn = call_mock_llm_activity if use_mock else call_llm_activity

        try:
            result: LLMResult = await workflow.execute_activity(
                activity_fn,
                prompt,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=LLM_RETRY_POLICY,
            )

            workflow.upsert_search_attributes({
                "LLM_Model": [result.model],
                "Total_Tokens": [result.total_tokens],
                "LLM_Status": ["Success"],
            })

            return result.text

        except ActivityError:
            workflow.upsert_search_attributes({"LLM_Status": ["Failed"]})
            raise
