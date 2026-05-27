"""
Web UI 結合動作確認テスト

新設した Hono API（GET /api/status / POST /api/approve）が
sop_generation_workflow の awaiting_pr_approval ゲートと正しく連携することを検証する。

テスト手順:
  Step 1 : ワークフロー起動（require_approval=True）
  Step 2 : Phase 1–3（outline/draft/review）を Python Temporal Client で自動承認
  Step 3 : Phase 4（autonomous_fix）+ PR Gate（awaiting_pr_approval）まで待機
  Step 4 : Web UI API 結合テスト（curl 経由）
    テスト A — GET /api/status/:workflowId → 200 / awaiting_pr_approval / current_output 非 null
    テスト B — GET /api/status/nonexistent  → 404
    テスト C — POST /api/approve            → { "success": true }
  Step 5 : ワークフロー完走（completed）確認
  Step 6 : 結果サマリー出力

Usage:
    python web_ui_e2e_test.py
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from core.models import GitHubParams
from workflows.sop_workflow import sop_generation_workflow, PHASE_LABELS

# ─── 設定 ─────────────────────────────────────────────────────────────────────

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE    = "llm-task-queue"
WEB_UI_BASE   = "http://localhost:3000"

TARGET_REPO     = "obataka/temporal-demo"
BASE_BRANCH     = "main"
FEATURE_BRANCH  = "auto-fix/webui-e2e-test"
FILE_PATH       = "docs/sop-webui-e2e-test.md"

TOPIC = "Web UI 結合動作確認テスト用 SOP（Temporal × Hono 統合検証）"

# sop_e2e_demo.py から流用（禁止用語なし・チェック済み）
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

POLL_INTERVAL    = 3.0
TIMEOUT_PER_PHASE = 480.0
TIMEOUT_PHASE4   = 600.0
TIMEOUT_GITHUB   = 300.0

_W = 70

# ─── テスト結果追跡 ────────────────────────────────────────────────────────────

_test_results: list[dict] = []


def _record(name: str, passed: bool, detail: str = "") -> None:
    """
    テスト結果を記録する。

    :param name: テスト名
    :param passed: 合否
    :param detail: 詳細情報（任意）
    """
    _test_results.append({"name": name, "passed": passed, "detail": detail})
    mark = "PASS" if passed else "FAIL"
    _log(mark, f"{name}{(' — ' + detail) if detail else ''}")


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
            _warn(f"Query エラー（リトライ）: {exc}")
        if dots % 10 == 0:
            print(f"  {label}...", end="", flush=True)
        else:
            print(".", end="", flush=True)
        dots += 1
        await asyncio.sleep(POLL_INTERVAL)
    print()
    raise TimeoutError(f"[{label}] {timeout}s 以内に {expected_statuses} に到達しませんでした。")


async def _poll_phase4_and_pr_gate(handle, timeout: float) -> dict:
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
                    print(f"\n  [{ts}] [Phase 4] バリデーション PASS")
                    print(f"  [{ts}] [Phase 5 gate] awaiting_pr_approval に到達")
                    return status
                elif st == "completed":
                    print(f"\n  [{ts}] [Phase 4] 完了")
                    return status

                last_status = st
                last_fix_attempt = fix_attempt

        except Exception as exc:
            _warn(f"Phase 4 Query エラー（リトライ）: {exc}")

        await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Phase 4 が {timeout}s 以内に完了しませんでした。")


# ─── Web UI API テスト ─────────────────────────────────────────────────────────

def _curl(method: str, url: str, data: dict | None = None) -> tuple[int, dict]:
    """
    curl を使って HTTP リクエストを送信し、(status_code, json_body) を返す。

    :param method: HTTP メソッド（GET / POST）
    :param url: リクエスト URL
    :param data: POST ボディ（dict。GET の場合は None）
    :returns: (HTTPステータスコード, レスポンスJSONボディ) のタプル
    :raises subprocess.CalledProcessError: curl 実行失敗時
    """
    cmd = ["curl", "-s", "-o", "/dev/stdout", "-w", "\n%{http_code}", "-X", method]
    if data is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = result.stdout.strip().rsplit("\n", 1)
    body_str = lines[0] if len(lines) >= 2 else "{}"
    status_code = int(lines[-1]) if lines[-1].isdigit() else 0

    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        body = {"raw": body_str}

    return status_code, body


def _run_web_ui_tests(workflow_id: str) -> None:
    """
    Web UI API の結合テストを実行する。

    :param workflow_id: テスト対象のワークフロー ID
    """
    _header("STEP 4 — Web UI API 結合テスト（curl）")

    # ── テスト A: GET /api/status/:workflowId ────────────────────────────────
    _info("テスト A: GET /api/status/:workflowId")
    url_a = f"{WEB_UI_BASE}/api/status/{workflow_id}"
    _info(f"  curl -s {url_a}")
    try:
        code, body = _curl("GET", url_a)
        print(f"  HTTP {code}")
        print(f"  status       : {body.get('status')}")
        print(f"  current_phase: {body.get('current_phase')}")
        print(f"  phase_label  : {body.get('phase_label')}")
        sop_preview = (body.get("current_output") or "")[:120]
        print(f"  current_output (先頭120文字): {repr(sop_preview)}")

        ok = (
            code == 200
            and body.get("status") == "awaiting_pr_approval"
            and bool(body.get("current_output"))
            and bool(body.get("phase_label"))
        )
        _record("テスト A: GET /api/status (200, awaiting_pr_approval)", ok,
                f"HTTP {code} / status={body.get('status')}")
    except Exception as exc:
        _record("テスト A: GET /api/status", False, str(exc))

    # ── テスト B: GET /api/status/nonexistent → 404 ──────────────────────────
    _info("テスト B: GET /api/status/nonexistent-id")
    url_b = f"{WEB_UI_BASE}/api/status/nonexistent-webui-e2e-test-id"
    _info(f"  curl -s {url_b}")
    try:
        code, body = _curl("GET", url_b)
        print(f"  HTTP {code}  body: {body}")
        _record("テスト B: GET /api/status (404 for nonexistent)",
                code == 404, f"HTTP {code}")
    except Exception as exc:
        _record("テスト B: GET /api/status (404)", False, str(exc))

    # ── テスト C: POST /api/approve ──────────────────────────────────────────
    _info("テスト C: POST /api/approve")
    url_c = f"{WEB_UI_BASE}/api/approve"
    payload = {"workflowId": workflow_id}
    _info(f"  curl -s -X POST {url_c} -d '{json.dumps(payload)}'")
    try:
        code, body = _curl("POST", url_c, data=payload)
        print(f"  HTTP {code}  body: {body}")
        _record("テスト C: POST /api/approve (200, success=true)",
                code == 200 and body.get("success") is True,
                f"HTTP {code} / success={body.get('success')}")
    except Exception as exc:
        _record("テスト C: POST /api/approve", False, str(exc))


# ─── メイン ───────────────────────────────────────────────────────────────────

async def main() -> None:
    """
    Web UI 結合テストのエントリポイント。全 Step を順番に実行し結果を集計する。
    """
    _rule()
    print("  Web UI E2E 結合テスト — Hono API × sop_generation_workflow")
    _rule()

    started_at = time.monotonic()

    # ── Temporal 接続 ────────────────────────────────────────────────────────
    _info(f"Temporal に接続中: {TEMPORAL_HOST}")
    client = await Client.connect(TEMPORAL_HOST)

    workflow_id = f"sop-webui-e2e-{uuid.uuid4().hex[:8]}"
    github_params = GitHubParams(
        repository=TARGET_REPO,
        base_branch=BASE_BRANCH,
        feature_branch=FEATURE_BRANCH,
        file_path=FILE_PATH,
        require_approval=True,
    )

    _info(f"Workflow ID : {workflow_id}")
    _info(f"Topic       : {TOPIC}")
    _info(f"Web UI Base : {WEB_UI_BASE}")
    print()

    # ── Step 1: ワークフロー起動 ──────────────────────────────────────────────
    _header("STEP 1 — ワークフロー起動")
    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[TOPIC, DUMMY_SOURCE_CODE, github_params],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    _ok("起動完了")
    _info(f"Temporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")

    # ── Step 2: Phase 1–3 自動承認 ────────────────────────────────────────────
    for phase in ("outline", "draft", "review"):
        phase_label = PHASE_LABELS[phase]
        _header(f"STEP 2 — {phase_label}（自動承認）")
        await _poll_until(
            handle,
            expected_statuses=("awaiting_approval", "completed"),
            timeout=TIMEOUT_PER_PHASE,
            label=f"{phase_label} 生成中",
        )
        _ok(f"{phase_label} 生成完了 → 自動承認")
        await handle.signal("approve_step", "")
        await asyncio.sleep(2.0)

    # ── Step 3: Phase 4 + PR Gate 待機 ────────────────────────────────────────
    _header("STEP 3 — Phase 4: 自律修正ループ → PR 承認ゲート待機")
    await asyncio.sleep(3.0)
    phase4_status = await _poll_phase4_and_pr_gate(handle, timeout=TIMEOUT_PHASE4)

    if phase4_status["status"] == "completed":
        _warn("ワークフローが PR ゲートをスキップして完了しました。テスト C はスキップします。")
        _run_web_ui_tests_skipped = True
    else:
        _run_web_ui_tests_skipped = False

    # ── Step 4: Web UI API 結合テスト ─────────────────────────────────────────
    if not _run_web_ui_tests_skipped:
        _run_web_ui_tests(workflow_id)

    # ── Step 5: ワークフロー完走確認 ──────────────────────────────────────────
    _header("STEP 5 — ワークフロー完走確認")
    _info("PR 作成中... (GitHub Activity 実行中)")
    try:
        final = await _poll_until(
            handle,
            expected_statuses=("completed",),
            timeout=TIMEOUT_GITHUB,
            label="PR 作成中",
        )
        pr_url = final.get("pr_url")
        if not pr_url:
            wf_result = await handle.result()
            pr_url = wf_result.get("pr_url") if isinstance(wf_result, dict) else None
        _ok(f"ワークフロー完走: {workflow_id}")
        _record("Step 5: ワークフロー completed", True, f"pr_url={pr_url}")
    except TimeoutError as exc:
        _warn(str(exc))
        pr_url = None
        _record("Step 5: ワークフロー completed", False, "タイムアウト")

    # ── Step 6: 結果サマリー ──────────────────────────────────────────────────
    elapsed = time.monotonic() - started_at
    _header("STEP 6 — テスト結果サマリー")

    passed = sum(1 for r in _test_results if r["passed"])
    total  = len(_test_results)

    print()
    _rule()
    print(f"  結果: {passed}/{total} PASS")
    _rule()
    for r in _test_results:
        mark = "✓ PASS" if r["passed"] else "✗ FAIL"
        detail = f"  ({r['detail']})" if r["detail"] else ""
        print(f"  {mark}  {r['name']}{detail}")
    print()
    if pr_url:
        print(f"  GitHub PR URL : {pr_url}")
    print(f"  Workflow ID   : {workflow_id}")
    print(f"  総所要時間    : {elapsed / 60:.1f} 分 ({elapsed:.0f}s)")
    print(f"  Temporal UI   : http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    _rule()

    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
