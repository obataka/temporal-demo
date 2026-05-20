# 概要ドキュメント: approve_pr Signal 実戦疎通テストスクリプト

**作成日:** 2026-05-20  
**タスク:** `sop_signal_test.py` — Human-in-the-Loop approve_pr Signal フローのエンドツーエンド検証

---

## A. System Interaction Flow

```
python sop_signal_test.py（ホストマシンで実行）
    ↓ Temporal Client.connect(localhost:7233)
    ↓ start_workflow(GitHubParams(require_approval=True, feature_branch="auto-fix/sop-signal-test"))
    ↓
[Phase 1-3] outline / draft / review
    ↓ _poll_until_ready(expected=("awaiting_approval",))
    ↓ handle.signal("approve_step", "")  × 3回
    ↓
[Phase 4] autonomous_fix（自律修正ループ）— Signal 不要
    ↓ _poll_until_ready(expected=("awaiting_pr_approval",))
    ↓
[PAUSE確認]
    ↓ handle.query("get_status")
    ↓   → status["status"] == "awaiting_pr_approval"
    ↓   → status["pr_approved"] == False
    ↓ コンソールに停止状態を出力
    ↓
[approve_pr Signal 送信]
    ↓ handle.signal("approve_pr")
    ↓   → sop_generation_workflow._pr_approved = True
    ↓   → wait_condition 解除 → Phase 5 開始
    ↓
[Phase 5] github_pr 作成
    ↓ _poll_until_ready(expected=("completed",))
    ↓ final_status["pr_url"] を出力
```

---

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `sop_signal_test.py` | **新規作成** | `require_approval=True` での approve_pr Signal フロー疎通検証 | `sop_generation_workflow`, Temporal Server |

---

## C. 設計の意図とクリティカルポイント

### なぜ既存の `sop_github_test.py` を拡張せず新ファイルとしたか
2つのテストスクリプトは「PR を作れるか」と「Signal で止まって再開できるか」という異なる関心事を持つ。
同一ファイルに混在させると `FEATURE_BRANCH` などの設定値が競合し、
並列実行時に同じブランチへの push が衝突する。独立ファイルで責務を分けた。

### クリティカルポイント（3点）

1. **`awaiting_pr_approval` は Phase 4 完了後に到達する** — Phase 1-3 の `awaiting_approval` と混同しないよう、`_poll_until_ready` の `expected_statuses` で両方を区別している。Phase 1-3 ループでは `("awaiting_pr_approval", "completed")` を早期終了条件として保持し、意図しないスキップを検知する。

2. **Signal 送信は Query による停止確認後** — `await handle.signal("approve_pr")` の前に必ず `_poll_until_ready(expected=("awaiting_pr_approval",))` で停止を確認する。Signal を先に送ると `_pr_approved=True` になるが `wait_condition` がまだ存在しないため無視される可能性がある。

3. **ブランチ名 `auto-fix/sop-signal-test`** — `sop_github_test.py` が使う `auto-fix/sop-first-test` と異なるブランチを使用。同時実行時の push 衝突を防止している。

---

## テスト実行手順

```bash
# Docker Worker が起動済みであること
docker compose ps

# テストスクリプト実行
python sop_signal_test.py
```

### 期待出力（抜粋）
```
[PAUSED] ワークフローが PR 承認待ちで一時停止中
  status      = awaiting_pr_approval
  pr_approved = False
[SIGNAL] approve_pr Signal を送信します...
[OK]     approve_pr Signal を送信しました
    [ポーリング] phase=github_pr, status=creating_pr
    [ポーリング] phase=github_pr, status=completed
[SUCCESS] PR URL: https://github.com/obataka/temporal-demo/pull/X
```
