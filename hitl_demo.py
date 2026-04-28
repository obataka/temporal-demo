"""
Human-in-the-Loop デモ — インタラクティブなフィードバックループ。

Usage:
    python hitl_demo.py "Temporalとは何か説明してください"
    python hitl_demo.py  # デフォルトタスク使用

フロー:
    1. Gemini が初回回答を生成
    2. 修正指示を入力 → Signal で送信 → 再生成
    3. 空 Enter または "ok" で承認 → 比較ログを表示
"""

import asyncio
import os
import sys
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from workflows.hitl_agent_workflow import hitl_agent_workflow

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

DEFAULT_TASK = (
    "Temporal というワークフローエンジンの主な特徴を説明してください。"
)

_SEP = "─" * 62


def _print_answer(attempt: int, answer: str, feedback: str | None = None) -> None:
    tag = "初期回答" if attempt == 0 else f"改善版 #{attempt}"
    print(f"\n{'='*62}")
    print(f"  試行 #{attempt} — {tag}")
    if feedback:
        print(f"  フィードバック: 「{feedback}」")
    print(f"{'='*62}")
    print(answer.strip())
    print()


def _print_comparison(history: list[dict]) -> None:
    print("\n" + "=" * 62)
    print("  改善比較ログ（全試行）")
    print("=" * 62)
    for entry in history:
        a = entry["attempt"]
        fb = entry.get("feedback")
        ans = entry["answer"].strip()
        tokens = entry.get("tokens", 0)
        latency = entry.get("latency_ms", 0)
        label = "初期回答" if a == 0 else f"フィードバック反映 #{a}"
        print(f"\n【試行 #{a} — {label}】  tokens={tokens}  latency={latency:.0f}ms")
        if fb:
            print(f"  └ フィードバック: 「{fb}」")
        print(_SEP)
        # 長すぎる場合は先頭200文字
        print(ans[:400] + ("..." if len(ans) > 400 else ""))
    print("\n" + "=" * 62)
    total = len(history)
    print(f"  合計試行: {total}  |  改善回数: {total - 1}  |  承認: ✅")
    print("=" * 62 + "\n")


async def wait_for_status(handle, target: str, timeout: float = 90.0) -> dict:
    """指定した status になるまでポーリングで待つ。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = await handle.query("get_status")
            if status["status"] in (target, "approved", "error"):
                return status
        except Exception:
            pass
        await asyncio.sleep(1.5)
    raise TimeoutError(f"Workflow が {timeout}s 以内に '{target}' にならなかった。")


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    task = args[0] if args else DEFAULT_TASK

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"hitl-{uuid.uuid4().hex[:8]}"

    print(f"\n{'='*62}")
    print("  Human-in-the-Loop AI Agent")
    print(f"{'='*62}")
    print(f"  Workflow ID : {workflow_id}")
    print(f"  Task        : {task}")
    print(f"  操作方法    : 修正指示を入力 → Enter で送信")
    print(f"              : 空 Enter または 'ok' で承認・終了")
    print(f"{'='*62}\n")

    # Workflow 起動
    handle = await client.start_workflow(
        hitl_agent_workflow.run,
        task,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    print("Gemini が回答を生成中...")
    status = await wait_for_status(handle, "awaiting_feedback")
    _print_answer(0, status["current_answer"])

    # フィードバックループ
    while True:
        try:
            user_input = input("フィードバック (空 Enter / 'ok' で承認): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n中断されました。")
            break

        if not user_input or user_input.lower() in ("ok", "承認", "done", "yes"):
            await handle.signal("approve")
            print("\n✅ 承認 Signal を送信しました。")
            break

        # フィードバック Signal を送信
        await handle.signal("provide_feedback", user_input)
        retry_count = status["retry_count"] + 1
        print(f"\nフィードバックを送信しました。Gemini が再生成中... (試行 #{retry_count})")

        status = await wait_for_status(handle, "awaiting_feedback")
        _print_answer(
            status["retry_count"],
            status["current_answer"],
            feedback=status["last_feedback"],
        )

    # 完了 → 比較ログ出力
    history = await handle.query("get_history")
    _print_comparison(history)

    print(f"Temporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")


if __name__ == "__main__":
    asyncio.run(main())
