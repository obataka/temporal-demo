"""
マルチエージェント環境スタンドアップ検証スクリプト。

Writer（SOP 改善担当）と Reviewer（セキュリティ・規律レビュー担当）の
2 エージェントを CrewAI × Gemini で最小構成で起動し、LLM 接続および
タスク実行が正常に動作することを確認する。

Usage:
    python3 workflows/agent_test.py
"""

import os
import sys
import textwrap
import time

_MODEL = "gemini/gemini-2.5-flash"

_SAMPLE_SOP = """\
# 本番データベース接続手順

## 概要
本手順は本番 PostgreSQL に接続するためのガイドです。

## 手順
1. ターミナルを開く
2. 以下のコマンドを実行する:
   ```
   psql -h prod-db.example.com -U admin -p 5432 database_name
   ```
3. パスワードを入力する（パスワード: P@ssw0rd123）
4. 必要なクエリを実行する
5. 作業終了後、\\q で接続を切断する

## 注意事項
- 本番データは慎重に扱うこと
"""


def _separator(label: str) -> None:
    """セクション区切りラインを出力する。

    :param label: 区切りに表示するラベル文字列
    """
    width = 60
    print(f"\n{'─' * width}")
    print(f"  {label}")
    print("─" * width)


def _print_output(text: str, max_lines: int = 30) -> None:
    """エージェント出力を整形して出力する。

    :param text: 出力テキスト
    :param max_lines: 表示する最大行数
    """
    lines = text.strip().splitlines()
    for line in lines[:max_lines]:
        wrapped = textwrap.wrap(line, width=70) if line else [""]
        for w in wrapped:
            print(f"  {w}")
    if len(lines) > max_lines:
        print(f"  ... (残り {len(lines) - max_lines} 行省略)")


def build_agents(llm):
    """Writer と Reviewer の Agent インスタンスを生成して返す。

    :param llm: CrewAI LLM インスタンス
    :returns: (writer, reviewer) のタプル
    """
    from crewai import Agent

    writer = Agent(
        role="SOP 改善担当",
        goal=(
            "SOP の誤り・不明瞭な表現を特定し、"
            "手順を明確かつ再現性の高い内容に修正する。"
        ),
        backstory=(
            "5 年以上のテクニカルライター経験を持つ専門家。"
            "Markdown ドキュメントの品質向上と手順の明確化を得意とする。"
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    reviewer = Agent(
        role="セキュリティ・規律レビュー担当",
        goal=(
            "SOP に含まれるセキュリティ上のリスク（認証情報の平文記載、"
            "過剰な権限付与など）と規律違反（承認フロー欠如、監査ログ不備など）"
            "を厳格に指摘し、改善案を提示する。"
        ),
        backstory=(
            "情報セキュリティ 8 年の経験を持つシニアエンジニア。"
            "OWASP ガイドラインと社内セキュリティポリシーに精通している。"
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    return writer, reviewer


def build_tasks(writer, reviewer):
    """Writer タスクと Reviewer タスクを生成して返す。

    :param writer: Writer Agent インスタンス
    :param reviewer: Reviewer Agent インスタンス
    :returns: (task_write, task_review) のタプル
    """
    from crewai import Task

    task_write = Task(
        description=(
            "以下の SOP 草稿を精査し、不明瞭な表現や手順の欠落を修正してください。\n\n"
            f"## SOP 草稿\n{_SAMPLE_SOP}"
        ),
        expected_output=(
            "修正後の SOP を Markdown 形式で出力してください。"
            "変更箇所には理由を一言添えること。"
        ),
        agent=writer,
    )

    task_review = Task(
        description=(
            "Writer が修正した SOP をセキュリティ・規律の観点で厳格にレビューしてください。\n"
            "特に以下の観点で問題がないか確認すること:\n"
            "- 認証情報（パスワード・トークン）の平文記載\n"
            "- 最小権限原則の遵守\n"
            "- 承認・監査フローの有無\n"
            "- 緊急時のロールバック手順"
        ),
        expected_output=(
            "発見した問題点を重大度（高/中/低）付きで箇条書きにし、"
            "各問題に対する具体的な改善案を提示してください。"
        ),
        agent=reviewer,
        context=[task_write],
    )

    return task_write, task_review


def main() -> int:
    """スクリプトのエントリポイント。

    :returns: 終了コード（0: 成功、1: エラー）
    """
    from crewai import Crew, LLM

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] 環境変数 GEMINI_API_KEY が設定されていません。", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  CrewAI × Gemini — マルチエージェント起動確認")
    print("=" * 60)
    print(f"  モデル : {_MODEL}")
    print(f"  エージェント: Writer / Reviewer")
    print(f"  入力SOP: {len(_SAMPLE_SOP)} 文字")

    llm = LLM(model=_MODEL, api_key=api_key)

    writer, reviewer = build_agents(llm)
    task_write, task_review = build_tasks(writer, reviewer)

    crew = Crew(
        agents=[writer, reviewer],
        tasks=[task_write, task_review],
        verbose=False,
    )

    _separator("実行開始")
    print("  CrewAI crew.kickoff() を呼び出し中 ...")
    start = time.monotonic()
    result = crew.kickoff()
    elapsed = time.monotonic() - start

    usage = result.token_usage
    total_tokens = getattr(usage, "total_tokens", 0) or 0

    _separator("Writer — 修正済み SOP")
    if result.tasks_output and len(result.tasks_output) > 0:
        _print_output(result.tasks_output[0].raw or "")

    _separator("Reviewer — セキュリティ・規律指摘")
    if result.tasks_output and len(result.tasks_output) > 1:
        _print_output(result.tasks_output[1].raw or "")

    _separator("実行結果サマリ")
    print(f"  総トークン数 : {total_tokens:,}")
    print(f"  所要時間     : {elapsed:.1f}s")
    print(f"  終了ステータス: 正常\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
