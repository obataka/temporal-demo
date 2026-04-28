"""
Real LLM Activity — Gemini API (gemini-2.5-flash) を呼び出す。
DEBUG_FAIL=1 で意図的に失敗させ Temporal のリトライを検証できる。
"""

import os
import time

from temporalio import activity

from core.models import LLMRequest, LLMResult
from core.observability import log_llm_interaction

_MODEL = "gemini-2.5-flash"

# 初回呼び出し用 system instruction
_SYSTEM_INITIAL = (
    "あなたは誠実で有能なAIアシスタントです。"
    "ユーザーの言語で、明確かつ丁寧に回答してください。"
)

# リトライ用 system instruction
_SYSTEM_RETRY = (
    "あなたは誠実で有能なAIアシスタントです。"
    "前回の回答に対して人間からフィードバックが届いています。"
    "そのフィードバックを最優先で反映し、具体的に改善された回答を提供してください。"
)


def _build_contents(request: LLMRequest) -> str:
    """LLMRequest から Gemini に渡す contents 文字列を構築する。"""
    if request.attempt == 0:
        return request.user_message

    return (
        f"## 元のタスク\n{request.user_message}\n\n"
        f"## 試行 {request.attempt - 1} の回答\n{request.previous_answer}\n\n"
        f"## 人間からのフィードバック\n{request.feedback}\n\n"
        "---\n上記フィードバックを具体的に反映した改善版の回答を提供してください。"
    )


@activity.defn
async def call_llm_activity(prompt: str) -> LLMResult:
    """単純プロンプト版（後方互換）。既存 workflow から引き続き使用可能。"""
    if os.environ.get("DEBUG_FAIL") == "1":
        raise RuntimeError(
            "[DEBUG_FAIL] LLM 呼び出しを意図的に失敗させました。Temporal がリトライします。"
        )

    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)

    with log_llm_interaction(_MODEL, prompt) as result_box:
        start = time.monotonic()
        response = client.models.generate_content(model=_MODEL, contents=prompt)
        latency_ms = (time.monotonic() - start) * 1000

        usage = response.usage_metadata
        result = LLMResult(
            text=response.text,
            model=_MODEL,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            total_tokens=getattr(usage, "total_token_count", 0) or 0,
            latency_ms=round(latency_ms, 2),
        )
        result_box.append(result)

    return result


@activity.defn
async def call_llm_with_context_activity(request: LLMRequest) -> LLMResult:
    """構造化リクエスト版。HITL ワークフロー専用。
    Gemini の system_instruction を活用し、フィードバックを適切に注入する。
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)
    system_instruction = _SYSTEM_RETRY if request.attempt > 0 else _SYSTEM_INITIAL
    contents = _build_contents(request)

    label = f"{_MODEL} (attempt={request.attempt})"
    with log_llm_interaction(label, contents[:120]) as result_box:
        start = time.monotonic()
        response = client.models.generate_content(
            model=_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        latency_ms = (time.monotonic() - start) * 1000

        usage = response.usage_metadata
        result = LLMResult(
            text=response.text,
            model=_MODEL,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            total_tokens=getattr(usage, "total_token_count", 0) or 0,
            latency_ms=round(latency_ms, 2),
        )
        result_box.append(result)

    return result
