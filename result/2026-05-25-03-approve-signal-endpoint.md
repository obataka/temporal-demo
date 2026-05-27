# POST /api/approve エンドポイント実装

## A. System Interaction Flow

```
HTTP クライアント
  → POST /api/approve  {"workflowId": "sop-xxxx"}
      → バリデーション: workflowId 欠落 → 400
      → getClient() シングルトン（既存）
      → client.workflow.getHandle(workflowId)
      → handle.signal("approve_pr")
          → Temporal Server (temporal:7233)
              → SopGenerationWorkflow.approve_pr()
                  → self._pr_approved = True
      ← 200 {"success": true}
```

エラー時:
- `workflowId` 欠落 → HTTP 400 `{"error":"workflowId is required"}`
- ワークフロー未存在・完了済み → HTTP 404 `{"error":"Workflow not found or already completed",...}`
- その他 → HTTP 500

## B. Responsibility Matrix

| ファイルパス | クラス/関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/src/index.ts` | `POST /api/approve` | ボディ検証 → シグナル送信 → レスポンス | `getClient()` / Temporal Server |
| `web-ui/src/index.ts` | `getClient()` | 既存シングルトン（変更なし）| Temporal gRPC |
| `workflows/sop_workflow.py` | `SopGenerationWorkflow.approve_pr()` | シグナルハンドラ（変更なし）| `self._pr_approved = True` |

## C. 設計の意図とクリティカル・ポイント

### 設計の意図
- `getClient()` とエラー判定ロジックは前回（GET /api/status）と同一パターンを流用し、コードの一貫性を維持
- 変更は `web-ui/src/index.ts` 1ファイルのみ

### クリティカル・ポイント

1. **完了済みワークフローへのシグナル = NOT_FOUND**: Temporal は完了済みワークフローへのシグナルも gRPC NOT_FOUND (code 5) で返す。既存の isNotFound 判定がそのまま機能するため 404 で正しく処理される。
2. **`workflowId` バリデーションを catch 外で実施**: JSON パース失敗（Content-Type 不正など）は Hono のデフォルトエラーハンドリングに委ねる設計。必要なら `c.req.json()` を try で囲む拡張が可能。

## 検証結果

```bash
# workflowId 欠落 → 400
POST /api/approve {}
→ {"error":"workflowId is required"} HTTP:400

# 存在しない ID → 404
POST /api/approve {"workflowId":"nonexistent-id"}
→ {"error":"Workflow not found or already completed","workflowId":"nonexistent-id"} HTTP:404

# コンテナログ: インポートエラー・型エラーなし
Started development server: http://localhost:3000
```
