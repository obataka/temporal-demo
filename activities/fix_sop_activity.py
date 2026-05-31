"""
SOP 自律修正 Activity — バリデーション失敗項目を Gemini に渡して修正版を生成する。

failures リストをプロンプトに注入し、最小限の変更で全指摘を解消した
改善版 SOP を Gemini 2.5 Flash に生成させる。
"""

import os
import time

from temporalio import activity

from core.models import LLMResult

_MODEL = "gemini-2.5-flash-lite"

_SYSTEM_INSTRUCTION = (
    "あなたは SOP 品質改善の専門家です。"
    "提供された SOP ドキュメントの問題点リストを確認し、"
    "全ての問題を解消した改善版 SOP を Markdown 形式で出力してください。"
    "内容の本質は変えず、最小限の修正で問題を解消してください。"
    "改善理由の説明は不要です。改善版 SOP のみを出力してください。"
)


def _build_prompt(sop_text: str, failures: list[str], human_feedback: str = "") -> str:
    """
    SOP テキストと失敗リストから修正依頼プロンプトを構築する。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :param human_feedback: 人間からの追加修正指示（省略時は空文字）
    :returns: Gemini に送信するプロンプト文字列
    """
    failures_str = "\n".join(f"- {f}" for f in failures)
    human_section = (
        f"\n\n## 人間からの修正指示\n{human_feedback}" if human_feedback else ""
    )
    return (
        f"## 修正が必要な問題点\n{failures_str}{human_section}\n\n"
        f"## 修正対象の SOP\n{sop_text}\n\n"
        "---\n上記の問題点を全て解消した改善版 SOP を出力してください。"
    )


@activity.defn
async def fix_sop_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
) -> LLMResult:
    """
    バリデーション失敗項目を修正した SOP を Gemini に生成させる。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :param human_feedback: 人間からの追加修正指示（省略時は空文字）
    :returns: 修正済み SOP を含む LLMResult
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)
    contents = _build_prompt(sop_text, failures, human_feedback)

    start = time.monotonic()
    response = client.models.generate_content(
        model=_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_INSTRUCTION),
    )
    latency_ms = (time.monotonic() - start) * 1000

    usage = response.usage_metadata
    return LLMResult(
        text=response.text,
        model=_MODEL,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        total_tokens=getattr(usage, "total_token_count", 0) or 0,
        latency_ms=round(latency_ms, 2),
    )
