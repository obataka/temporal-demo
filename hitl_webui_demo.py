"""
Web UI 画面承認デモ — Human-in-the-Loop ライブデモ

Phase 1–3 を自動承認し、Phase 5 承認ゲートで停止。
ブラウザから http://localhost:3000 で承認ボタンを押すと
シグナルを受信して GitHub PR 作成まで自動完走する。

Usage:
    python hitl_webui_demo.py
"""

import asyncio
import os
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from core.models import GitHubParams
from workflows.sop_workflow import sop_generation_workflow, PHASE_LABELS

# ─── 設定 ─────────────────────────────────────────────────────────────────────

TEMPORAL_HOST   = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE      = "llm-task-queue"

TARGET_REPO     = "obataka/temporal-demo"
BASE_BRANCH     = "main"
FEATURE_BRANCH  = "auto-fix/hitl-webui-demo"
FILE_PATH       = "docs/sop-hitl-webui-demo.md"

TOPIC = "Web UI 画面承認デモ用 SOP（Temporal × Hono HITL 統合検証）"

DUMMY_SOURCE_CODE = '''\
"""
E2E デモ用ダミーモジュール — ロジックが欠落した不完全実装

このモジュールは E2E グランドデモの入力ソースコードとして使用する。
バリデーションロジックや戻り値が実装されておらず、実際には動作しない。
"""

import logging

logger = logging.getLogger(__name__)


class DataProcessor:
    """データ変換・検証を担うクラス。"""

    def process(self, data: dict) -> dict | None:
        """
        入力データを処理して結果を返す。

        :param data: 処理対象の辞書
        :returns: 処理済みデータ、または None
        """
        result = None
        logger.debug("process called with %s", data)
        return result

    def validate(self, item: object) -> bool:
        """
        アイテムの妥当性を検証する。

        :param item: 検証対象オブジェクト
        :returns: 常に False（未実装）
        """
        return False


def run_pipeline(inputs: list) -> None:
    """
    入力リストに対してパイプラインを実行する。

    :param inputs: 処理対象データのリスト
    """
    processor = DataProcessor()
    for inp in inputs:
        result = processor.process(inp)
        if result is None:
            logger.warning("Skipping invalid input: %s", inp)
'''

POLL_INTERVAL      = 3.0
TIMEOUT_PER_PHASE  = 480.0
TIMEOUT_PHASE4     = 600.0
TIMEOUT_GITHUB     = 300.0
TIMEOUT_HUMAN      = 600.0   # 人間承認待ちタイムアウト: 10 分

_W = 60


# ─── 表示ヘルパー ──────────────────────────────────────────────────────────────

def _rule(char: str = "═") -> None:
    """区切り線を出力する。"""
    print(char * _W)


def _log(tag: str, msg: str) -> None:
    """タグ付きログを出力する。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] [{tag}] {msg}")


# ─── ポーリングユーティリティ ─────────────────────────────────────────────────

async def _poll_until(
    handle,
    expected_statuses: tuple[str, ...],
    timeout: float,
    label: str = "待機中",
) -> dict:
    """
    指定ステータスのいずれかになるまでポーリングする。

    :param handle: Temporal WorkflowHandle
    :param expected_statuses: 待機対象のステータス文字列のタプル
    :param timeout: タイムアウト秒数
    :param label: ログに表示するラベル
    :returns: get_status() の結果辞書
    :raises TimeoutError: タイムアウト以内に到達しなかった場合
    """
    deadline = time.monotonic() + timeout
    dots = 0
    while time.monotonic() < deadline:
        try:
            status = await handle.query("get_status")
            if status["status"] in expected_statuses:
                if dots:
                    print()
                return status
        except Exception as exc:
            _log("WARN", f"Query エラー（リトライ）: {exc}")
        if dots % 10 == 0:
            print(f"  {label}...", end="", flush=True)
        else:
            print(".", end="", flush=True)
        dots += 1
        await asyncio.sleep(POLL_INTERVAL)
    print()
    raise TimeoutError(f"[{label}] {timeout}s 以内に {expected_statuses} に到達しませんでした。")


async def _poll_phase4(handle, timeout: float) -> dict:
    """
    Phase 4（autonomous_fix）の進捗をリアルタイム表示し、
    awaiting_pr_approval に達したら返す。

    :param handle: Temporal WorkflowHandle
    :param timeout: タイムアウト秒数
    :returns: awaiting_pr_approval 時の get_status() 結果
    :raises TimeoutError: タイムアウト超過時
    """
    last_status = None
    last_fix_attempt = -1
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            status = await handle.query("get_status")
            st = status["status"]
            fix_attempt = status.get("fix_attempt", 0)
            v_result = status.get("validation_result") or {}

            if st != last_status or fix_attempt != last_fix_attempt:
                ts = datetime.now().strftime("%H:%M:%S")
                if st == "validating":
                    print(f"\n  [{ts}] [Phase 4] 検証中... (試行 #{fix_attempt + 1})")
                elif st == "fixing":
                    failures = v_result.get("failures", [])
                    print(f"\n  [{ts}] [Phase 4] バリデーション失敗 → AI 修正中")
                    for f in failures:
                        print(f"    ✗ {f}")
                elif st == "awaiting_pr_approval":
                    print(f"\n  [{ts}] [Phase 4] バリデーション PASS ✓")
                    return status
                elif st == "completed":
                    return status
                last_status = st
                last_fix_attempt = fix_attempt
        except Exception as exc:
            _log("WARN", f"Phase 4 Query エラー: {exc}")

        await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Phase 4 が {timeout}s 以内に完了しませんでした。")


async def _wait_for_human_action(
    handle,
    workflow_id: str,
    round_num: int = 1,
) -> str:
    """
    ユーザーがブラウザから approve_pr または reject_with_feedback を送信するまで待機する。

    :param handle: Temporal WorkflowHandle
    :param workflow_id: ワークフロー ID（案内メッセージ表示用）
    :param round_num: ループバック回数（案内メッセージ表示用）
    :returns: "approved" または "rejected"
    :raises TimeoutError: TIMEOUT_HUMAN 秒以内にシグナルが来なかった場合
    """
    round_label = f"（ラウンド {round_num}）" if round_num > 1 else ""
    print()
    _rule()
    print(f"  [Phase 5 GATE] 人間承認待ち{round_label}")
    _rule()
    print()
    print(f"  Workflow ID : {workflow_id}")
    print()
    print("  ■ ブラウザで以下を開いてください:")
    print("      http://localhost:3000")
    print()
    print("  ■ ドロップダウンから上記 ID を選択し、")
    print('  ■「GitHub PR 作成を承認する」または「修正を指示して差し戻す」を選んでください。')
    print()
    print("  操作すると自動的に処理が再開されます。")
    _rule()
    print("  待機中", end="", flush=True)

    deadline = time.monotonic() + TIMEOUT_HUMAN
    while time.monotonic() < deadline:
        await asyncio.sleep(5.0)
        try:
            status = await handle.query("get_status")
            current = status["status"]
            if current != "awaiting_pr_approval":
                print()
                ts = datetime.now().strftime("%H:%M:%S")
                print()
                # 差し戻し → Phase 4 が再走中
                if current in ("fixing", "validating", "autonomous_fix"):
                    _log("SIGNAL", f"✓ reject_with_feedback シグナルを受信しました（{ts}）")
                    return "rejected"
                # 承認 → PR 作成フェーズへ
                _log("SIGNAL", f"✓ approve_pr シグナルを受信しました（{ts}）")
                return "approved"
            print(".", end="", flush=True)
        except Exception as exc:
            _log("WARN", f"Query エラー: {exc}")

    print()
    raise TimeoutError(f"人間承認シグナルが {TIMEOUT_HUMAN}s 以内に届きませんでした。")


# ─── メイン ───────────────────────────────────────────────────────────────────

async def main() -> None:
    """
    HITL Web UI デモのエントリポイント。
    Phase A（自動）→ Phase B（人間待機）→ Phase C（自動完走）を実行する。
    """
    started_at = time.monotonic()

    _rule()
    print("  Web UI 画面承認デモ（HITL）")
    print("  Temporal × Hono — Human-in-the-Loop ライブデモ")
    _rule()
    print()

    _log("INFO", f"Temporal に接続中: {TEMPORAL_HOST}")
    client = await Client.connect(TEMPORAL_HOST)

    workflow_id = f"sop-hitl-demo-{uuid.uuid4().hex[:8]}"
    github_params = GitHubParams(
        repository=TARGET_REPO,
        base_branch=BASE_BRANCH,
        feature_branch=FEATURE_BRANCH,
        file_path=FILE_PATH,
        require_approval=True,
    )

    _log("INFO", f"Workflow ID : {workflow_id}")
    _log("INFO", f"Topic       : {TOPIC}")
    print()

    # ── フェーズ A: ワークフロー起動 ──────────────────────────────────────────
    _log("DEMO", "ワークフロー起動中...")
    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[TOPIC, DUMMY_SOURCE_CODE, github_params],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    _log("OK", f"起動完了 → Temporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    print()

    # ── フェーズ A: Phase 1–3 自動承認 ────────────────────────────────────────
    for phase in ("outline", "draft", "review"):
        label = PHASE_LABELS[phase]
        _log("AUTO", f"{label} を自動承認します")
        await _poll_until(
            handle,
            expected_statuses=("awaiting_approval", "completed"),
            timeout=TIMEOUT_PER_PHASE,
            label=f"  {label} 生成中",
        )
        _log("OK", f"{label} 生成完了 → 承認シグナル送信")
        await handle.signal("approve_step", "")
        await asyncio.sleep(2.0)

    # ── フェーズ A: Phase 4 自律修正 ──────────────────────────────────────────
    print()
    _log("AUTO", "Phase 4（自律修正ループ）を待機中...")
    await asyncio.sleep(3.0)
    await _poll_phase4(handle, timeout=TIMEOUT_PHASE4)

    # ── フェーズ B〜C: 人間承認 / ループバック対話ループ ────────────────────
    round_num = 0
    while True:
        round_num += 1
        action = await _wait_for_human_action(handle, workflow_id, round_num)

        if action == "approved":
            # ── フェーズ C: GitHub PR 作成 ────────────────────────────────
            print()
            _log("Phase 5", "GitHub PR 作成中...")
            break
        else:
            # ── 差し戻し → Phase 4 再実行待ち ────────────────────────────
            print()
            _log("LOOP", f"差し戻し受信 → Phase 4 再修正ループ実行中... (ラウンド {round_num})")
            await _poll_phase4(handle, timeout=TIMEOUT_PHASE4)
            _log("OK", f"Phase 4 再修正完了 → 再び承認待ち (ラウンド {round_num})")

    final = await _poll_until(
        handle,
        expected_statuses=("completed",),
        timeout=TIMEOUT_GITHUB,
        label="  PR 作成中",
    )

    pr_url = final.get("pr_url")
    if not pr_url:
        try:
            wf_result = await handle.result()
            pr_url = wf_result.get("pr_url") if isinstance(wf_result, dict) else None
        except Exception as exc:
            _log("WARN", f"Workflow result() 取得失敗: {exc}")

    elapsed = time.monotonic() - started_at

    print()
    _rule()
    print("  [DONE] デモ完了")
    _rule()
    print()
    if pr_url:
        print(f"  GitHub PR URL : {pr_url}")
    else:
        print("  PR URL        : (Temporal UI で確認してください)")
    print(f"  Workflow ID   : {workflow_id}")
    print(f"  総所要時間    : {elapsed / 60:.1f} 分 ({elapsed:.0f}s)")
    print(f"  Temporal UI   : http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    _rule()


if __name__ == "__main__":
    asyncio.run(main())
