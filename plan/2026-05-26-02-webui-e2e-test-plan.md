# Plan: Web UI 結合動作確認テスト（web_ui_e2e_test.py）

## Context

JavaScript ロジックを実装した `web-ui/public/index.html` が Hono API と正しく連携することを
結合テストで確認する。具体的には：

1. `GET /api/status/:workflowId` が正しいレスポンスを返し、
2. `POST /api/approve` がワークフローに `approve_pr` Signal を送信し、
3. ワークフローが `awaiting_pr_approval` → `completed` へ正常遷移すること

を curl で HTTP レイヤーから検証する。

## 机上デバッグ結果（実行前チェック）

| チェック項目 | 結果 |
|---|---|
| DUMMY_SOURCE_CODE の禁止用語（未定/確認中/作成中） | 問題なし |
| DUMMY_SOURCE_CODE の TODO/TBD | 問題なし |
| 使用モデル | gemini-2.5-flash-lite（高クォータ枠） |
| 実行中ワークフロー | `sop-df8be811`（別フロー draft 待ち。本テストとは独立） |

## 新規ファイル

- `web_ui_e2e_test.py`（プロジェクトルート）

## sop_e2e_demo.py からの再利用箇所

- `DUMMY_SOURCE_CODE`（禁止用語なし・チェック済み）をそのままコピー
- Phase 4 + PR Gate ポーリングロジック
- `GitHubParams(require_approval=True)` 設定
- Phase 1–3 自動承認ループ（`approve_step` Signal）

## 実装内容

### Step 1: ワークフロー起動
```python
handle = await client.start_workflow(
    sop_generation_workflow.run,
    args=[TOPIC, DUMMY_SOURCE_CODE, github_params],
    id=f"sop-webui-e2e-{uuid.uuid4().hex[:8]}",
    task_queue="llm-task-queue",
)
```

### Step 2: Phase 1–3 自動承認（Python Temporal Client 経由）
`outline` → `draft` → `review` の各フェーズで `awaiting_approval` を待ち、
空文字の `approve_step` Signal を送信。

### Step 3: Phase 4 + PR Gate 待機
`awaiting_pr_approval` になるまでポーリング。

### Step 4: Web UI API 結合テスト（curl 呼び出し）

- **テスト A**: GET /api/status/:workflowId → 200, status="awaiting_pr_approval", current_output 非 null
- **テスト B**: GET /api/status/nonexistent → 404
- **テスト C**: POST /api/approve → { success: true }

### Step 5: ワークフロー完走確認
`completed` になるまでポーリングし、`pr_url` を表示。

### Step 6: 結果サマリー出力
- Web UI テスト A/B/C の PASS/FAIL
- 総所要時間、PR URL

## 検証手順

1. `python web_ui_e2e_test.py` を実行
2. Step 4 の curl 結果で PASS を確認
3. Step 5 で PR URL を確認
