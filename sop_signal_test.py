"""
approve_pr Signal 実戦疎通テスト — Human-in-the-Loop ガバナンスの end-to-end 検証

require_approval=True でワークフローを起動し、Phase 5 PR 作成前に
ワークフローが awaiting_pr_approval で停止することを確認した後、
approve_pr Signal を送信して PR 作成まで完走することを検証する。

実行手順:
    1. Docker Worker が起動済みであること:
           docker compose ps

    2. このスクリプトを実行（ホストマシンから）:
           python sop_signal_test.py

注意:
    - GITHUB_TOKEN は .env または環境変数から Docker Worker コンテナへ渡される
    - gh CLI と git は Dockerfile でインストール済み
"""

import asyncio
import os
import subprocess
import sys
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from core.models import GitHubParams
from workflows.sop_workflow import sop_generation_workflow, PHASE_LABELS

# ─── 設定 ─────────────────────────────────────────────────────────────────────

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

TARGET_REPO = "obataka/temporal-demo"
BASE_BRANCH = "main"
FEATURE_BRANCH = "auto-fix/sop-signal-test"
FILE_PATH = "docs/sop-signal-test.md"

TOPIC = "approve_pr Signal 疎通テスト用SOP（Temporal Human-in-the-Loop 検証）"
SOURCE_FILE = "activities/github_activity.py"

POLL_INTERVAL = 3.0    # ポーリング間隔（秒）
TIMEOUT = 900.0         # 全体タイムアウト（15分）

# ─── ユーティリティ ────────────────────────────────────────────────────────────


def _ensure_github_token() -> None:
    """
    GITHUB_TOKEN を環境変数に設定する。未設定の場合は gh CLI から取得する。

    :raises RuntimeError: gh CLI でのトークン取得にも失敗した場合
    """
    if os.environ.get("GITHUB_TOKEN"):
        print("[INFO] GITHUB_TOKEN は環境変数から取得済み")
        return

    print("[INFO] GITHUB_TOKEN 未設定 — gh CLI からトークンを取得します...")
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
        token = result.stdout.strip()
        if not token:
            raise RuntimeError("gh auth token が空でした。")
        os.environ["GITHUB_TOKEN"] = token
        print("[INFO] GITHUB_TOKEN を gh CLI から取得しました（先頭10文字: "
              f"{token[:10]}...）")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"gh CLI でのトークン取得に失敗しました: {exc.stderr.strip()}"
        ) from exc


def _load_source_code() -> str:
    """
    疎通テスト用のソースコードを読み込む。

    :returns: GitHub Activity のソースコード文字列
    :raises SystemExit: ファイルが見つからない場合
    """
    try:
        with open(SOURCE_FILE, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"[ERROR] ソースファイルが見つかりません: {SOURCE_FILE}")
        sys.exit(1)


async def _poll_until_ready(
    handle,
    expected_statuses: tuple[str, ...],
    timeout: float,
) -> dict:
    """
    指定ステータスのいずれかになるまでポーリングする。

    :param handle: Temporal WorkflowHandle
    :param expected_statuses: 待機対象のステータス文字列のタプル
    :param timeout: タイムアウト秒数
    :returns: get_status() の結果辞書
    :raises TimeoutError: タイムアウト以内に目的のステータスに到達しなかった場合
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = await handle.query("get_status")
            phase = status.get("current_phase", "?")
            st = status.get("status", "?")
            print(f"    [ポーリング] phase={phase}, status={st}")
            if st in expected_statuses:
                return status
        except Exception as exc:
            print(f"    [ポーリング] Query エラー（リトライします）: {exc}")
        await asyncio.sleep(POLL_INTERVAL)
    raise TimeoutError(
        f"{timeout}s 以内に {expected_statuses} に到達しませんでした。"
    )


# ─── メイン ───────────────────────────────────────────────────────────────────


async def main() -> None:
    """
    approve_pr Signal 実戦疎通テストのエントリポイント。

    Phase 1-3 を自動承認し、Phase 5 前に awaiting_pr_approval で停止することを確認後、
    approve_pr Signal を送信して PR 作成まで完走することを検証する。
    """
    print("=" * 60)
    print("  approve_pr Signal 実戦疎通テスト")
    print("=" * 60)

    # GITHUB_TOKEN を確保
    _ensure_github_token()

    # ソースコード読み込み
    source_code = _load_source_code()
    print(f"[INFO] ソースコード読み込み完了: {SOURCE_FILE} ({len(source_code)} chars)")

    # Temporal 接続
    print(f"[INFO] Temporal に接続中: {TEMPORAL_HOST}")
    client = await Client.connect(TEMPORAL_HOST)

    workflow_id = f"sop-signal-test-{uuid.uuid4().hex[:8]}"
    github_params = GitHubParams(
        repository=TARGET_REPO,
        base_branch=BASE_BRANCH,
        feature_branch=FEATURE_BRANCH,
        file_path=FILE_PATH,
        require_approval=True,
    )

    print(f"[INFO] Workflow ID      : {workflow_id}")
    print(f"[INFO] Topic            : {TOPIC}")
    print(f"[INFO] Repository       : {TARGET_REPO}")
    print(f"[INFO] PR Branch        : {FEATURE_BRANCH}")
    print(f"[INFO] File Path        : {FILE_PATH}")
    print(f"[INFO] require_approval : {github_params.require_approval}")
    print()

    # Workflow 起動
    print("[STEP] ワークフローを起動します...")
    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[TOPIC, source_code, github_params],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print(f"[INFO] 起動完了 → Temporal UI: "
          f"http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    print()

    # Phase 1〜3: 自動承認ループ
    for phase in ("outline", "draft", "review"):
        phase_label = PHASE_LABELS[phase]
        print(f"[STEP] {phase_label} を待機中...")

        status = await _poll_until_ready(
            handle,
            expected_statuses=("awaiting_approval", "awaiting_pr_approval", "completed"),
            timeout=TIMEOUT,
        )

        if status["status"] in ("awaiting_pr_approval", "completed"):
            print(f"[WARN] Phase 1-3 中に予期しないステータス: {status['status']}")
            break

        print(f"[AUTO] {phase_label} を自動承認します（空文字 Signal 送信）")
        await handle.signal("approve_step", "")
        print(f"[OK]   {phase_label} 承認完了\n")

        # Worker がシグナルを消化して generating に遷移するまで待機
        await asyncio.sleep(2.0)

    # Phase 4（autonomous_fix）完了後、awaiting_pr_approval 待ち
    print("[STEP] Phase 4（自律修正）完了 → awaiting_pr_approval を待機中...")
    paused_status = await _poll_until_ready(
        handle,
        expected_statuses=("awaiting_pr_approval",),
        timeout=TIMEOUT,
    )

    # ポーズ状態を確認して表示
    print()
    print("=" * 60)
    print("  [PAUSED] ワークフローが PR 承認待ちで一時停止中")
    print("=" * 60)
    print(f"  status      = {paused_status.get('status')}")
    print(f"  pr_approved = {paused_status.get('pr_approved')}")
    print(f"  phase       = {paused_status.get('current_phase')}")
    print()

    # approve_pr Signal 送信（ユーザー承認待ち）
    input("\n[INPUT] PR 作成を承認する場合は Enter を押してください（Ctrl+C で中断）...")
    await handle.signal("approve_pr")
    print("[OK]     approve_pr Signal を送信しました\n")

    # Phase 5（GitHub PR 作成）完了待ち
    print("[STEP] Phase 5（GitHub PR 作成）を待機中...")
    final_status = await _poll_until_ready(
        handle,
        expected_statuses=("completed",),
        timeout=TIMEOUT,
    )

    pr_url = final_status.get("pr_url")

    print()
    print("=" * 60)
    print("  テスト完了")
    print("=" * 60)

    if pr_url:
        print(f"[SUCCESS] PR URL: {pr_url}")
    else:
        # Workflow の戻り値から pr_url を取得
        result = await handle.result()
        pr_url = result.get("pr_url") if isinstance(result, dict) else None
        if pr_url:
            print(f"[SUCCESS] PR URL: {pr_url}")
        else:
            print("[WARN] PR URL が取得できませんでした。Temporal UI で確認してください。")

    print(f"[INFO] Temporal UI: "
          f"http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
