"""
Real LLM Activity — Gemini API (gemini-2.5-flash) を呼び出す。
DEBUG_FAIL=1 で意図的に失敗させ Temporal のリトライを検証できる。
"""

import os
import time

from temporalio import activity

from core.models import LLMResult
from core.observability import log_llm_interaction


@activity.defn
async def call_llm_activity(prompt: str) -> LLMResult:
    if os.environ.get("DEBUG_FAIL") == "1":
        raise RuntimeError(
            "[DEBUG_FAIL] LLM 呼び出しを意図的に失敗させました。Temporal がリトライします。"
        )

    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)

    with log_llm_interaction("gemini-2.5-flash", prompt) as result_box:
        start = time.monotonic()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        latency_ms = (time.monotonic() - start) * 1000

        usage = response.usage_metadata
        result = LLMResult(
            text=response.text,
            model="gemini-2.5-flash",
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            total_tokens=getattr(usage, "total_token_count", 0) or 0,
            latency_ms=round(latency_ms, 2),
        )
        result_box.append(result)

    return result
