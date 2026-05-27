"""
SOP 生成 Activity — フェーズ別 Gemini 呼び出し。

フェーズ:
    outline : 章立て提案（ソースコードを分析してアウトライン提案）
    draft   : 詳細執筆（承認済みアウトラインをもとに本文執筆）
    review  : 最終レビュー（草稿を徹底レビューして最終版を出力）
"""

import os
import time

from temporalio import activity

from core.models import SOPRequest, LLMResult

_MODEL = "gemini-2.5-flash-lite"

_SYSTEM = {
    "outline": (
        "あなたは経験豊富なドキュメントアーキテクトです。"
        "与えられたソースコードを分析し、標準作業手順書（SOP）の章立て（アウトライン）を提案してください。"
        "各章のタイトルと1〜2行の説明を含め、明確で構造化されたアウトラインをMarkdownで出力してください。"
    ),
    "outline_retry": (
        "あなたは経験豊富なドキュメントアーキテクトです。"
        "前回のアウトラインに対して人間からフィードバックが届いています。"
        "そのフィードバックを最優先で反映し、改善されたアウトラインをMarkdownで提供してください。"
    ),
    "draft": (
        "あなたは熟練した技術ライターです。"
        "承認されたアウトラインに基づき、ソースコードの詳細な標準作業手順書（SOP）本文をMarkdownで執筆してください。"
        "各章を詳細に展開し、実装の意図・手順・注意点・コード例を含めてください。"
    ),
    "draft_retry": (
        "あなたは熟練した技術ライターです。"
        "前回のSOP草稿に対して人間からフィードバックが届いています。"
        "そのフィードバックを最優先で反映し、改善された草稿をMarkdownで提供してください。"
    ),
    "review": (
        "あなたは品質保証の専門家です。"
        "提供されたSOP草稿を徹底的にレビューし、【改善点リスト】と【最終版SOP】をMarkdownで提供してください。"
        "正確性・完全性・明確さ・実用性を重視してください。"
    ),
    "review_retry": (
        "あなたは品質保証の専門家です。"
        "前回のレビュー結果に対して人間からフィードバックが届いています。"
        "そのフィードバックを最優先で反映し、改善された最終版をMarkdownで提供してください。"
    ),
}


def _build_contents(request: SOPRequest) -> str:
    phase = request.phase
    is_retry = request.attempt > 0

    if phase == "outline":
        base = (
            f"## ドキュメント化対象\n{request.topic}\n\n"
            f"## ソースコード\n```python\n{request.source_code}\n```"
        )
        if is_retry:
            return (
                f"{base}\n\n"
                f"## 前回のアウトライン（試行 #{request.attempt - 1}）\n"
                f"{request.previous_output}\n\n"
                f"## 人間からのフィードバック\n{request.feedback}\n\n"
                "---\nフィードバックを反映した改善版アウトラインを提供してください。"
            )
        return base + "\n\n---\n上記ソースコードの SOP アウトラインを提案してください。"

    elif phase == "draft":
        base = (
            f"## ドキュメント化対象\n{request.topic}\n\n"
            f"## 承認済みアウトライン\n{request.outline}\n\n"
            f"## ソースコード\n```python\n{request.source_code}\n```"
        )
        if is_retry:
            return (
                f"{base}\n\n"
                f"## 前回の草稿（試行 #{request.attempt - 1}）\n"
                f"{request.previous_output}\n\n"
                f"## 人間からのフィードバック\n{request.feedback}\n\n"
                "---\nフィードバックを反映した改善版草稿を提供してください。"
            )
        return base + "\n\n---\n上記アウトラインに基づき、詳細なSOP本文を執筆してください。"

    else:  # review
        base = (
            f"## ドキュメント化対象\n{request.topic}\n\n"
            f"## SOP草稿\n{request.draft}"
        )
        if is_retry:
            return (
                f"{base}\n\n"
                f"## 前回のレビュー結果（試行 #{request.attempt - 1}）\n"
                f"{request.previous_output}\n\n"
                f"## 人間からのフィードバック\n{request.feedback}\n\n"
                "---\nフィードバックを反映した改善された最終版を提供してください。"
            )
        return base + "\n\n---\nこのSOP草稿をレビューし、【改善点リスト】と【最終版SOP】を提供してください。"


@activity.defn
async def generate_sop_phase_activity(request: SOPRequest) -> LLMResult:
    """フェーズ別 SOP 生成 Activity。Gemini の system_instruction でフェーズを制御する。"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)

    phase_key = f"{request.phase}_retry" if request.attempt > 0 else request.phase
    system_instruction = _SYSTEM[phase_key]
    contents = _build_contents(request)

    start = time.monotonic()
    response = client.models.generate_content(
        model=_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_instruction),
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
