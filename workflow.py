"""
Temporal Workflow & Activity definitions.

Activity  : call_llm_activity  — Gemini API (gemini-2.0-flash 無料枠) を呼び出す。
                                  DEBUG_FAIL=1 で意図的に失敗させリトライを検証可能。
Workflow  : ai_agent_workflow   — ActivityをRetryPolicy(最大3回)で包んで実行。
"""

import os
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy


# --------------------------------------------------------------------------- #
# Activity                                                                     #
# --------------------------------------------------------------------------- #

@activity.defn
async def call_llm_activity(prompt: str) -> str:
    """Gemini API を呼び出して応答を返す。

    環境変数 DEBUG_FAIL=1 を設定すると意図的に例外を送出し、
    Temporal のリトライ動作を検証できる。
    """
    # デバッグモード: 意図的に失敗させてリトライを確認する
    if os.environ.get("DEBUG_FAIL") == "1":
        raise RuntimeError(
            "[DEBUG_FAIL] LLM 呼び出しを意図的に失敗させました。Temporal がリトライします。"
        )

    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text


# --------------------------------------------------------------------------- #
# Workflow                                                                     #
# --------------------------------------------------------------------------- #

@workflow.defn
class ai_agent_workflow:
    """LLM呼び出しを Temporal で包んだ「不滅ワークフロー」。

    Activity が失敗しても RetryPolicy により最大3回まで自動リトライする。
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
        )

        result = await workflow.execute_activity(
            call_llm_activity,
            prompt,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry_policy,
        )
        return result
