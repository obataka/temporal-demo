# 概要ドキュメント: approve_pr Signal E2E 疎通テスト完了

**作成日:** 2026-05-20  
**タスク:** sop_signal_test.py によるHuman-in-the-Loop approve_pr Signal フローの実証

---

## A. System Interaction Flow

```
python sop_signal_test.py（ホストマシン）
    ↓ GitHubParams(require_approval=True, feature_branch="auto-fix/sop-signal-test")
    ↓ start_workflow → sop-signal-test-5f7cbb51
    ↓
[Phase 1-3] 自動承認（approve_step Signal × 3）
    ↓
[Phase 4] autonomous_fix（バリデーション → AI修正 → パス）
    ↓
[Phase 5入口] require_approval=True → status="awaiting_pr_approval"
    ↓ wait_condition(lambda: self._pr_approved) → 待機中
    ↓
[人間による判断] Temporal Web UI (localhost:8080) から
    ↓   Signal: approve_pr（Input 空）→ Submit
    ↓ _pr_approved = True → wait_condition 解除
    ↓
[Phase 5続行] status="creating_pr" → GitHubActivity.create_pull_request
    ↓
PR作成完了 → https://github.com/obataka/temporal-demo/pull/2
status="completed", pr_approved=True
```

---

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `sop_signal_test.py` | 新規作成 | approve_pr Signal E2E 疎通テストスクリプト | Temporal Server, sop_generation_workflow |
| `workflows/sop_workflow.py` | 実装済み | approve_pr Signal ハンドラ + wait_condition ゲート | temporal-worker（Docker） |

---

## C. 設計の意図とクリティカルポイント

### クリティカルポイント（3点）

1. **Worker のリビルドが必要** — `docker-compose.yaml` は `build: .`（COPY方式）のため、ワークフローコード変更後は必ず `docker compose up --build worker -d` が必要。マウント方式と異なり、コード変更がコンテナに自動反映されない。

2. **`input()` は Claude Code の Bash ツールでは動作しない** — stdin が TTY でないため `EOFError` になる。インタラクティブな承認操作はユーザーが直接ターミナルで実行するか、Temporal Web UI の Signal 送信機能を使う必要がある。

3. **`temporal-ui` コンテナは手動起動が必要** — `docker compose up --build worker` を実行しても `temporal-ui` は起動しない（`worker` サービスのみ対象）。Web UI を使う場合は `docker compose up temporal-ui -d` を別途実行すること。

---

## テスト結果

| 検証項目 | 結果 |
|---|---|
| `awaiting_pr_approval` で停止することを確認 | ✅ |
| `pr_approved = False` で停止中を確認 | ✅ |
| Temporal Web UI から `approve_pr` Signal 送信 | ✅ |
| Signal 受信後に PR 作成まで完走 | ✅ |
| PR URL 取得 | ✅ https://github.com/obataka/temporal-demo/pull/2 |
