"""
SOP 自律修正 Activity — バリデーション失敗項目を Gemini に渡して修正版を生成する。

failures リストをプロンプトに注入し、最小限の変更で全指摘を解消した
改善版 SOP を Gemini 2.5 Flash に生成させる。

CrewAI 拡張（fix_sop_with_crew_activity）:
    Writer（SOP 修正担当）と Reviewer（セキュリティ・規律レビュー担当）の
    2 エージェントを直列に実行し、Writer の修正済み SOP を LLMResult として返す。
    既存の fix_sop_activity とシグネチャ・戻り値型が同一なので、
    将来的にワークフロー側の呼び出し先を差し替えるだけで移行できる。
"""

import asyncio
import os
import time

from temporalio import activity

from core.models import LLMResult

_MODEL = "gemini-2.5-flash-lite"
_CREW_MODEL = "gemini/gemini-2.5-flash"  # CrewAI (LiteLLM 経由) — crew_activity.py と同一

# ラウンドごとの temperature テーブル（差し戻し回数に応じて LLM の探索幅を広げる）
_TEMPERATURE_BY_ROUND: dict[int, float] = {
    0: 0.3,   # 保守的：最小変更で確実に直す
    1: 0.6,   # 中庸：前回より踏み込んだ再解釈を許容
    2: 0.9,   # 積極的：大胆な再構成も許容
}

# ラウンドごとの緊迫度プレフィックス（エージェントへの追加指示）
_URGENCY_PREFIX_BY_ROUND: dict[int, str] = {
    0: "",
    1: (
        "\n\n【重要】前回の修正では指摘事項を解消しきれませんでした。"
        "今回は全項目を一つずつ確認し、必ず解消してください。"
    ),
    2: (
        "\n\n【最終修正】これが最後の修正機会です。"
        "セキュリティと規律の不備を大胆かつクリエイティブな視点で洗い出し、"
        "残存する問題点を全て解消してください。"
    ),
}

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


def _build_sop_crew(
    sop_text: str,
    failures: list[str],
    human_feedback: str,
    llm,
    attempt: int = 0,
):
    """
    Writer と Reviewer の 2 エージェント Crew を構築して返す。

    Writer が SOP の修正案を生成し、Reviewer がセキュリティ・規律の観点で
    Writer の出力を検証する直列タスクチェーンを定義する。
    Crew インスタンスは kickoff() 呼び出し前の状態で返される。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :param human_feedback: 人間からの追加修正指示（空文字可）
    :param llm: CrewAI LLM インスタンス（呼び出し元で生成して渡す）
    :param attempt: 差し戻し回数（緊迫度プレフィックスの選択に使用）
    :returns: 実行準備済みの Crew インスタンス
    """
    from crewai import Agent, Task, Crew

    failures_str = "\n".join(f"- {f}" for f in failures) if failures else "（指定なし）"
    human_section = (
        f"\n\n## 人間からの追加修正指示\n{human_feedback}" if human_feedback else ""
    )
    sop_snippet = sop_text[:4000] + ("\n...(省略)" if len(sop_text) > 4000 else "")
    urgency = _URGENCY_PREFIX_BY_ROUND.get(attempt, _URGENCY_PREFIX_BY_ROUND[2])

    writer = Agent(
        role="SOP 修正担当",
        goal=(
            "SOP のバリデーション失敗項目を全て解消し、"
            "最小限の変更で明確・再現性の高い改善版を Markdown 形式で出力する。"
        ),
        backstory=(
            "5 年以上のテクニカルライター経験を持つ専門家。"
            "Markdown ドキュメントの品質向上と手順の明確化を得意とする。"
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    reviewer = Agent(
        role="セキュリティ・規律レビュー担当",
        goal=(
            "Writer が修正した SOP に残存するセキュリティリスク"
            "（認証情報の平文記載・過剰権限など）と規律違反"
            "（承認フロー欠如・監査ログ不備など）を重大度付きで指摘する。"
        ),
        backstory=(
            "情報セキュリティ 8 年の経験を持つシニアエンジニア。"
            "OWASP ガイドラインと社内セキュリティポリシーに精通している。"
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    task_write = Task(
        description=(
            "以下の問題点リストを全て解消した改善版 SOP を Markdown 形式で出力してください。"
            "内容の本質は変えず、最小限の修正で問題を解消してください。\n\n"
            f"## 修正が必要な問題点\n{failures_str}{human_section}\n\n"
            f"## 修正対象の SOP\n{sop_snippet}"
            f"{urgency}"
        ),
        expected_output=(
            "全問題点を解消した改善版 SOP を Markdown 形式のみで出力してください。"
            "説明文は不要です。SOP 本文のみを出力してください。"
        ),
        agent=writer,
    )

    task_review = Task(
        description=(
            "Writer が修正した SOP をセキュリティ・規律の観点で厳格にレビューしてください。\n"
            "確認観点:\n"
            "- 認証情報（パスワード・トークン）の平文記載\n"
            "- 最小権限原則の遵守\n"
            "- 承認・監査フローの有無\n"
            "- 緊急時のロールバック手順\n"
            "- 障害発生時の緊急連絡体制\n\n"
            "各観点を一つずつ丁寧に確認し、評価根拠とともに出力してください。"
        ),
        expected_output=(
            "以下の形式でレビュー結果を出力してください:\n\n"
            "## レビュー観点チェック\n"
            "各観点について「確認済み / 問題あり / 該当なし」と評価根拠を記載してください。\n"
            "- 認証情報（パスワード・トークン）の平文記載: \n"
            "- 最小権限原則の遵守: \n"
            "- 承認・監査フローの有無: \n"
            "- 緊急時のロールバック手順: \n"
            "- 障害発生時の緊急連絡体制: \n\n"
            "## 発見した問題点\n"
            "重大度（高/中/低）付きの箇条書きで記載してください。\n"
            "問題がない場合は「指摘なし」と記載してください。\n\n"
            "## 総評\n"
            "エンタープライズ品質の観点から総合評価を2〜3文で記載してください。"
        ),
        agent=reviewer,
        context=[task_write],
    )

    return Crew(
        agents=[writer, reviewer],
        tasks=[task_write, task_review],
        verbose=True,
    )


# NOTE: 後方互換のため残存。新規実装では writer_task_activity / reviewer_task_activity を使用すること。
@activity.defn
async def fix_sop_with_crew_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
    attempt: int = 0,
) -> LLMResult:
    """
    Writer + Reviewer の CrewAI 2 エージェントで SOP を修正する Activity。

    fix_sop_activity と同一のシグネチャ・戻り値型を持つ。
    将来的にワークフロー側の呼び出し先を本 Activity に切り替えるだけで移行できる。

    crew.kickoff() は同期ブロッキングなので asyncio.to_thread で安全にラップする。
    LLMResult.text には Writer の修正済み SOP を格納する。

    attempt が増えるほど _TEMPERATURE_BY_ROUND に従い temperature を引き上げ、
    _URGENCY_PREFIX_BY_ROUND に従い task_write の指示に緊迫度を付与する。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :param human_feedback: 人間からの追加修正指示（省略時は空文字）
    :param attempt: 差し戻し回数（デフォルト 0、後方互換）
    :returns: Writer の修正済み SOP を含む LLMResult
    """
    from crewai import LLM

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    temperature = _TEMPERATURE_BY_ROUND.get(attempt, 0.9)
    llm = LLM(model=_CREW_MODEL, api_key=api_key, temperature=temperature)
    crew = _build_sop_crew(sop_text, failures, human_feedback, llm, attempt)

    start = time.monotonic()
    crew_output = await asyncio.to_thread(crew.kickoff)
    latency_ms = (time.monotonic() - start) * 1000

    usage = crew_output.token_usage
    total_tokens = getattr(usage, "total_tokens", 0) or 0

    corrected_sop = ""
    if crew_output.tasks_output:
        corrected_sop = crew_output.tasks_output[0].raw or ""
    if not corrected_sop:
        corrected_sop = crew_output.raw or ""

    reviewer_log = ""
    if len(crew_output.tasks_output) > 1:
        reviewer_log = crew_output.tasks_output[1].raw or ""

    return LLMResult(
        text=corrected_sop,
        model=_CREW_MODEL,
        input_tokens=0,
        output_tokens=0,
        total_tokens=total_tokens,
        latency_ms=round(latency_ms, 2),
        agent_logs=reviewer_log,
    )


@activity.defn
async def writer_task_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
    attempt: int = 0,
) -> LLMResult:
    """
    Writer エージェント単体を起動し、修正済み SOP を返す。

    fix_sop_with_crew_activity から Writer の責務を分離した独立 Activity。
    ワークフロー側で _active_agent = "Writer" を設定してから本 Activity を呼び出すことで、
    UI へリアルタイムにエージェントステータスを中継できる。

    attempt に応じて _TEMPERATURE_BY_ROUND で temperature を制御し、
    _URGENCY_PREFIX_BY_ROUND で task の緊迫度を引き上げる。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :param human_feedback: 人間からの追加修正指示（省略時は空文字）
    :param attempt: 差し戻し回数（デフォルト 0、後方互換）
    :returns: Writer の修正済み SOP を含む LLMResult（agent_logs は空文字）
    """
    from crewai import Agent, Task, Crew, LLM

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    temperature = _TEMPERATURE_BY_ROUND.get(attempt, 0.9)
    llm = LLM(model=_CREW_MODEL, api_key=api_key, temperature=temperature)

    failures_str = "\n".join(f"- {f}" for f in failures) if failures else "（指定なし）"
    human_section = (
        f"\n\n## 人間からの追加修正指示\n{human_feedback}" if human_feedback else ""
    )
    sop_snippet = sop_text[:4000] + ("\n...(省略)" if len(sop_text) > 4000 else "")
    urgency = _URGENCY_PREFIX_BY_ROUND.get(attempt, _URGENCY_PREFIX_BY_ROUND[2])

    writer = Agent(
        role="SOP 修正担当",
        goal=(
            "SOP のバリデーション失敗項目を全て解消し、"
            "最小限の変更で明確・再現性の高い改善版を Markdown 形式で出力する。"
        ),
        backstory=(
            "5 年以上のテクニカルライター経験を持つ専門家。"
            "Markdown ドキュメントの品質向上と手順の明確化を得意とする。"
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    task_write = Task(
        description=(
            "以下の問題点リストを全て解消した改善版 SOP を Markdown 形式で出力してください。"
            "内容の本質は変えず、最小限の修正で問題を解消してください。\n\n"
            f"## 修正が必要な問題点\n{failures_str}{human_section}\n\n"
            f"## 修正対象の SOP\n{sop_snippet}"
            f"{urgency}"
        ),
        expected_output=(
            "全問題点を解消した改善版 SOP を Markdown 形式のみで出力してください。"
            "説明文は不要です。SOP 本文のみを出力してください。"
        ),
        agent=writer,
    )

    crew = Crew(agents=[writer], tasks=[task_write], verbose=True)

    start = time.monotonic()
    crew_output = await asyncio.to_thread(crew.kickoff)
    latency_ms = (time.monotonic() - start) * 1000

    usage = crew_output.token_usage
    total_tokens = getattr(usage, "total_tokens", 0) or 0

    corrected_sop = ""
    if crew_output.tasks_output:
        corrected_sop = crew_output.tasks_output[0].raw or ""
    if not corrected_sop:
        corrected_sop = crew_output.raw or ""

    return LLMResult(
        text=corrected_sop,
        model=_CREW_MODEL,
        input_tokens=0,
        output_tokens=0,
        total_tokens=total_tokens,
        latency_ms=round(latency_ms, 2),
        agent_logs="",
    )


@activity.defn
async def reviewer_task_activity(
    corrected_sop: str,
) -> LLMResult:
    """
    Reviewer エージェント単体を起動し、セキュリティ・規律の監査結果を返す。

    fix_sop_with_crew_activity から Reviewer の責務を分離した独立 Activity。
    ワークフロー側で _active_agent = "Reviewer" を設定してから本 Activity を呼び出すことで、
    UI へリアルタイムにエージェントステータスを中継できる。

    corrected_sop を task_review の description に直接埋め込むため、
    前工程の Writer Task への context 参照は不要。

    :param corrected_sop: Writer が出力した修正済み SOP 全文
    :returns: レビュー結果を含む LLMResult（text と agent_logs の両方に Reviewer 出力を格納）
    """
    from crewai import Agent, Task, Crew, LLM

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    llm = LLM(model=_CREW_MODEL, api_key=api_key, temperature=0.3)

    sop_snippet = corrected_sop[:4000] + ("\n...(省略)" if len(corrected_sop) > 4000 else "")

    reviewer = Agent(
        role="セキュリティ・規律レビュー担当",
        goal=(
            "提供された SOP に残存するセキュリティリスク"
            "（認証情報の平文記載・過剰権限など）と規律違反"
            "（承認フロー欠如・監査ログ不備など）を重大度付きで指摘する。"
        ),
        backstory=(
            "情報セキュリティ 8 年の経験を持つシニアエンジニア。"
            "OWASP ガイドラインと社内セキュリティポリシーに精通している。"
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    task_review = Task(
        description=(
            "以下の SOP をセキュリティ・規律の観点で厳格にレビューしてください。\n"
            "確認観点:\n"
            "- 認証情報（パスワード・トークン）の平文記載\n"
            "- 最小権限原則の遵守\n"
            "- 承認・監査フローの有無\n"
            "- 緊急時のロールバック手順\n"
            "- 障害発生時の緊急連絡体制\n\n"
            "各観点を一つずつ丁寧に確認し、評価根拠とともに出力してください。\n\n"
            f"## レビュー対象の SOP\n{sop_snippet}"
        ),
        expected_output=(
            "以下の形式でレビュー結果を出力してください:\n\n"
            "## レビュー観点チェック\n"
            "各観点について「確認済み / 問題あり / 該当なし」と評価根拠を記載してください。\n"
            "- 認証情報（パスワード・トークン）の平文記載: \n"
            "- 最小権限原則の遵守: \n"
            "- 承認・監査フローの有無: \n"
            "- 緊急時のロールバック手順: \n"
            "- 障害発生時の緊急連絡体制: \n\n"
            "## 発見した問題点\n"
            "重大度（高/中/低）付きの箇条書きで記載してください。\n"
            "問題がない場合は「指摘なし」と記載してください。\n\n"
            "## 総評\n"
            "エンタープライズ品質の観点から総合評価を2〜3文で記載してください。"
        ),
        agent=reviewer,
    )

    crew = Crew(agents=[reviewer], tasks=[task_review], verbose=False)

    start = time.monotonic()
    crew_output = await asyncio.to_thread(crew.kickoff)
    latency_ms = (time.monotonic() - start) * 1000

    usage = crew_output.token_usage
    total_tokens = getattr(usage, "total_tokens", 0) or 0

    reviewer_output = ""
    if crew_output.tasks_output:
        reviewer_output = crew_output.tasks_output[0].raw or ""
    if not reviewer_output:
        reviewer_output = crew_output.raw or ""

    return LLMResult(
        text=reviewer_output,
        model=_CREW_MODEL,
        input_tokens=0,
        output_tokens=0,
        total_tokens=total_tokens,
        latency_ms=round(latency_ms, 2),
        agent_logs=reviewer_output,
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
