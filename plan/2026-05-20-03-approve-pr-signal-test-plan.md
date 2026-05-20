# 計画: approve_pr Signal 実戦疎通テストスクリプト作成

## Context
Human-in-the-Loop ガバナンス機能（`approve_pr` Signal + `require_approval` フラグ）を実装済みだが、
この Signal フローのエンドツーエンド検証スクリプトがない。
`sop_github_test.py` は `require_approval=False`（デフォルト）での PR 作成疎通のみを確認するため、
新しいスクリプト `sop_signal_test.py` を作成し、Signal によるポーズ → 承認 → PR 作成フローを確認する。

---

## 変更ファイル一覧

| ファイル | 操作 | 概要 |
|---|---|---|
| `sop_signal_test.py` | **新規作成** | `require_approval=True` での approve_pr Signal 疎通テスト |

---

## `sop_signal_test.py` の実装方針

### 設定値
```python
FEATURE_BRANCH = "auto-fix/sop-signal-test"
FILE_PATH      = "docs/sop-signal-test.md"
TOPIC          = "approve_pr Signal 疎通テスト用SOP"
SOURCE_FILE    = "activities/github_activity.py"   # 既存と同じ
```

### フロー設計

```
1. _ensure_github_token()
2. client = await Client.connect()
3. handle = await client.start_workflow(
       ..., args=[TOPIC, source_code,
           GitHubParams(require_approval=True, feature_branch=FEATURE_BRANCH, ...)]
   )

4. [Phase 1-3 自動承認ループ]
   for phase in ("outline", "draft", "review"):
       await _poll_until_ready(handle, expected=("awaiting_approval",), ...)
       await handle.signal("approve_step", "")
       await asyncio.sleep(2.0)

5. [Phase 4 完了 + awaiting_pr_approval 待ち]
   await _poll_until_ready(handle, expected=("awaiting_pr_approval",), ...)

6. [ポーズ確認ログ出力]
   status = await handle.query("get_status")
   # 期待値: status["status"] == "awaiting_pr_approval"
   #         status["pr_approved"] == False
   print("[PAUSED] ワークフローが PR 承認待ちで一時停止中")
   print(f"  status      = {status['status']}")
   print(f"  pr_approved = {status['pr_approved']}")

7. [approve_pr Signal 送信]
   await handle.signal("approve_pr")
   print("[SIGNAL] approve_pr を送信しました")

8. [完了待ち & 結果表示]
   final_status = await _poll_until_ready(handle, expected=("completed",), ...)
   print(f"[SUCCESS] PR URL: {final_status['pr_url']}")
```

### 既存コードの再利用（`sop_github_test.py` から流用）
- `_ensure_github_token()` — GITHUB_TOKEN 確保ロジック（全文コピー）
- `_load_source_code()` — ソースファイル読み込み（全文コピー）
- `_poll_until_ready()` — ポーリングヘルパー（全文コピー）。`expected_statuses` 引数で `("awaiting_pr_approval",)` を渡すだけで対応できる

---

## 検証手順

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
[SIGNAL] approve_pr を送信しました
    [ポーリング] phase=github_pr, status=creating_pr
    [ポーリング] phase=github_pr, status=completed
[SUCCESS] PR URL: https://github.com/obataka/temporal-demo/pull/X
```
