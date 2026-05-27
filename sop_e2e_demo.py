"""
E2E グランドデモ — sop_generation_workflow 全 Phase 一本通し実証スクリプト

以下のフローを自動実行し、各フェーズの遷移ログと最終 GitHub PR URL を出力する。

  Phase 1 (outline)      : 自動承認
  Phase 2 (draft)        : 自動承認
  Phase 3 (review)       : 1回目は「禁止用語を注入する」フィードバックを送信し
                           意図的にバリデーションエラーが発生する状態を作る。
                           2回目（禁止用語入り SOP）を承認。
  Phase 4 (autonomous_fix): バリデーション検出 → AI自己修正 → 再検証 PASS
  Phase 5 gate           : awaiting_pr_approval で一時停止 → approve_pr Signal
  Phase 5 (github_pr)    : GitHub へ force-push & PR 作成 → PR URL 返却

Usage:
    python sop_e2e_demo.py
"""

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from core.models import GitHubParams
from workflows.sop_workflow import sop_generation_workflow, PHASE_LABELS

# ─── 設定 ─────────────────────────────────────────────────────────────────────

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

TOPIC = "E2E グランドデモ — Temporal AI 自律修正ループ 統合検証 SOP"

# デモ用のソースコード（意図的にロジックが欠落しているが検証ルールには引っかからない）
# 禁止用語・TODO/TBD/仮 はバリデーション回避のため含めない
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
        # バリデーションなし — 戻り値が常に None
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

TARGET_REPO = "obataka/temporal-demo"
BASE_BRANCH = "main"
FEATURE_BRANCH = "auto-fix/sop-e2e-final"
FILE_PATH = "docs/sop-e2e-final.md"

POLL_INTERVAL = 3.0
TIMEOUT_PER_PHASE = 480.0   # フェーズ毎タイムアウト（8分）
TIMEOUT_PHASE4 = 600.0      # Phase 4 タイムアウト（10分）
TIMEOUT_GITHUB = 300.0      # Phase 5 タイムアウト（5分）

# Phase 3 で注入するフィードバック（禁止用語を仕込む）
INJECT_FEEDBACK = (
    "「現状の問題点」セクションを追加してください。"
    "以下の文章を必ず一字一句そのまま含めてください：\n"
    "「本手順書は現在確認中のため、一部の仕様は未定であり、実装は作成中の段階です。」"
)

_W = 70


# ─── 表示ヘルパー ──────────────────────────────────────────────────────────────

def _rule(char: str = "═") -> None:
    """区切り線を出力する。"""
    print(char * _W)


def _header(title: str) -> None:
    """セクションヘッダーを出力する。"""
    print(f"\n{'═' * _W}")
    print(f"  {title}")
    print("═" * _W)


def _log(tag: str, msg: str) -> None:
    """タグ付きログを出力する。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] [{tag}] {msg}")


def _ok(msg: str) -> None:
    """成功ログを出力する。"""
    _log("OK", msg)


def _info(msg: str) -> None:
    """情報ログを出力する。"""
    _log("INFO", msg)


def _warn(msg: str) -> None:
    """警告ログを出力する。"""
    _log("WARN", msg)


# ─── 環境チェック ─────────────────────────────────────────────────────────────

def _ensure_github_token() -> str:
    """
    GITHUB_TOKEN を確保して返す。未設定の場合は gh CLI から取得する。

    :returns: GitHub Personal Access Token 文字列
    :raises RuntimeError: トークン取得に失敗した場合
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        _info(f"GITHUB_TOKEN 取得済み（先頭10文字: {token[:10]}...）")
        return token

    _info("GITHUB_TOKEN 未設定 — gh CLI からトークンを取得します...")
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
        token = result.stdout.strip()
        if not token:
            raise RuntimeError("gh auth token が空でした。")
        os.environ["GITHUB_TOKEN"] = token
        _info(f"GITHUB_TOKEN を gh CLI から取得しました（先頭10文字: {token[:10]}...）")
        return token
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"gh CLI でのトークン取得に失敗: {exc.stderr.strip()}"
        ) from exc


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
    :raises TimeoutError: タイムアウト以内に目的のステータスに到達しなかった場合
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
            _warn(f"Query エラー（リトライ）: {exc}")
        if dots % 10 == 0:
            print(f"  {label}...", end="", flush=True)
        else:
            print(".", end="", flush=True)
        dots += 1
        await asyncio.sleep(POLL_INTERVAL)
    print()
    raise TimeoutError(
        f"[{label}] {timeout}s 以内に {expected_statuses} に到達しませんでした。"
    )


async def _poll_phase4_and_pr_gate(handle, timeout: float) -> dict:
    """
    Phase 4（autonomous_fix）の validating/fixing 遷移をリアルタイム表示し、
    awaiting_pr_approval または completed に達したら即座に返す。

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

            # ステータスまたは fix_attempt が変わったときだけログ出力
            if st != last_status or fix_attempt != last_fix_attempt:
                ts = datetime.now().strftime("%H:%M:%S")

                if st == "validating":
                    print(f"\n  [{ts}] [Phase 4] 検証中... (試行 #{fix_attempt + 1})")

                elif st == "fixing":
                    failures = v_result.get("failures", [])
                    score = v_result.get("score", {})
                    print(
                        f"\n  [{ts}] [Phase 4] バリデーション失敗 — "
                        f"score: chars={score.get('char_count', '?')}, "
                        f"sections={score.get('section_count', '?')}, "
                        f"code_blocks={score.get('code_block_count', '?')}"
                    )
                    for f in failures:
                        print(f"    ✗ {f}")
                    print(f"  [{ts}] [Phase 4] Gemini による AI 修正を開始...")

                elif st == "awaiting_pr_approval":
                    print(f"\n  [{ts}] [Phase 4] バリデーション PASS")
                    print(f"  [{ts}] [Phase 5 gate] 承認待ち（awaiting_pr_approval）に到達")
                    return status

                elif st == "completed":
                    print(f"\n  [{ts}] [Phase 4] 完了（PR承認なしで完走）")
                    return status

                last_status = st
                last_fix_attempt = fix_attempt

        except Exception as exc:
            _warn(f"Phase 4 Query エラー（リトライ）: {exc}")

        await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Phase 4 が {timeout}s 以内に完了しませんでした。")


# ─── メイン ───────────────────────────────────────────────────────────────────

async def main() -> None:
    """
    E2E グランドデモのエントリポイント。

    全フェーズを一本通しで自動実行し、最終的な GitHub PR URL を標準出力へ表示する。
    """
    _rule()
    print("  E2E グランドデモ — temporal-demo 全 Phase 一本通し")
    _rule()

    # ── 環境チェック ─────────────────────────────────────────────────────────
    _ensure_github_token()

    # ── Temporal 接続 ────────────────────────────────────────────────────────
    _info(f"Temporal に接続中: {TEMPORAL_HOST}")
    client = await Client.connect(TEMPORAL_HOST)

    workflow_id = f"sop-e2e-grand-demo-{uuid.uuid4().hex[:8]}"
    github_params = GitHubParams(
        repository=TARGET_REPO,
        base_branch=BASE_BRANCH,
        feature_branch=FEATURE_BRANCH,
        file_path=FILE_PATH,
        require_approval=True,
    )

    _info(f"Workflow ID  : {workflow_id}")
    _info(f"Topic        : {TOPIC}")
    _info(f"Repository   : {TARGET_REPO}")
    _info(f"PR Branch    : {FEATURE_BRANCH}")
    _info(f"Require Approval : True（approve_pr Signal 必須）")
    _info(f"Source code  : {len(DUMMY_SOURCE_CODE):,} chars（意図的バグ入りダミー）")
    print()

    started_at = time.monotonic()

    # ── ワークフロー起動 ─────────────────────────────────────────────────────
    _header("STEP 1 — ワークフロー起動")
    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[TOPIC, DUMMY_SOURCE_CODE, github_params],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    _ok(f"起動完了")
    _info(f"Temporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")

    # ── Phase 1: outline ─────────────────────────────────────────────────────
    _header(f"STEP 2 — {PHASE_LABELS['outline']} (自動承認)")
    await _poll_until(
        handle,
        expected_statuses=("awaiting_approval", "completed"),
        timeout=TIMEOUT_PER_PHASE,
        label="outline 生成中",
    )
    _ok("outline 生成完了 → 自動承認（空フィードバック）")
    await handle.signal("approve_step", "")
    await asyncio.sleep(2.0)

    # ── Phase 2: draft ───────────────────────────────────────────────────────
    _header(f"STEP 3 — {PHASE_LABELS['draft']} (自動承認)")
    await _poll_until(
        handle,
        expected_statuses=("awaiting_approval", "completed"),
        timeout=TIMEOUT_PER_PHASE,
        label="draft 生成中（長くなります）",
    )
    _ok("draft 生成完了 → 自動承認（空フィードバック）")
    await handle.signal("approve_step", "")
    await asyncio.sleep(2.0)

    # ── Phase 3: review (1回目: 禁止用語注入) ───────────────────────────────
    _header(f"STEP 4 — {PHASE_LABELS['review']} (禁止用語注入 → 2回目承認)")
    await _poll_until(
        handle,
        expected_statuses=("awaiting_approval", "completed"),
        timeout=TIMEOUT_PER_PHASE,
        label="review 1回目生成中",
    )
    _info("review 1回目生成完了")
    _info(f"フィードバック送信: 禁止用語（確認中・未定・作成中）を埋め込む")
    print(f"    Signal: approve_step(feedback='{INJECT_FEEDBACK[:60]}...')")
    await handle.signal("approve_step", INJECT_FEEDBACK)
    await asyncio.sleep(2.0)

    # Phase 3 の 2 回目（禁止用語入り SOP）を承認
    await _poll_until(
        handle,
        expected_statuses=("awaiting_approval", "completed"),
        timeout=TIMEOUT_PER_PHASE,
        label="review 2回目生成中（禁止用語入り）",
    )
    _ok("review 2回目生成完了 — 禁止用語を含む SOP を承認します（意図的）")
    _info("Phase 4 のバリデーションがこれを検出します")
    await handle.signal("approve_step", "")

    # ── Phase 4: autonomous_fix ──────────────────────────────────────────────
    _header("STEP 5 — Phase 4: 自律修正ループ（検証 → AI修正 → 再検証）")
    await asyncio.sleep(3.0)
    phase4_status = await _poll_phase4_and_pr_gate(handle, timeout=TIMEOUT_PHASE4)

    if phase4_status["status"] == "completed":
        # PR 承認なしで完走した（require_approval=False だった場合等）
        _warn("ワークフローが PR 承認ゲートをスキップして完了しました。")
        final = phase4_status
    else:
        # ── Phase 5 gate: awaiting_pr_approval ───────────────────────────────
        _header("STEP 6 — Phase 5 gate: 人間承認 Signal 送信")
        _info("ワークフローは await_condition で一時停止中（awaiting_pr_approval）")
        _info("approve_pr Signal を送信して PR 作成を解放します...")
        await asyncio.sleep(1.0)
        await handle.signal("approve_pr")
        _ok("approve_pr Signal 送信完了")

        # ── Phase 5: GitHub PR 作成 ───────────────────────────────────────────
        _header("STEP 7 — Phase 5: GitHub PR 作成")
        _info("GitHubActivity.create_pull_request 実行中...")
        _info(f"  force-push → {FEATURE_BRANCH}")
        _info(f"  gh pr create / 既存PRチェック")
        final = await _poll_until(
            handle,
            expected_statuses=("completed",),
            timeout=TIMEOUT_GITHUB,
            label="PR 作成中",
        )

    elapsed = time.monotonic() - started_at

    # ── 最終結果 ─────────────────────────────────────────────────────────────
    pr_url = final.get("pr_url")
    if not pr_url:
        # Query の pr_url が None の場合は result() から取得
        try:
            wf_result = await handle.result()
            pr_url = wf_result.get("pr_url") if isinstance(wf_result, dict) else None
        except Exception as exc:
            _warn(f"Workflow result() 取得失敗: {exc}")

    history = await handle.query("get_history")
    total_tokens = sum(e.get("tokens", 0) for e in history)
    fix_attempts = sum(1 for e in history if e.get("phase") == "autonomous_fix")

    print()
    _rule()
    print("  E2E グランドデモ — 完了")
    _rule()
    print()
    if pr_url:
        print(f"  GitHub PR URL : {pr_url}")
    else:
        print(f"  PR URL        : (取得できませんでした — Temporal UI で確認してください)")

    print(f"  Workflow ID   : {workflow_id}")
    print(f"  総所要時間    : {elapsed / 60:.1f} 分 ({elapsed:.0f}s)")
    print(f"  総トークン消費: {total_tokens:,}")
    print(f"  Phase 4 試行回数: {fix_attempts} 回")
    print()
    print(f"  Temporal UI   : http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    _rule()

    # フェーズ別サマリー
    print()
    print("  フェーズ別サマリー")
    print(f"  {'─' * 50}")
    phase_map: dict[str, list] = {}
    for entry in history:
        phase_map.setdefault(entry["phase"], []).append(entry)

    phase_order = ["outline", "draft", "review", "autonomous_fix"]
    labels = PHASE_LABELS
    for p in phase_order:
        entries = phase_map.get(p, [])
        if not entries:
            continue
        total_t = sum(e.get("tokens", 0) for e in entries)
        approved_count = sum(1 for e in entries if e.get("approved"))
        failures_all = [f for e in entries for f in (e.get("failures") or [])]
        label = labels.get(p, p)
        print(f"  {label}")
        print(f"    試行数: {len(entries)}  承認: {approved_count}  トークン: {total_t:,}")
        if failures_all:
            print(f"    検出エラー:")
            for f in sorted(set(failures_all)):
                print(f"      - {f}")
        print()

    _rule()


if __name__ == "__main__":
    asyncio.run(main())
