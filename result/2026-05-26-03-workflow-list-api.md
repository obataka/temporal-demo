# ワークフロー一覧 API + フロントエンドドロップダウン

## A. System Interaction Flow

```
ブラウザ (window.load / ↻ 更新ボタン)
  → GET /api/workflows?limit=30  (web-ui/src/index.ts)
      → client.workflow.list({ pageSize: 30 })
      ← AsyncIterable<WorkflowExecutionInfo>
          { workflowId, status.name, startTime, closeTime, workflowType }
      ← JSON 配列

  → <select id="workflowSelect"> に option 動的生成
      option: "sop-df8be811  🟡 実行中  05/13 12:20"

  ユーザーが option を選択
  → workflowIdInput.value = id
  → fetchStatus() 自動実行
      → GET /api/status/:workflowId
      ← statusBadge / sopPreview / approveBtn 更新
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/src/index.ts` | `GET /api/workflows` 追加 | ワークフロー一覧を取得して JSON 返却 | `client.workflow.list()` |
| `web-ui/public/index.html` | Section ⓪ HTML 追加 | `<select>` + 「↻ 更新」ボタン | JS `loadWorkflowList()` |
| `web-ui/public/index.html` | `loadWorkflowList()` 追加 | API fetch → option 生成 | `/api/workflows` |
| `web-ui/public/index.html` | `workflowSelect.change` ハンドラ追加 | 選択 → input 同期 → `fetchStatus()` | `fetchStatus()` |

## C. 設計の意図・クリティカルポイント

1. **`wf.status` の型**: TypeScript SDK では `wf.status` は `{ code: number, name: string }` オブジェクト。
   `wf.status.name` で文字列を取得する必要があった（数値マップ方式は不正解）。
   コンテナ内で実際の型を `bun -e` で確認してから修正した。

2. **`window.load` で自動フェッチ**: ページ表示と同時にリストを取得するため UX を向上。
   エラー時はトーストを表示して select を「取得失敗」に戻す。

3. **`select.change` → `fetchStatus()` 自動連鎖**: ドロップダウン選択 → 入力欄同期 → 状態取得まで
   ワンアクションで完結する。既存の `fetchStatus()` を再利用してコードを最小に保った。

## D. 検証結果

```
GET /api/workflows
→ HTTP 200
[
  { "workflowId": "sop-df8be811",       "status": "RUNNING",    "startTime": "2026-05-13T03:20:04.119Z", ... },
  { "workflowId": "sop-webui-e2e-d96474cf", "status": "COMPLETED", "startTime": "2026-05-26T01:20:32.235Z", ... }
]

node --check (JS 構文チェック): RC=0（エラーなし）
docker compose build → up: 正常完了
```
