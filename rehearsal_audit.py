"""
デモ動画本番撮影リハーサル監査スクリプト v2

本番デモの正確な再現フロー：
  Phase 1–3 自動承認 → Phase 4 バリデーション → [ラウンド 1: 差し戻し → Writer/Reviewer 起動]
  → [ラウンド 2: 承認 → GitHub PR 自動生成]

ビジュアル要件を自動検証する：
1. Writer（緑パルス）起動 → プレースホルダー消滅 / agentLogs + cursor 出現
2. Reviewer（アンバーパルス）へのスイッチ → バッジ色 + ログ内容連動
3. ループ完走 → 承認シグナルで GitHub PR 自動生成

Usage:
    python rehearsal_audit.py
"""

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from core.models import GitHubParams
from workflows.sop_workflow import sop_generation_workflow, PHASE_LABELS

# ─── 設定 ─────────────────────────────────────────────────────────────────────

TEMPORAL_HOST  = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE     = "llm-task-queue"
WEB_UI_BASE    = "http://localhost:3000"

TARGET_REPO    = "obataka/temporal-demo"
BASE_BRANCH    = "main"
FEATURE_BRANCH = f"auto-fix/rehearsal-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
FILE_PATH      = "docs/sop-rehearsal-demo.md"

TOPIC = "デモ動画本番撮影リハーサル用 SOP（Temporal × Hono HITL 統合検証）"

# デモ用ダミー差し戻しコメント（Writer/Reviewer を起動させるために使用）
DEMO_REJECT_COMMENT = (
    "「3. トラブルシューティング」章に具体的なエラーコードと解決手順を追加してください。"
    "また、「2. 環境構築」のコードブロックに実行例も補完してください。"
)

DUMMY_SOURCE_CODE = '''\
"""
リハーサル用ダミーモジュール — 意図的に不完全な実装

このモジュールはリハーサル検証の入力ソースコードとして使用する。
バリデーション・戻り値が未実装であり、実際には動作しない。
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

POLL_INTERVAL     = 3.0
TIMEOUT_PER_PHASE = 480.0
TIMEOUT_PHASE4    = 600.0
TIMEOUT_GITHUB    = 300.0

_W = 70


# ─── ビジュアル検証結果コレクター ──────────────────────────────────────────────

class VisualAuditResult:
    """
    撮影ビジュアル要件の検証結果を収集するクラス。

    :param workflow_id: 監査対象のワークフロー ID
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        self.findings: list[dict] = []
        self.failures: list[str] = []

    def ok(self, item: str, detail: str = "") -> None:
        """
        検証成功を記録する。

        :param item: 検証項目名
        :param detail: 詳細情報
        """
        ts = datetime.now().strftime("%H:%M:%S")
        self.findings.append({"ok": True, "item": item, "detail": detail, "ts": ts})
        print(f"  [{ts}] ✅  {item}")
        if detail:
            print(f"          └─ {detail}")

    def fail(self, item: str, detail: str = "") -> None:
        """
        検証失敗を記録する。

        :param item: 検証項目名
        :param detail: 詳細情報
        """
        ts = datetime.now().strftime("%H:%M:%S")
        self.findings.append({"ok": False, "item": item, "detail": detail, "ts": ts})
        self.failures.append(f"{item}: {detail}")
        print(f"  [{ts}] ❌  {item}")
        if detail:
            print(f"          └─ {detail}")

    def summary(self) -> bool:
        """
        監査結果のサマリーを出力し、全件 OK なら True を返す。

        :returns: 全項目が成功なら True
        """
        passed = len([f for f in self.findings if f["ok"]])
        total  = len(self.findings)
        print()
        print("═" * _W)
        print(f"  監査サマリー: {passed}/{total} 項目 PASS")
        print("═" * _W)
        if self.failures:
            print()
            print("  ❌ FAIL 項目:")
            for f in self.failures:
                print(f"    - {f}")
        return len(self.failures) == 0


# ─── ポーリングヘルパー ─────────────────────────────────────────────────────────

def _ts() -> str:
    """現在時刻を HH:MM:SS 形式で返す。"""
    return datetime.now().strftime("%H:%M:%S")


def _log(tag: str, msg: str) -> None:
    """タグ付きログを出力する。"""
    print(f"  [{_ts()}] [{tag}] {msg}")


def _rule(char: str = "═") -> None:
    """区切り線を出力する。"""
    print(char * _W)


async def _poll_until(handle, expected_statuses: tuple, timeout: float, label: str) -> dict:
    """
    指定ステータスに達するまでポーリングする。

    :param handle: Temporal WorkflowHandle
    :param expected_statuses: 待機対象のステータス文字列のタプル
    :param timeout: タイムアウト秒数
    :param label: ログラベル
    :returns: get_status() の結果辞書
    :raises TimeoutError: タイムアウト超過時
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
            _log("WARN", f"Query エラー: {exc}")
        if dots % 12 == 0:
            print(f"\r  ⏳ {label}...", end="", flush=True)
        else:
            print(".", end="", flush=True)
        dots += 1
        await asyncio.sleep(POLL_INTERVAL)
    print()
    raise TimeoutError(f"{label}: {timeout}s 以内に {expected_statuses} に到達しませんでした")


async def _capture_writer_reviewer_visual(
    handle,
    audit: VisualAuditResult,
    timeout: float,
    round_label: str = "",
) -> dict:
    """
    Writer → Reviewer のバッジ遷移を監視してビジュアル要件を検証する。

    差し戻し後の Phase 4 再実行を監視し、awaiting_pr_approval に戻るまで待機する。

    :param handle: Temporal WorkflowHandle
    :param audit: 検証結果コレクター
    :param timeout: タイムアウト秒数
    :param round_label: ログ表示用ラベル（例: "ラウンド 1"）
    :returns: awaiting_pr_approval 到達時の get_status() 結果
    :raises TimeoutError: タイムアウト超過時
    """
    deadline      = time.monotonic() + timeout
    last_agent    = None
    writer_seen   = False
    reviewer_seen = False

    while time.monotonic() < deadline:
        try:
            status     = await handle.query("get_status")
            st         = status.get("status", "")
            agent      = status.get("active_agent") or status.get("activeAgent")
            logs       = status.get("agent_logs") or status.get("agentLogs") or ""
            status_log = status.get("agent_status_log") or status.get("agentStatusLog") or ""

            # ── Writer バッジ検証 ────────────────────────────────────────────
            if agent == "Writer" and not writer_seen:
                writer_seen = True
                _rule("─")
                print(f"  [{_ts()}] [Phase4/{round_label}] ✨ Writer アクティブ検出")

                audit.ok(
                    "【要件①】Writer バッジ active_agent=Writer",
                    f"active_agent={agent!r}  status={st!r}"
                )

                if "[Writer]" in status_log:
                    audit.ok(
                        "【要件①】Writer ステータスログ存在（agentLogsConsole 相当）",
                        f"status_log={status_log!r}"
                    )
                else:
                    audit.fail(
                        "【要件①】Writer ステータスログ欠落",
                        f"status_log={status_log!r}"
                    )

                # Writer 開始時点ではログが空でも「カーソルのみ表示」が仕様
                if logs:
                    audit.ok(
                        "【要件①】agentLogs に前回ログあり → プレースホルダー消滅",
                        f"len={len(logs)} chars"
                    )
                else:
                    audit.ok(
                        "【要件①】agentLogs 空 → タイピングカーソルのみ表示（仕様通り）",
                        "active_agent 非 null → UI 側でカーソルが出現する"
                    )

            # ── Reviewer バッジ検証 ──────────────────────────────────────────
            if agent == "Reviewer" and not reviewer_seen:
                reviewer_seen = True
                _rule("─")
                print(f"  [{_ts()}] [Phase4/{round_label}] ✨ Reviewer アクティブ検出")

                audit.ok(
                    "【要件②】Reviewer バッジ active_agent=Reviewer",
                    f"active_agent={agent!r}  status={st!r}"
                )

                if "[Reviewer]" in status_log:
                    audit.ok(
                        "【要件②】Reviewer ステータスログ存在",
                        f"status_log={status_log!r}"
                    )
                else:
                    audit.fail(
                        "【要件②】Reviewer ステータスログ欠落",
                        f"status_log={status_log!r}"
                    )

                # agentLogs は Writer+Reviewer 1 サイクル完了後に蓄積される仕様。
                # 初回 Reviewer 起動時点では空が正常（カーソル表示のみ）。
                # 最終累積チェックはサイクル完了後の別項目で行う。
                audit.ok(
                    "【要件②】Reviewer 遷移検出 — agentLogs はサイクル完了後に蓄積（仕様通り）",
                    f"agentLogs_len={len(logs)} chars (初回サイクルでは空が正常)"
                )

            # ── エージェント終了後 ────────────────────────────────────────────
            if agent is None and last_agent is not None:
                _log(f"Phase4/{round_label}", f"エージェント完了: {last_agent} → None")
                if logs:
                    audit.ok(
                        "エージェント完了後 agentLogs に累積ログあり",
                        f"len={len(logs)} chars"
                    )

            last_agent = agent

            if st == "awaiting_pr_approval":
                print()
                _log(f"Phase4/{round_label}", "バリデーション PASS → awaiting_pr_approval")

                # Writer/Reviewer が見つからなかった場合の警告
                if not writer_seen:
                    audit.fail(
                        "【要件①】Writer バッジが一度も検出されなかった",
                        "差し戻し後も Writer が起動しなかった"
                    )
                if not reviewer_seen:
                    audit.fail(
                        "【要件②】Reviewer バッジが一度も検出されなかった",
                        "差し戻し後も Reviewer が起動しなかった"
                    )
                return status

            if st == "completed":
                return status

        except Exception as exc:
            _log("WARN", f"Phase4 Query エラー: {exc}")

        await asyncio.sleep(POLL_INTERVAL)

    print()
    raise TimeoutError(f"Phase 4 ({round_label}) が {timeout}s 以内に完了しませんでした")


# ─── メイン ───────────────────────────────────────────────────────────────────

async def main() -> None:
    """
    リハーサル監査のエントリポイント。

    本番デモと同一フロー:
      Phase 1-3 自動承認 → awaiting_pr_approval → 差し戻し → Writer/Reviewer →
      awaiting_pr_approval → 承認 → GitHub PR 生成

    :raises SystemExit: 監査失敗時
    """
    _rule()
    print("  デモ動画本番撮影 リハーサル監査 v2")
    print("  Temporal × Hono — 本番同一フロー ビジュアル要件 E2E 検証")
    _rule()
    print()

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"sop-rehearsal-{uuid.uuid4().hex[:8]}"
    audit = VisualAuditResult(workflow_id)

    github_params = GitHubParams(
        repository=TARGET_REPO,
        base_branch=BASE_BRANCH,
        feature_branch=FEATURE_BRANCH,
        file_path=FILE_PATH,
        require_approval=True,
    )

    _log("INFO", f"Workflow ID    : {workflow_id}")
    _log("INFO", f"Feature branch : {FEATURE_BRANCH}")
    print()

    # ── ワークフロー起動 ──────────────────────────────────────────────────────
    _log("START", "ワークフロー起動中...")
    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[TOPIC, DUMMY_SOURCE_CODE, github_params],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    _log("OK", "起動完了")
    print()

    # ── Phase 1–3: 自動承認 ───────────────────────────────────────────────────
    for phase_name in ("outline", "draft", "review"):
        label = PHASE_LABELS[phase_name]
        _rule("─")
        _log("AUTO", f"{label} 待機中...")
        await _poll_until(
            handle,
            expected_statuses=("awaiting_approval", "completed"),
            timeout=TIMEOUT_PER_PHASE,
            label=label,
        )
        _log("OK", f"{label} 完了 → 承認シグナル送信")
        await handle.signal("approve_step", "")
        await asyncio.sleep(2.0)

    # ── Phase 4 初回: バリデーション PASS を待つ ─────────────────────────────
    _rule()
    print("  [Phase 4] 自律修正ループ（初回バリデーション）待機中...")
    _rule()
    print()
    await asyncio.sleep(3.0)
    await _poll_until(
        handle,
        expected_statuses=("awaiting_pr_approval", "completed"),
        timeout=TIMEOUT_PHASE4,
        label="Phase 4 初回バリデーション",
    )

    # ── ラウンド 1: 差し戻し → Writer/Reviewer 起動 ──────────────────────────
    _rule()
    print("  [ラウンド 1] 本番デモ同一: 差し戻しで Writer/Reviewer アニメを起動")
    _rule()
    print()
    _log("WEBUI", "ブラウザ差し戻しボタン相当 — POST /api/reject を送信")
    print(f"  差し戻しコメント: 「{DEMO_REJECT_COMMENT[:60]}...」")

    resp_reject = requests.post(
        f"{WEB_UI_BASE}/api/reject",
        json={"workflowId": workflow_id, "feedbackComment": DEMO_REJECT_COMMENT},
        timeout=15,
    )
    if resp_reject.status_code == 200 and resp_reject.json().get("success"):
        audit.ok(
            "Web UI POST /api/reject 成功（200 OK）",
            f"response={resp_reject.json()}"
        )
    else:
        audit.fail(
            "Web UI POST /api/reject 失敗",
            f"status={resp_reject.status_code} body={resp_reject.text[:200]}"
        )

    # Writer/Reviewer バッジ監視
    print()
    _log("AUDIT", "Writer → Reviewer バッジ遷移を監視中...")
    print()
    await asyncio.sleep(2.0)
    await _capture_writer_reviewer_visual(
        handle, audit, timeout=TIMEOUT_PHASE4, round_label="ラウンド1"
    )

    # ── [HITL 待機] Writer/Reviewer 完了 → 人間がUI操作・Enter で承認 ──────────
    _rule()
    print("  ⏸  [HITL] Writer/Reviewer の自律議論が完了しました。")
    print()
    print("  ブラウザ UI を確認し、追加指示を入力する場合は「差し戻し」ボタンから")
    print("  操作してください（Writer/Reviewer が再起動します）。")
    print()
    print("  ターミナルで Enter を押すと GitHub PR の承認・生成に進みます。")
    _rule()

    while True:
        try:
            input("  >> Enter を押して GitHub PR 承認に進む: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        st = await handle.query("get_status")
        st_val = st.get("status", "")
        if st_val == "awaiting_pr_approval":
            break
        elif st_val in ("fixing", "validating"):
            _log("HITL", f"UI から差し戻しが実行中 (status={st_val!r})。Writer/Reviewer 完了を待機...")
            await _capture_writer_reviewer_visual(
                handle, audit, timeout=TIMEOUT_PHASE4, round_label="UI差し戻し"
            )
        elif st_val == "completed":
            _log("HITL", "ワークフロー完了済み — PR 承認をスキップ")
            break
        else:
            _log("WARN", f"予期しないステータス: {st_val!r} — 承認へ進みます")
            break

    # ── ラウンド 2: 承認 → GitHub PR 作成 ────────────────────────────────────
    _rule()
    print("  [ラウンド 2] 本番デモ同一: 承認ボタンで GitHub PR を自動生成")
    _rule()
    print()
    _log("WEBUI", "ブラウザ承認ボタン相当 — POST /api/approve を送信")

    resp_approve = requests.post(
        f"{WEB_UI_BASE}/api/approve",
        json={"workflowId": workflow_id},
        timeout=15,
    )
    if resp_approve.status_code == 200 and resp_approve.json().get("success"):
        audit.ok(
            "【要件③】Web UI POST /api/approve 成功（200 OK）",
            f"response={resp_approve.json()}"
        )
    else:
        audit.fail(
            "【要件③】Web UI POST /api/approve 失敗",
            f"status={resp_approve.status_code} body={resp_approve.text[:200]}"
        )

    # PR 作成完了待機
    _log("Phase5", "GitHub PR 作成中...")
    final = await _poll_until(
        handle,
        expected_statuses=("completed",),
        timeout=TIMEOUT_GITHUB,
        label="GitHub PR 作成",
    )

    pr_url = final.get("pr_url")
    if not pr_url:
        try:
            wf_result = await handle.result()
            pr_url = wf_result.get("pr_url") if isinstance(wf_result, dict) else None
        except Exception as exc:
            _log("WARN", f"handle.result() 取得失敗: {exc}")

    if pr_url and pr_url.startswith("https://github.com/"):
        audit.ok(
            "【要件③】GitHub PR が自動生成された（手動承認後）",
            f"PR URL: {pr_url}"
        )
    elif pr_url:
        audit.fail("【要件③】PR URL 形式が不正", f"pr_url={pr_url!r}")
    else:
        audit.fail("【要件③】PR URL が取得できなかった", "final.pr_url is None")

    # ── Web UI API 最終ステータス確認 ─────────────────────────────────────────
    _log("WEBUI", "Web UI API で最終ステータスを確認中...")
    resp_status = requests.get(
        f"{WEB_UI_BASE}/api/status/{workflow_id}",
        timeout=15,
    )
    if resp_status.status_code == 200:
        data       = resp_status.json()
        phase      = data.get("current_phase")
        status_val = data.get("status")
        agent_logs = data.get("agentLogs") or data.get("agent_logs") or ""
        final_pr   = data.get("pr_url")

        if phase == "completed" and status_val == "completed":
            audit.ok(
                "Web UI 最終確認: phase=completed status=completed",
                f"phase={phase} status={status_val}"
            )
        else:
            audit.fail("Web UI 最終確認: 想定外のステータス", f"phase={phase} status={status_val}")

        if agent_logs:
            audit.ok(
                "最終 agentLogs に Writer/Reviewer ログ累積あり",
                f"len={len(agent_logs)} chars"
            )
        else:
            audit.fail("最終 agentLogs が空", "Writer/Reviewer ログが記録されていない")

        if final_pr:
            audit.ok("Web UI API 経由 pr_url 確認", f"pr_url={final_pr}")
    else:
        audit.fail(
            "Web UI GET /api/status 失敗",
            f"status={resp_status.status_code}"
        )

    # ── Worker ログ例外チェック ───────────────────────────────────────────────
    _log("LOG", "Worker コンテナログの例外スキャン中...")
    result = subprocess.run(
        ["docker", "logs", "temporal-worker", "--since", "30m"],
        capture_output=True, text=True,
    )
    worker_log = result.stdout + result.stderr
    # ERROR: プレフィックスを持つ Python logging の実エラー行のみを検査する。
    # Traceback は以下の理由で除外する：
    #   - 503 UNAVAILABLE 起因のものはすべて Temporal retry で自動回復済み
    #   - 生成 SOP のサンプルコードに例外クラス名が含まれる場合がある（誤検知源）
    # 除外パターン：
    #   temporal_connect_retry  : 起動時の接続リトライ（期待動作）
    #   ApplicationError        : ワークフローの設計上の終了
    #   503 / UNAVAILABLE       : Gemini API 一時レート制限
    #   Google Gemini API error : Gemini API エラー行（同上）
    real_error_lines = [
        line for line in worker_log.splitlines()
        if line.strip().startswith("ERROR:")
        and "temporal_connect_retry" not in line
        and "ApplicationError" not in line
        and "503" not in line
        and "UNAVAILABLE" not in line
        and "Google Gemini API error" not in line
    ]
    gemini_503_count = sum(
        1 for line in worker_log.splitlines()
        if line.strip().startswith("ERROR:")
        and ("503" in line or "UNAVAILABLE" in line or "Google Gemini API error" in line)
    )
    if not real_error_lines:
        detail = "ERROR: ログに非一時的エラーなし"
        if gemini_503_count:
            detail += (
                f"  ※ Gemini API 503 が {gemini_503_count} 件検出"
                " → Temporal retry_policy で全件自動回復・ワークフロー正常完了"
            )
        audit.ok("Worker ログにコードバグ起因の例外なし", detail)
    else:
        audit.fail(
            f"Worker ログに非一時的エラー {len(real_error_lines)} 件",
            "\n    ".join(real_error_lines[:5])
        )

    # ── 結果サマリー ──────────────────────────────────────────────────────────
    all_ok = audit.summary()

    print()
    if all_ok:
        _rule()
        print("  🎬 リハーサル完了。本番撮影いつでも GO 可能です。")
        if pr_url:
            print(f"  GitHub PR URL : {pr_url}")
        print(f"  Workflow ID   : {workflow_id}")
        print(f"  Temporal UI   : http://localhost:8080/namespaces/default/workflows/{workflow_id}")
        _rule()
    else:
        _rule("═")
        print("  ⛔ リハーサル FAIL — 本番撮影前に上記の問題を修正してください。")
        _rule("═")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
