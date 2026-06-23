"""
E2E 監査スクリプト: active_agent データパス検証（改訂版）

reject_with_feedback シグナルでループバックを強制し、
_call_fix_decomposed (Writer → Reviewer) が実行される状態を作り
Hono API /api/status/:workflowId から active_agent が正確に届くか確認する。

Usage:
    python e2e_active_agent_audit.py
"""

import asyncio
import time
import uuid

import httpx
from temporalio.client import Client

from core.models import GitHubParams
from workflows.sop_workflow import sop_generation_workflow

TEMPORAL_HOST = "localhost:7233"
HONO_BASE     = "http://localhost:3000"
TASK_QUEUE    = "llm-task-queue"

TOPIC  = "E2E 監査用 SOP テスト"
SOURCE = "# test\nprint('hello')\n"


async def poll_until_status(
    http: httpx.AsyncClient,
    workflow_id: str,
    target_statuses: list[str],
    timeout: float = 300.0,
    interval: float = 3.0,
    log_prefix: str = "",
) -> dict:
    """指定ステータスに到達するまで Hono API をポーリング。"""
    deadline = time.monotonic() + timeout
    prev_status = None
    while time.monotonic() < deadline:
        try:
            r = await http.get(f"/api/status/{workflow_id}")
            data = r.json()
            st = data.get("status", "?")
            if st != prev_status:
                print(f"  {log_prefix}[status変化] → {st}  (phase={data.get('current_phase','?')})")
                prev_status = st
            if st in target_statuses:
                return data
        except Exception as e:
            print(f"  {log_prefix}[poll error] {e}")
        await asyncio.sleep(interval)
    raise TimeoutError(f"target_statuses={target_statuses} に {timeout}s 以内に到達せず")


async def watch_active_agent(
    http: httpx.AsyncClient,
    workflow_id: str,
    timeout: float = 420.0,
    interval: float = 2.0,
) -> list:
    """active_agent の変化を記録して完了まで監視。"""
    deadline = time.monotonic() + timeout
    observed: list = []
    prev_agent = "__unset__"
    prev_status = None

    while time.monotonic() < deadline:
        try:
            r = await http.get(f"/api/status/{workflow_id}")
            data = r.json()
            status = data.get("status", "?")
            active_agent = data.get("active_agent")   # Python が snake_case で返す

            if active_agent != prev_agent:
                ts = time.strftime("%H:%M:%S")
                print(f"  [{ts}] active_agent: {repr(prev_agent)} → {repr(active_agent)}  (status={status})")
                observed.append(active_agent)
                prev_agent = active_agent

            if status != prev_status:
                ts = time.strftime("%H:%M:%S")
                print(f"  [{ts}] status 変化: {prev_status} → {status}")
                prev_status = status

            if status in ("completed", "failed", "awaiting_pr_approval"):
                return observed

        except Exception as e:
            print(f"  [watch error] {e}")

        await asyncio.sleep(interval)

    return observed


async def main() -> None:
    print("=" * 64)
    print("  E2E 監査: active_agent データパス全層検証")
    print("=" * 64)

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"e2e-audit-{uuid.uuid4().hex[:8]}"
    print(f"  Workflow ID: {workflow_id}")

    # github_params を設定し require_approval=True で Phase 5 に停止点を作る
    github_params = GitHubParams(
        repository="dummy/e2e-test",
        base_branch="main",
        feature_branch=f"test/{workflow_id}",
        require_approval=True,
    )

    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[TOPIC, SOURCE, github_params],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print(f"  ワークフロー起動完了\n")

    async with httpx.AsyncClient(base_url=HONO_BASE, timeout=15) as http:

        # ── Phase 1-3 を即時承認 ─────────────────────────────────────
        for phase_name in ["outline", "draft", "review"]:
            print(f"[Phase: {phase_name}] 生成待機中...")
            await poll_until_status(
                http, workflow_id, ["awaiting_approval"],
                timeout=300, log_prefix=f"{phase_name} "
            )
            print(f"  → 承認シグナル送信")
            await handle.signal("approve_step", "")
            await asyncio.sleep(1)

        # ── Phase 4 通過後 → awaiting_pr_approval を待つ ────────────
        print(f"\n[Phase 4+5] バリデーション通過 → awaiting_pr_approval 待機中...")
        await poll_until_status(
            http, workflow_id, ["awaiting_pr_approval"],
            timeout=300, log_prefix="p4/p5 "
        )

        # ── reject_with_feedback でループバックを強制 ────────────────
        print(f"\n[reject] reject_with_feedback シグナルを送信してループバックを誘発...")
        await handle.signal("reject_with_feedback", {"comment": "E2E 監査用テスト差し戻し"})
        await asyncio.sleep(1)

        # ── Phase 4 ループバック: active_agent を監視 ────────────────
        print(f"\n[監視] Writer/Reviewer の active_agent 変化を Hono API 経由で追跡中...")
        print(f"       (ポーリング間隔 2 秒 / タイムアウト 420 秒)")
        observed = await watch_active_agent(http, workflow_id, timeout=420)

    # ── 結果サマリー ─────────────────────────────────────────────────
    has_writer   = "Writer"   in observed
    has_reviewer = "Reviewer" in observed
    ends_null    = bool(observed) and observed[-1] is None

    print("\n" + "=" * 64)
    print("  監査結果サマリー")
    print("=" * 64)
    print(f"  観測した active_agent 遷移 : {observed}")
    print(f"  Writer   点灯確認          : {'✅ YES' if has_writer   else '❌ NO'}")
    print(f"  Reviewer 点灯確認          : {'✅ YES' if has_reviewer else '❌ NO'}")
    print(f"  null 復帰確認              : {'✅ YES' if ends_null    else '❌ NO'}")

    if has_writer and has_reviewer and ends_null:
        print("\n  ✅ active_agent データパス全層正常動作を確認")
    else:
        print("\n  ⚠️  一部の遷移が未観測（ログ上部の [watch error] を参照）")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
