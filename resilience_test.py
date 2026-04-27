"""
Resilience Test — Signal 注入 → クラッシュ → 復旧後に指示が保持されることを自動検証。

ステップ:
  1. Worker をサブプロセスで起動
  2. immortal_agent_workflow を開始（タスク3件、モックモード、5秒インターバル）
  3. inject_human_feedback / update_task_priority シグナルを送信
  4. Query でシグナル受信を確認
  5. Worker を強制終了（クラッシュシミュレーション）
  6. Worker を再起動（自動復旧）
  7. Query で「変更された指示」が保持されていることを検証
  8. stop_agent シグナルで終了

Usage:
    python resilience_test.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from workflows.immortal_agent_workflow import immortal_agent_workflow

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
# Docker worker との競合を避けるため専用キューを使う
TASK_QUEUE = "resilience-demo-queue"

INITIAL_TASKS: list[str] = []  # 空スタートにすることでクラッシュ前はアイドル状態を保証する

INJECTED_FEEDBACK = "重要指示: 必ず「Temporal は最高です！」という一文で締めくくること。"
INJECTED_PRIORITY = 9


def _sep(title: str = "") -> None:
    if title:
        print(f"\n{'='*20} {title} {'='*20}")
    else:
        print("=" * 60)


async def query_and_print(handle, label: str) -> dict:
    print(f"\n--- Query: {label} ---")
    try:
        status = await handle.query("get_status")
        stats = await handle.query("get_live_stats")
        print(f"  status           : {status['status']}")
        print(f"  current_task     : {status['current_task']}")
        print(f"  queue_size       : {status['queue_size']}")
        print(f"  priority         : {status['priority']}")
        print(f"  feedback_pending : {status['human_feedback_pending']}")
        print(f"  tasks_completed  : {stats['tasks_completed']}")
        print(f"  total_tokens     : {stats['total_tokens']}")
        return {"status": status, "stats": stats}
    except Exception as e:
        print(f"  [Query failed: {e}]")
        return {}


def start_worker() -> subprocess.Popen:
    env = os.environ.copy()
    # この Worker だけ専用キューを使う（Docker worker との競合を避ける）
    env["RESILIENCE_TASK_QUEUE"] = TASK_QUEUE
    proc = subprocess.Popen(
        [sys.executable, "-m", "resilience_worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    print(f"  Worker PID: {proc.pid}")
    return proc


async def wait_for_worker(client: Client, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # 軽量な疎通確認として名前空間を取得
            await asyncio.wait_for(client.service_client.workflow_service.get_system_info(None), timeout=2.0)
            return True
        except Exception:
            await asyncio.sleep(1.0)
    return False


async def main() -> None:
    _sep("Resilience Test: Signal & Crash Recovery")
    print("Temporal のイベントソーシングにより、クラッシュ後も Signal の効果が保持されることを検証します。\n")

    # ── Step 1: Worker 起動 ──────────────────────────────────────────────────
    _sep("Step 1: Worker を起動")
    worker_proc = start_worker()
    print("  Worker の起動を待機中...")
    await asyncio.sleep(4)

    client = await Client.connect(TEMPORAL_HOST)

    # ── Step 2: Workflow 開始 ────────────────────────────────────────────────
    _sep("Step 2: immortal_agent_workflow を開始（モックモード、インターバル5秒）")
    workflow_id = f"resilience-test-{uuid.uuid4().hex[:8]}"
    print(f"  Workflow ID: {workflow_id}")

    handle = await client.start_workflow(
        immortal_agent_workflow.run,
        args=[INITIAL_TASKS, True, 0.0],  # initial_tasks=[], use_mock=True, interval=0
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print("  Workflow 開始完了。タスクなしでアイドル待機中...")
    await asyncio.sleep(2)

    # ── Step 3: Query (ベースライン) ─────────────────────────────────────────
    _sep("Step 3: Signal 送信前の状態を確認")
    await query_and_print(handle, "before signal")

    # ── Step 4: Signal 送信 ──────────────────────────────────────────────────
    _sep("Step 4: Signal を送信")
    print(f"  inject_human_feedback: {INJECTED_FEEDBACK!r}")
    await handle.signal("inject_human_feedback", INJECTED_FEEDBACK)

    print(f"  update_task_priority: {INJECTED_PRIORITY}")
    await handle.signal("update_task_priority", INJECTED_PRIORITY)

    await asyncio.sleep(0.5)

    # ── Step 5: Query (Signal 受信確認) ──────────────────────────────────────
    _sep("Step 5: Signal 受信を確認")
    before = await query_and_print(handle, "after signal")
    assert before.get("status", {}).get("human_feedback_pending") is True, \
        "❌ フィードバックが設定されていません！"
    assert before.get("status", {}).get("priority") == INJECTED_PRIORITY, \
        "❌ 優先度が更新されていません！"
    print("\n  ✅ Signal 受信確認: feedback_pending=True, priority=9")

    # ── Step 6: Worker クラッシュ ─────────────────────────────────────────────
    _sep("Step 6: Worker を強制終了（クラッシュシミュレーション）")
    worker_proc.kill()
    worker_proc.wait()
    print(f"  💥 Worker (PID={worker_proc.pid}) を強制終了しました。")
    print("  ※ 通常であれば、ここで全ての状態が消えるはずですが…")
    await asyncio.sleep(3)

    # ── Step 7: Worker 再起動 ─────────────────────────────────────────────────
    _sep("Step 7: Worker を再起動（自動復旧）")
    worker_proc = start_worker()
    print("  Worker の再起動を待機中...")
    await asyncio.sleep(4)

    # ── Step 8: Query (復旧後の状態確認) ──────────────────────────────────────
    _sep("Step 8: 復旧後の状態を確認 — Signal の効果は残っているか？")
    after = await query_and_print(handle, "after crash recovery")

    feedback_ok = after.get("status", {}).get("human_feedback_pending") is True
    priority_ok = after.get("status", {}).get("priority") == INJECTED_PRIORITY

    print()
    if feedback_ok and priority_ok:
        print("  ✅ PASS: クラッシュ後もすべての Signal が保持されていました！")
        print(f"     feedback_pending = True  (期待値: True)")
        print(f"     priority         = {after['status']['priority']}  (期待値: {INJECTED_PRIORITY})")
        print()
        print("  理由: Temporal はすべての Signal をイベント履歴に永続記録する。")
        print("        Worker 再起動時に履歴を決定論的に再生することで、Signal の効果が復元される。")
        print("        これが 'イベントソーシングによる耐障害性' の本質だ。")
    elif not priority_ok:
        print("  ❌ FAIL: 優先度が失われました。")
        print(f"     priority = {after.get('status', {}).get('priority')} (期待値: {INJECTED_PRIORITY})")
    else:
        # feedback が既に消費された場合（タスクが処理された）
        completed = after.get("stats", {}).get("tasks_completed", 0)
        if completed > 0:
            print("  ✅ PASS (変形): フィードバックはクラッシュ後の復旧タスク処理で消費されました。")
            print(f"     priority = {after.get('status', {}).get('priority')} (保持 ✅)")
            print(f"     feedback は {completed} 件目のタスクに適用済み (消費 ✅)")
        else:
            print("  ❌ FAIL: フィードバックが予期せず失われました。")
            print(f"     feedback_pending = False (期待値: True)")
            print(f"     tasks_completed  = {completed}")

    # ── Step 9: フィードバックが実際に消費されるか確認 ───────────────────────
    _sep("Step 9: フィードバックが次のタスクに適用されることを確認")
    print("  add_task シグナルを送信中...")
    await handle.signal("add_task", "フィードバックが適用されるか確認するタスクです。")
    await asyncio.sleep(6)  # タスク処理を待つ

    final = await query_and_print(handle, "after feedback consumed")
    feedback_consumed = not final.get("status", {}).get("human_feedback_pending", True)
    if feedback_consumed:
        print("\n  ✅ フィードバックがタスクに適用されて消費されました（one-shot）。")
    else:
        print("\n  ⏳ フィードバックはまだ保留中です（タスクが処理されていない可能性）。")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    _sep("Cleanup: エージェントを停止")
    await handle.signal("stop_agent")
    print("  stop_agent シグナルを送信しました。")
    await asyncio.sleep(2)

    worker_proc.kill()
    worker_proc.wait()
    print(f"  Worker (PID={worker_proc.pid}) を停止しました。")

    _sep("テスト完了")
    print(f"  Temporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
