"""
Agentic SOP Review Demo — CrewAI 多役割エージェントによる SOP レビュー

Usage:
    python crew_demo.py                        # 最新の evidence/ から SOP 草稿を読み込む
    python crew_demo.py --draft path/to/sop.md # 指定ファイルを草稿として使用
    python crew_demo.py --hint "コード例を増やしてください"  # 技術担当へのヒントを事前指定

デモの流れ:
    Phase 1 — 校正担当エージェント（CrewAI）が実行中
              ↓ 約 20 秒後に inject_hint Signal を自動送信（技術担当へのヒント）
    Phase 2 — 技術担当エージェント（CrewAI）がヒントを受け取って実行
    Phase 3 — Gemini が 2 エージェントの出力を統合
    最後に Inner Monologue ログを表示
"""

import asyncio
import glob
import json
import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from workflows.agentic_review_workflow import agentic_review_workflow, PHASE_LABELS

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

_DEFAULT_HINT = (
    "retry_policy の設定例と ServerError の具体的な対処方法を"
    "コードスニペット付きで説明するよう強調してください"
)
_W = 68


# ─── Display ─────────────────────────────────────────────────────────────────

def _rule(c: str = "═") -> None:
    print(c * _W)


def _phase_banner(label: str) -> None:
    print(f"\n{'─' * _W}")
    print(f"  {label}")
    print("─" * _W)


def _print_thought(agent_label: str, thought: str) -> None:
    print(f"\n  💭 [{agent_label}] Inner Monologue")
    print(f"  ┌{'─' * (_W - 4)}┐")
    for line in thought.strip().split("\n")[:10]:
        if len(line) > _W - 6:
            line = line[:_W - 9] + "..."
        print(f"  │ {line}")
    if thought.count("\n") > 10:
        print(f"  │ ...")
    print(f"  └{'─' * (_W - 4)}┘")


def _print_full_log(agent_log: list[dict]) -> None:
    _rule()
    print("  Inner Monologue — 全エージェントの思考ログ")
    _rule()

    for entry in agent_log:
        label = entry.get("agent_label", entry["agent"])
        tokens = entry.get("tokens", 0)
        latency = entry.get("latency_ms", 0)

        _phase_banner(f"{label}  tokens={tokens:,}  latency={latency:.0f}ms")

        hints = entry.get("hints_received", [])
        if hints:
            print(f"\n  [inject_hint で注入されたヒント: {len(hints)} 件]")
            for h in hints:
                print(f"  📡 「{h[:80]}{'...' if len(h) > 80 else ''}」")

        thoughts = entry.get("thoughts", [])
        if thoughts:
            for i, t in enumerate(thoughts):
                print(f"\n  [思考ステップ {i + 1}]")
                print(f"  {'·' * (_W - 4)}")
                for line in t.strip().split("\n")[:15]:
                    if len(line) > _W - 6:
                        line = line[:_W - 9] + "..."
                    print(f"  {line}")
        else:
            print("  (思考ログなし)")

        output = entry.get("output", "")
        print(f"\n  [最終出力]  {len(output):,} chars")
        print(f"  {'·' * (_W - 4)}")
        snippet = output.strip()[:500]
        for line in snippet.split("\n")[:12]:
            if len(line) > _W - 4:
                line = line[:_W - 7] + "..."
            print(f"  {line}")
        if len(output) > 500:
            print(f"  ... (残り {len(output) - 500} 文字省略)")

    _rule()


# ─── Temporal Helpers ────────────────────────────────────────────────────────

async def poll_until(handle, target_phases: list[str], timeout: float = 600.0) -> dict:
    """指定フェーズまたは completed になるまでポーリング。"""
    deadline = time.monotonic() + timeout
    last_phase = ""
    while time.monotonic() < deadline:
        try:
            st = await handle.query("get_agent_status")
            phase = st["current_phase"]
            if phase != last_phase:
                last_phase = phase
            if st["status"] == "completed" or phase in target_phases:
                return st
        except Exception:
            pass
        print(".", end="", flush=True)
        await asyncio.sleep(3.0)
    raise TimeoutError(f"Workflow が {timeout:.0f}s 以内に応答しませんでした。")


# ─── Main ────────────────────────────────────────────────────────────────────

async def main() -> None:
    # ── 引数パース ────────────────────────────────────────────────────────────
    args = sys.argv[1:]
    draft_file: str | None = None
    hint = _DEFAULT_HINT

    i = 0
    while i < len(args):
        if args[i] == "--draft" and i + 1 < len(args):
            draft_file = args[i + 1]; i += 2
        elif args[i] == "--hint" and i + 1 < len(args):
            hint = args[i + 1]; i += 2
        else:
            i += 1

    # ── SOP 草稿を取得 ────────────────────────────────────────────────────────
    if draft_file:
        with open(draft_file, encoding="utf-8") as f:
            draft = f.read()
    else:
        # 最新の evidence JSON から Phase 2 (draft) の承認済み出力を使用
        json_files = sorted(glob.glob("evidence/sop_*.json"))
        if json_files:
            with open(json_files[-1], encoding="utf-8") as f:
                ev = json.load(f)
            draft_entry = next(
                (e for e in ev["history"] if e["phase"] == "draft" and e.get("approved")),
                None,
            )
            draft = draft_entry["output"] if draft_entry else ev["history"][-1]["output"]
            print(f"  evidence から草稿を読み込みました: {json_files[-1]}")
        else:
            # フォールバック: sop_workflow.py の内容
            with open("workflows/sop_workflow.py", encoding="utf-8") as f:
                draft = f"# SOP ドラフト\n\n以下のコードをドキュメント化してください:\n\n```python\n{f.read()}\n```"

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"crew-review-{uuid.uuid4().hex[:8]}"

    _rule()
    print("  Agentic SOP Review — CrewAI × Temporal")
    _rule()
    print(f"  Workflow ID   : {workflow_id}")
    print(f"  Draft length  : {len(draft):,} chars")
    print(f"  Hint          : {hint[:60]}...")
    print(f"  Phase 1       : 校正担当エージェント（CrewAI）")
    print(f"  Phase 2       : 技術担当エージェント（CrewAI + hint）")
    print(f"  Phase 3       : レビュー統合（Gemini）")
    print(f"  Temporal UI   : http://localhost:8080")
    _rule()
    print()

    handle = await client.start_workflow(
        agentic_review_workflow.run,
        draft,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    # ── Phase 1: 校正担当が実行中 ─────────────────────────────────────────────
    _phase_banner(PHASE_LABELS["proofreader"])
    print("⏳ 校正担当エージェントが実行中", end="", flush=True)

    # 20 秒後に inject_hint Signal を送信（校正担当が動いている間に技術担当へのヒントを注入）
    async def inject_after_delay() -> None:
        await asyncio.sleep(20)
        try:
            st = await handle.query("get_agent_status")
            if st["current_phase"] == "proofreader":
                await handle.signal("inject_hint", hint)
                print(f"\n\n  📡 inject_hint Signal 送信 → 技術担当に引き継がれます")
                print(f"     ヒント: 「{hint[:65]}...」\n")
        except Exception:
            pass

    hint_task = asyncio.create_task(inject_after_delay())

    # tech_reviewer フェーズに移行するまで待機
    st = await poll_until(handle, ["tech_reviewer", "merging", "completed"])
    hint_task.cancel()

    # 校正担当の Inner Monologue を表示
    full_log = await handle.query("get_full_log")
    if full_log:
        proofreader_entry = next((e for e in full_log if e["agent"] == "proofreader"), None)
        if proofreader_entry and proofreader_entry.get("thoughts"):
            _print_thought("校正担当", proofreader_entry["thoughts"][-1])

    # ── Phase 2: 技術担当 ─────────────────────────────────────────────────────
    if st["current_phase"] != "completed":
        _phase_banner(PHASE_LABELS["tech_reviewer"])
        # pending_hints: Phase 1 実行中に届いたヒントがここにある
        queued = st.get("pending_hints", [])
        hint_msg = f"注入済みヒント: {len(queued)} 件" if queued else "ヒントなし"
        print(f"⏳ 技術担当エージェントが実行中（{hint_msg}）", end="", flush=True)

        st = await poll_until(handle, ["merging", "completed"])

        full_log = await handle.query("get_full_log")
        tech_entry = next((e for e in full_log if e["agent"] == "tech_reviewer"), None)
        if tech_entry and tech_entry.get("thoughts"):
            _print_thought("技術担当", tech_entry["thoughts"][-1])

    # ── Phase 3: 統合 ─────────────────────────────────────────────────────────
    if st["current_phase"] not in ("completed",):
        _phase_banner(PHASE_LABELS["merging"])
        print("⏳ Gemini がレビューを統合中", end="", flush=True)
        st = await poll_until(handle, ["completed"])

    print()

    # ── 完了・最終レポート ─────────────────────────────────────────────────────
    _rule()
    print("  ✅ Agentic Review 完了")
    _rule()

    # 最終ログ
    full_log = await handle.query("get_full_log")
    _print_full_log(full_log)

    # 最終 SOP を保存
    try:
        result = await handle.result()
        final = result.get("final_review", "")
        total_tokens = result.get("total_tokens", 0)
        total_latency = result.get("total_latency_ms", 0)

        evidence_dir = Path("evidence")
        evidence_dir.mkdir(exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = evidence_dir / f"crew_{ts}_final.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# Agentic Review — 最終版 SOP\n\n")
            f.write(f"*{ts} | Workflow: {workflow_id}*\n\n")
            f.write(final)

        print(f"\n  📊 総トークン消費  : {total_tokens:,}")
        print(f"  ⏱️  総推論時間      : {total_latency / 1000:.1f}s")
        print(f"  📄 最終 SOP        : {out_path}")
    except Exception as e:
        print(f"  ⚠️  結果取得エラー: {e}")

    print(f"  🌐 Temporal UI     : http://localhost:8080/namespaces/default/workflows/{workflow_id}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
