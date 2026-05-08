"""
SOP Generation Demo — Interactive Step-by-Step Approval

Usage:
    python sop_demo.py                            # デフォルト: hitl_agent_workflow.py を文書化
    python sop_demo.py --source workflows/immortal_agent_workflow.py
    python sop_demo.py --topic "カスタムトピック" --source path/to/code.py

フロー:
    フェーズ1 — Gemini がソースコードを分析してアウトラインを提案
    フェーズ2 — 承認済みアウトラインをもとに詳細な SOP 本文を執筆
    フェーズ3 — 草稿をレビューして最終版を出力
    各フェーズで: 空 Enter → 承認して次フェーズへ / テキスト入力 → 再生成

最後に: 全試行の比較ログ（Evidence）を表示
"""

import asyncio
import os
import sys
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from workflows.sop_workflow import sop_generation_workflow, PHASES, PHASE_LABELS

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

DEFAULT_SOURCE = "workflows/hitl_agent_workflow.py"
DEFAULT_TOPIC = "Human-in-the-Loop AI Agent ワークフロー（Temporal + Gemini）"

_W = 66
_SEP = "─" * _W


def _header(title: str) -> None:
    print(f"\n{'═' * _W}")
    print(f"  {title}")
    print(f"{'═' * _W}")


def _section(title: str) -> None:
    print(f"\n{'─' * _W}")
    print(f"  {title}")
    print(_SEP)


def _print_output(phase_label: str, attempt: int, output: str, feedback: str | None = None) -> None:
    tag = "初期生成" if attempt == 0 else f"フィードバック反映 #{attempt}"
    _section(f"{phase_label}  ┃  試行 #{attempt} — {tag}")
    if feedback:
        print(f"  フィードバック: 「{feedback}」\n")
    # 長い場合は先頭 800 文字を表示
    display = output.strip()
    if len(display) > 800:
        print(display[:800])
        print(f"\n  ... (残り {len(display) - 800} 文字は省略) ...")
    else:
        print(display)
    print()


def _print_evidence(history: list[dict]) -> None:
    _header("Evidence Log — 人間介入による改善の比較（Before / After）")

    # フェーズごとにグループ化
    phases: dict[str, list[dict]] = {}
    for entry in history:
        phases.setdefault(entry["phase"], []).append(entry)

    for phase, entries in phases.items():
        interventions = sum(1 for e in entries if e.get("feedback"))
        print(f"\n{'═' * _W}")
        print(f"  {entries[0]['phase_label']}  ─── 介入: {interventions} 回")
        print("═" * _W)

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            tag = "BEFORE" if i < len(entries) - 1 else ("AFTER " if len(entries) > 1 else "      ")
            approved = entry.get("approved", False)
            tokens = entry.get("tokens", 0)
            latency = entry.get("latency_ms", 0)
            output = entry["output"].strip()
            status_mark = "✅ 承認" if approved else "🔄 再生成"

            print(f"\n  {tag}  試行 #{entry['attempt']}  tokens={tokens:,}  latency={latency:.0f}ms  {status_mark}")

            if entry.get("feedback"):
                fb = entry["feedback"]
                short = fb[:74] + ("..." if len(fb) > 74 else "")
                print(f"  ↑ Signal: 「{short}」")

            print(f"  ┌{'─' * (_W - 4)}┐")
            lines = output.split("\n")
            for line in lines[:10]:
                if len(line) > _W - 6:
                    line = line[:_W - 9] + "..."
                print(f"  │ {line}")
            if len(lines) > 10:
                print(f"  │ ... (+{len(lines) - 10} 行)")
            print(f"  └{'─' * (_W - 4)}┘")

        # Before/After 差分統計（2試行以上のフェーズのみ）
        if len(entries) >= 2:
            b, a = entries[0], entries[-1]
            dt = a.get("tokens", 0) - b.get("tokens", 0)
            dl = len(a["output"]) - len(b["output"])
            pct_t = f"{dt / b['tokens'] * 100:+.0f}%" if b.get("tokens") else "n/a"
            pct_l = f"{dl / len(b['output']) * 100:+.0f}%" if b["output"] else "n/a"
            print(f"\n  📊 変化: tokens {'+' if dt >= 0 else ''}{dt:,} ({pct_t})  ─  "
                  f"chars {'+' if dl >= 0 else ''}{dl:,} ({pct_l})")

    # サマリー
    total = len(history)
    feedbacks = sum(1 for e in history if e.get("feedback"))
    total_tokens = sum(e.get("tokens", 0) for e in history)
    approved_count = sum(1 for e in history if e.get("approved"))

    print(f"\n{'═' * _W}")
    print(f"  合計試行: {total}  |  人間介入: {feedbacks} 回  |  総トークン: {total_tokens:,}  |  承認: {approved_count}/3 フェーズ")
    print(f"{'═' * _W}\n")


async def wait_for_ready(handle, timeout: float = 180.0) -> dict:
    """status が 'awaiting_approval' または 'completed' になるまでポーリングする。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = await handle.query("get_status")
            if status["status"] in ("awaiting_approval", "completed"):
                return status
        except Exception:
            pass
        await asyncio.sleep(2.0)
    raise TimeoutError(f"Workflow が {timeout}s 以内に応答しませんでした。")


async def main() -> None:
    # ── 引数パース ────────────────────────────────────────────────────────────
    args = sys.argv[1:]
    source_file = DEFAULT_SOURCE
    topic = DEFAULT_TOPIC

    i = 0
    while i < len(args):
        if args[i] == "--source" and i + 1 < len(args):
            source_file = args[i + 1]
            i += 2
        elif args[i] == "--topic" and i + 1 < len(args):
            topic = args[i + 1]
            i += 2
        else:
            i += 1

    # ── ソースコードを読み込む ─────────────────────────────────────────────────
    try:
        with open(source_file, encoding="utf-8") as f:
            source_code = f.read()
    except FileNotFoundError:
        print(f"Error: {source_file} が見つかりません。")
        sys.exit(1)

    # ── Temporal 接続 ─────────────────────────────────────────────────────────
    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"sop-{uuid.uuid4().hex[:8]}"

    _header("SOP 自動生成 — Interactive Step-by-Step Approval")
    print(f"  Workflow ID  : {workflow_id}")
    print(f"  Topic        : {topic}")
    print(f"  Source File  : {source_file} ({len(source_code)} chars)")
    print(f"  Phases       : {' → '.join(PHASE_LABELS.values())}")
    print(f"\n  操作方法     : 各フェーズ完了後にフィードバックを入力")
    print(f"               : 空 Enter または 'ok' → 承認して次フェーズへ")
    print(f"               : テキスト入力 → フィードバックとして再生成")
    print(f"{'═' * _W}\n")

    # ── Workflow 起動 ─────────────────────────────────────────────────────────
    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[topic, source_code],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    # ── フェーズごとのインタラクティブループ ───────────────────────────────────
    for phase in PHASES:
        phase_label = PHASE_LABELS[phase]
        attempt = 0

        while True:
            print(f"⏳ {phase_label} を生成中...")
            status = await wait_for_ready(handle)

            if status["status"] == "completed":
                break

            _print_output(
                phase_label=phase_label,
                attempt=attempt,
                output=status["current_output"] or "",
                feedback=None if attempt == 0 else None,
            )

            try:
                user_input = input(f"フィードバック (空 Enter / 'ok' で承認): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n中断されました。")
                return

            if not user_input or user_input.lower() in ("ok", "承認", "done", "yes"):
                await handle.signal("approve_step", "")
                print(f"✅ {phase_label} を承認しました。\n")
                break
            else:
                await handle.signal("approve_step", user_input)
                print(f"\n🔄 フィードバックを送信しました。{phase_label} を再生成中...\n")
                attempt += 1
                # Workflow がシグナルを処理して generating に遷移するまで少し待つ
                await asyncio.sleep(1.5)

    # ── 完了メッセージ ─────────────────────────────────────────────────────────
    _header("✅ SOP 生成完了")
    print(f"  Temporal UI  : http://localhost:8080/namespaces/default/workflows/{workflow_id}")

    # ── Evidence Log（比較ログ）を表示 ────────────────────────────────────────
    history = await handle.query("get_history")
    _print_evidence(history)


if __name__ == "__main__":
    asyncio.run(main())
