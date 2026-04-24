"""
Comparison Workflow — Mock と Gemini を同一 Workflow 内で並列実行し、
レイテンシ・トークン数・コストを並べて比較するデモ用ワークフロー。

Usage (from run_comparison.py):
    python run_comparison.py "任意のプロンプト"

比較ポイント:
  - Mock   : 即時応答 / 低コスト / 決定論的トークン数
  - Gemini : 実推論 / 実コスト / 可変トークン数
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ActivityError

from core.models import LLMResult
from core.retry_policy import LLM_RETRY_POLICY

with workflow.unsafe.imports_passed_through():
    from activities.llm_activity import call_llm_activity
    from activities.mock_activity import call_mock_llm_activity


@workflow.defn
class comparison_workflow:
    """Mock と Gemini を並列実行してコスト・レイテンシを比較するワークフロー。"""

    @workflow.run
    async def run(self, prompt: str) -> dict:
        workflow.upsert_search_attributes({"LLM_Status": ["Running"]})

        # Mock と Gemini を並列実行
        mock_handle = workflow.execute_activity(
            call_mock_llm_activity,
            prompt,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=LLM_RETRY_POLICY,
        )
        gemini_handle = workflow.execute_activity(
            call_llm_activity,
            prompt,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=LLM_RETRY_POLICY,
        )

        try:
            mock_result: LLMResult = await mock_handle
            gemini_result: LLMResult = await gemini_handle

            total_tokens = mock_result.total_tokens + gemini_result.total_tokens
            workflow.upsert_search_attributes({
                "LLM_Model": ["comparison"],
                "Total_Tokens": [total_tokens],
                "LLM_Status": ["Success"],
            })

            return {
                "mock": {
                    "model": mock_result.model,
                    "text": mock_result.text,
                    "input_tokens": mock_result.input_tokens,
                    "output_tokens": mock_result.output_tokens,
                    "total_tokens": mock_result.total_tokens,
                    "latency_ms": mock_result.latency_ms,
                },
                "gemini": {
                    "model": gemini_result.model,
                    "text": gemini_result.text[:200] + ("..." if len(gemini_result.text) > 200 else ""),
                    "input_tokens": gemini_result.input_tokens,
                    "output_tokens": gemini_result.output_tokens,
                    "total_tokens": gemini_result.total_tokens,
                    "latency_ms": gemini_result.latency_ms,
                },
            }

        except ActivityError:
            workflow.upsert_search_attributes({"LLM_Status": ["Failed"]})
            raise
