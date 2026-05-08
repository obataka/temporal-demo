"""
CrewAI Agent Activities — Temporal Worker から多役割エージェントを安全に呼び出すラッパー。

Agents:
    proofreader  : 校正担当。文法・表記・論理的一貫性を検証し修正案を提案する。
    tech_reviewer: 技術担当。コード例の正確性・実装手順の完全性を検証する。

merge_reviews_activity:
    両エージェントの出力を Gemini で統合し、最終版 SOP を生成する。

設計上の注意:
    CrewAI の crew.kickoff() は同期ブロッキング。asyncio.to_thread() でスレッド実行し、
    Temporal の asyncio イベントループをブロックしない。
    task_callback で各 Agent の出力を収集し、Inner Monologue として返す。
"""

import asyncio
import os
import time

from temporalio import activity

from core.models import AgentReviewRequest, AgentResult, LLMResult

_GEMINI_CREW = "gemini/gemini-2.5-flash"   # CrewAI (LiteLLM) 経由
_GEMINI_MERGE = "gemini-2.5-flash"          # Merge Activity は google-genai 直接呼び出し

# ─── Agent 設定テーブル ───────────────────────────────────────────────────────

_AGENT_CFG = {
    "proofreader": {
        "role": "SOP校正担当",
        "goal": (
            "SOPの文章品質を高める。"
            "文法・送り仮名・表記ゆれ・論理的一貫性の問題を特定し、"
            "具体的な修正案を提示する。"
        ),
        "backstory": (
            "10年以上のテクニカルライター経験を持つ校正専門家。"
            "Markdown ドキュメントの品質保証を得意とする。"
        ),
    },
    "tech_reviewer": {
        "role": "技術レビュー担当",
        "goal": (
            "SOPの技術的正確性を保証する。"
            "コードスニペットの動作可能性・API の使用法・"
            "エラーハンドリング設計の妥当性を検証する。"
        ),
        "backstory": (
            "Python/Temporal バックエンド開発 5 年以上のシニアエンジニア。"
            "Temporal SDK と Gemini API を熟知している。"
        ),
    },
}


def _task_description(request: AgentReviewRequest) -> str:
    """リクエスト内容から Task の description を構築する。"""
    parts: list[str] = []

    if request.hints:
        parts.append(
            "## レビュアーへのヒント（優先対応）\n"
            + "\n".join(f"- {h}" for h in request.hints)
        )

    if request.proofreader_output:
        excerpt = request.proofreader_output[:1500]
        if len(request.proofreader_output) > 1500:
            excerpt += "\n...(省略)"
        parts.append(f"## 校正担当の指摘（参考）\n{excerpt}")

    draft_snippet = request.draft[:4000]
    if len(request.draft) > 4000:
        draft_snippet += "\n...(省略)"

    if request.agent_role == "proofreader":
        parts.append(
            "## 依頼内容\n"
            "以下の SOP 草稿を校正し、問題点と修正案を箇条書きで提示してください。\n\n"
            "### 確認項目\n"
            "- 文法・句読点・送り仮名の誤り\n"
            "- 用語の表記ゆれ（例: 「ワークフロー」vs「workflow」）\n"
            "- 段落構造と見出しの適切さ\n"
            "- 説明の論理的一貫性\n\n"
            f"## SOP草稿\n{draft_snippet}"
        )
    else:
        parts.append(
            "## 依頼内容\n"
            "以下の SOP 草稿を技術的観点でレビューし、問題点と改善提案を提示してください。\n\n"
            "### 確認項目\n"
            "- コードスニペットの正確性と実行可能性\n"
            "- Temporal SDK・Gemini API の使用法の正確性\n"
            "- エラーハンドリングと retry_policy 設計の妥当性\n"
            "- 手順の完全性（省略ステップがないか）\n\n"
            f"## SOP草稿\n{draft_snippet}"
        )

    return "\n\n".join(parts)


def _expected_output(role: str) -> str:
    if role == "proofreader":
        return "修正提案リスト（各項目: 箇所・問題点・修正案）を Markdown 形式で出力。"
    return "技術的な問題点と改善提案リストを Markdown 形式で出力。"


# ─── Activities ──────────────────────────────────────────────────────────────

@activity.defn
async def run_agent_activity(request: AgentReviewRequest) -> AgentResult:
    """
    CrewAI エージェント（校正担当 or 技術担当）を Temporal Activity として実行する。

    crew.kickoff() は同期ブロッキングなので asyncio.to_thread で安全にラップする。
    task_callback で Inner Monologue（各ステップの出力）を収集して返す。
    """
    from crewai import Agent, Task, Crew, LLM

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    llm = LLM(model=_GEMINI_CREW, api_key=api_key)
    cfg = _AGENT_CFG[request.agent_role]

    # Inner Monologue バッファ: task_callback で追記される
    thoughts: list[str] = []

    def on_task_complete(task_output) -> None:
        raw = (task_output.raw or "").strip()
        if raw:
            thoughts.append(raw[:600])

    agent = Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    task = Task(
        description=_task_description(request),
        expected_output=_expected_output(request.agent_role),
        agent=agent,
        callback=on_task_complete,
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=False)

    start = time.monotonic()
    # sync CrewAI をスレッドプールで実行し、asyncio イベントループをブロックしない
    crew_output = await asyncio.to_thread(crew.kickoff)
    latency_ms = (time.monotonic() - start) * 1000

    usage = crew_output.token_usage
    tokens = getattr(usage, "total_tokens", 0) or 0

    return AgentResult(
        agent_role=request.agent_role,
        output=crew_output.raw or "",
        thoughts=thoughts,
        tokens=tokens,
        latency_ms=round(latency_ms, 2),
    )


@activity.defn
async def merge_reviews_activity(corrections: str, tech_review: str, draft: str) -> LLMResult:
    """
    校正担当・技術担当の出力を Gemini で統合して最終版 SOP を生成する Activity。
    CrewAI は使わず google-genai を直接呼び出す（シンプルな統合タスクのため）。
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "あなたはドキュメント統合の専門家です。"
        "校正担当と技術担当のレビュー結果を統合し、"
        "全ての指摘を反映した最終版 SOP を Markdown 形式で出力してください。"
        "改善理由の説明は不要です。最終版のみを出力してください。"
    )

    contents = (
        f"## 元のSOP草稿\n{draft[:3000]}\n\n"
        f"## 校正担当の指摘（文法・表記）\n{corrections[:2000]}\n\n"
        f"## 技術担当の指摘（技術的正確性）\n{tech_review[:2000]}\n\n"
        "---\n上記の全指摘を反映した最終版 SOP を出力してください。"
    )

    start = time.monotonic()
    response = client.models.generate_content(
        model=_GEMINI_MERGE,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_instruction),
    )
    latency_ms = (time.monotonic() - start) * 1000

    usage = response.usage_metadata
    return LLMResult(
        text=response.text,
        model=_GEMINI_MERGE,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        total_tokens=getattr(usage, "total_token_count", 0) or 0,
        latency_ms=round(latency_ms, 2),
    )
