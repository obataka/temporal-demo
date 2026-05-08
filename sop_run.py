"""
SOP Evidence Collection Runner — 自動実行 + Resilience Test 統合版

事前定義された修正指示で 2 回の人間介入をシミュレートし、
LLM 出力の変化を Before/After 形式で記録する。
また、Phase 1 承認後に Worker を自動再起動してレジリエンスを検証する。

Usage:
    python sop_run.py
    python sop_run.py --source workflows/sop_workflow.py
"""

import asyncio
import json
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

from workflows.sop_workflow import sop_generation_workflow, PHASES, PHASE_LABELS

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

DEFAULT_SOURCE = "activities/sop_activity.py"
DEFAULT_TOPIC = "Temporal SOP 生成 Activity — フェーズ別 Gemini 呼び出し実装"

# 事前定義フィードバック（2 回の人間介入）
FEEDBACKS = {
    "outline": (
        "各章にサブセクションを 2〜3 個追加してください。"
        "また「対象読者（初心者 / 上級者）」と「所要時間の目安」を各章の冒頭に明記してください。"
    ),
    "draft": (
        "「エラーハンドリングと retry_policy の設計」章を追加し、"
        "実際に動作する Python コードスニペット（retry_policy の設定例）を含めてください。"
    ),
}

_W = 68


# ─── Display Helpers ─────────────────────────────────────────────────────────

def _rule(char: str = "═") -> None:
    print(char * _W)


def _phase_header(label: str, interventions: int) -> None:
    print(f"\n{'═' * _W}")
    print(f"  {label}  ─── 予定介入: {interventions} 回")
    print("═" * _W)


def _boxed(tag: str, attempt: int, output: str, tokens: int, latency: float, *, approved: bool) -> None:
    status_mark = "✅ 承認" if approved else "🔄 待機"
    tok_s = f"tokens={tokens:,}" if tokens else "tokens=?"
    lat_s = f"latency={latency:.0f}ms" if latency else "latency=?"
    print(f"\n  {tag:6s}  試行 #{attempt}  {tok_s}  {lat_s}  {status_mark}")
    print(f"  ┌{'─' * (_W - 4)}┐")
    lines = output.strip().split("\n")
    for line in lines[:14]:
        if len(line) > _W - 6:
            line = line[:_W - 9] + "..."
        print(f"  │ {line}")
    if len(lines) > 14:
        print(f"  │ ... (残り {len(lines) - 14} 行省略)")
    print(f"  └{'─' * (_W - 4)}┘")


def _signal_arrow(feedback: str) -> None:
    print(f"\n  {'▼' * 3}  Signal: approve_step(feedback=...)")
    short = feedback[:72] + ("..." if len(feedback) > 72 else "")
    print(f"  フィードバック: 「{short}」\n")


def _stats_diff(b_tokens: int, b_len: int, a_tokens: int, a_len: int) -> None:
    dt = a_tokens - b_tokens
    dl = a_len - b_len
    pct_t = f"{dt / b_tokens * 100:+.0f}%" if b_tokens else "n/a"
    pct_l = f"{dl / b_len * 100:+.0f}%" if b_len else "n/a"
    st = f"{'+' if dt >= 0 else ''}{dt:,}"
    sl = f"{'+' if dl >= 0 else ''}{dl:,}"
    print(f"\n  📊 変化: tokens {st} ({pct_t})  ─  length {sl} chars ({pct_l})")


# ─── Temporal Helpers ────────────────────────────────────────────────────────

async def wait_for_ready(handle, timeout: float = 300.0) -> dict:
    """status が awaiting_approval または completed になるまでポーリング。"""
    deadline = time.monotonic() + timeout
    dots = 0
    while time.monotonic() < deadline:
        try:
            status = await handle.query("get_status")
            if status["status"] in ("awaiting_approval", "completed"):
                if dots:
                    print()
                return status
        except Exception:
            pass
        if dots % 5 == 0:
            print(".", end="", flush=True)
        dots += 1
        await asyncio.sleep(2.0)
    raise TimeoutError(f"Workflow が {timeout}s 以内に応答しませんでした。")


async def wait_for_query(handle, timeout: float = 60.0) -> dict:
    """Worker 再起動後など、クエリが成功するまでリトライ。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return await handle.query("get_status")
        except Exception:
            await asyncio.sleep(2.0)
    raise TimeoutError("Query が成功しませんでした。")


# ─── Resilience Test ─────────────────────────────────────────────────────────

async def run_resilience_check(handle) -> bool:
    """Worker を再起動し、Workflow 状態が保持されることを検証する。"""
    _rule("─")
    print("  🔬 RESILIENCE TEST — Worker 再起動によるワークフロー継続性検証")
    _rule("─")

    status_before = await handle.query("get_status")
    print(f"  [Before] status={status_before['status']}  phase={status_before['current_phase']}")

    print("  Worker を再起動中... (docker compose restart worker)")
    result = subprocess.run(
        ["docker", "compose", "restart", "worker"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ⚠️  restart stderr: {result.stderr[:120]}")

    print("  Worker の起動を待機中 (15s)...", end="", flush=True)
    await asyncio.sleep(15)
    print(" done")

    try:
        status_after = await wait_for_query(handle, timeout=60)
        print(f"  [After]  status={status_after['status']}  phase={status_after['current_phase']}")
        ok = status_after["status"] == "awaiting_approval"
        if ok:
            print("  ✅ RESILIENCE OK: 再起動後も Workflow 状態を完全保持（Temporal イベント履歴から自動復元）")
        else:
            print(f"  ❌ RESILIENCE NG: 期待 awaiting_approval, 実際 {status_after['status']}")
    except TimeoutError:
        print("  ❌ RESILIENCE NG: Worker 再起動後に Query タイムアウト")
        ok = False

    _rule("─")
    print()
    return ok


# ─── Main ────────────────────────────────────────────────────────────────────

async def main() -> None:
    args = sys.argv[1:]
    source_file = DEFAULT_SOURCE
    topic = DEFAULT_TOPIC

    i = 0
    while i < len(args):
        if args[i] == "--source" and i + 1 < len(args):
            source_file, topic = args[i + 1], f"{args[i + 1]} の SOP"
            i += 2
        else:
            i += 1

    with open(source_file, encoding="utf-8") as f:
        source_code = f.read()

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"sop-evidence-{uuid.uuid4().hex[:8]}"

    _rule()
    print("  SOP Evidence Collection Run")
    _rule()
    print(f"  Workflow ID  : {workflow_id}")
    print(f"  Source       : {source_file} ({len(source_code):,} chars)")
    print(f"  Topic        : {topic[:62]}")
    print(f"  介入シナリオ  : outline +1回フィードバック → draft +1回フィードバック → review 直接承認")
    print(f"  Resilience   : Phase 1 完了後に Worker 再起動テスト")
    _rule()
    print()

    started_at = time.monotonic()

    handle = await client.start_workflow(
        sop_generation_workflow.run,
        args=[topic, source_code],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    # evidence 保存用バッファ: phase → [{"output", "tokens", "latency_ms", "feedback"}]
    records: dict[str, list[dict]] = {p: [] for p in PHASES}

    # ── Phase 1: outline ─────────────────────────────────────────────────────
    _phase_header(PHASE_LABELS["outline"], 1)
    print("⏳ 生成中", end="", flush=True)
    status = await wait_for_ready(handle)
    history = await handle.query("get_history")
    latest = history[-1]

    rec_before = {"output": latest["output"], "tokens": latest["tokens"],
                  "latency_ms": latest["latency_ms"], "feedback": None}
    records["outline"].append(rec_before)
    _boxed("BEFORE", 0, rec_before["output"], rec_before["tokens"], rec_before["latency_ms"], approved=False)

    # Resilience テスト（Phase 1 の初期出力を確認後に実施）
    resilience_ok = await run_resilience_check(handle)

    # フィードバック Signal
    _signal_arrow(FEEDBACKS["outline"])
    await handle.signal("approve_step", FEEDBACKS["outline"])
    await asyncio.sleep(2.0)

    print("⏳ 再生成中", end="", flush=True)
    status = await wait_for_ready(handle)
    history = await handle.query("get_history")
    latest = history[-1]

    rec_after = {"output": latest["output"], "tokens": latest["tokens"],
                 "latency_ms": latest["latency_ms"], "feedback": FEEDBACKS["outline"]}
    records["outline"].append(rec_after)
    _boxed("AFTER ", 1, rec_after["output"], rec_after["tokens"], rec_after["latency_ms"], approved=True)
    _stats_diff(rec_before["tokens"], len(rec_before["output"]),
                rec_after["tokens"], len(rec_after["output"]))

    print(f"\n  ✅ Phase 1 承認")
    await handle.signal("approve_step", "")
    await asyncio.sleep(2.0)

    # ── Phase 2: draft ───────────────────────────────────────────────────────
    _phase_header(PHASE_LABELS["draft"], 1)
    print("⏳ 生成中（草稿は長くなります）", end="", flush=True)
    status = await wait_for_ready(handle, timeout=360)
    history = await handle.query("get_history")
    latest = history[-1]

    rec_before = {"output": latest["output"], "tokens": latest["tokens"],
                  "latency_ms": latest["latency_ms"], "feedback": None}
    records["draft"].append(rec_before)
    _boxed("BEFORE", 0, rec_before["output"], rec_before["tokens"], rec_before["latency_ms"], approved=False)

    _signal_arrow(FEEDBACKS["draft"])
    await handle.signal("approve_step", FEEDBACKS["draft"])
    await asyncio.sleep(2.0)

    print("⏳ 再生成中", end="", flush=True)
    status = await wait_for_ready(handle, timeout=360)
    history = await handle.query("get_history")
    latest = history[-1]

    rec_after = {"output": latest["output"], "tokens": latest["tokens"],
                 "latency_ms": latest["latency_ms"], "feedback": FEEDBACKS["draft"]}
    records["draft"].append(rec_after)
    _boxed("AFTER ", 1, rec_after["output"], rec_after["tokens"], rec_after["latency_ms"], approved=True)
    _stats_diff(rec_before["tokens"], len(rec_before["output"]),
                rec_after["tokens"], len(rec_after["output"]))

    print(f"\n  ✅ Phase 2 承認")
    await handle.signal("approve_step", "")
    await asyncio.sleep(2.0)

    # ── Phase 3: review ──────────────────────────────────────────────────────
    _phase_header(PHASE_LABELS["review"], 0)
    print("⏳ 生成中（最終レビュー）", end="", flush=True)
    status = await wait_for_ready(handle, timeout=360)
    history = await handle.query("get_history")
    latest = history[-1]

    rec_review = {"output": latest["output"], "tokens": latest["tokens"],
                  "latency_ms": latest["latency_ms"], "feedback": None}
    records["review"].append(rec_review)
    _boxed("      ", 0, rec_review["output"], rec_review["tokens"], rec_review["latency_ms"], approved=True)

    print(f"\n  ✅ Phase 3 承認（直接）")
    await handle.signal("approve_step", "")

    elapsed = time.monotonic() - started_at

    # ── Final Evidence Summary ────────────────────────────────────────────────
    history = await handle.query("get_history")
    total_tokens = sum(e.get("tokens", 0) for e in history)
    total_latency = sum(e.get("latency_ms", 0) for e in history)
    feedbacks = sum(1 for e in history if e.get("feedback"))

    print(f"\n\n{'═' * _W}")
    print(f"  ✅ SOP 生成完了  (総所要時間: {elapsed:.0f}s)")
    print(f"{'═' * _W}")
    print(f"\n  📊 Evidence Summary")
    print(f"  {'─' * 42}")
    print(f"  総試行数      : {len(history)}")
    print(f"  人間介入回数  : {feedbacks} 回")
    print(f"  総トークン消費: {total_tokens:,}")
    print(f"  総推論時間    : {total_latency / 1000:.1f}s")
    print(f"  Resilience    : {'✅ OK' if resilience_ok else '❌ NG'}")
    print()

    # フェーズ別 Before/After 差分
    print(f"  {'─' * 42}")
    for phase in PHASES:
        entries = records[phase]
        label = PHASE_LABELS[phase]
        if len(entries) >= 2:
            b, a = entries[0], entries[1]
            dt = a["tokens"] - b["tokens"]
            dl = len(a["output"]) - len(b["output"])
            st = f"{'+' if dt >= 0 else ''}{dt:,}"
            sl = f"{'+' if dl >= 0 else ''}{dl:,}"
            print(f"  {label}")
            print(f"    Before → After: tokens {st}  chars {sl}")
        else:
            r = entries[0]
            print(f"  {label}")
            print(f"    直接承認: {r['tokens']:,} tokens / {len(r['output']):,} chars")
        print()

    # JSON + Markdown 保存
    evidence_dir = Path("evidence")
    evidence_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    evidence_data = {
        "workflow_id": workflow_id,
        "topic": topic,
        "source_file": source_file,
        "timestamp": ts,
        "resilience_ok": resilience_ok,
        "summary": {
            "total_attempts": len(history),
            "total_feedbacks": feedbacks,
            "total_tokens": total_tokens,
            "total_latency_ms": round(total_latency),
            "elapsed_sec": round(elapsed),
        },
        "history": history,
    }
    json_path = evidence_dir / f"sop_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, ensure_ascii=False, indent=2)

    # 最終 SOP を Markdown で保存
    final_review = records["review"][0]["output"] if records["review"] else ""
    md_path = evidence_dir / f"sop_{ts}_final.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n")
        f.write(f"*Generated: {ts} | Workflow: {workflow_id}*\n\n")
        f.write(final_review)

    print(f"  💾 Evidence JSON : {json_path}")
    print(f"  📄 Final SOP MD  : {md_path}")
    print(f"  🌐 Temporal UI   : http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    print(f"{'═' * _W}\n")


if __name__ == "__main__":
    asyncio.run(main())
