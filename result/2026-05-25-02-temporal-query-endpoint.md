# GET /api/status/:workflowId エンドポイント実装

## A. System Interaction Flow

```
HTTP クライアント
  → GET /api/status/:workflowId (Hono / web-ui:3000)
      → getClient() シングルトン
          → Connection.connect("temporal:7233") [初回のみ gRPC 接続確立]
          → new Client({ connection })
      → client.workflow.getHandle(workflowId)
      → handle.query("get_status")
          → Temporal Server (temporal:7233)
              → SopGenerationWorkflow.get_status()
                  ↓ returns dict
      ← JSON レスポンス (status / current_phase / current_output / ...)
```

エラー時:
- ワークフロー未存在 → gRPC NOT_FOUND → HTTP 404 `{"error":"Workflow not found","workflowId":"..."}`
- その他エラー → HTTP 500 `{"error":"..."}`

## B. Responsibility Matrix

| ファイルパス | クラス/関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/src/index.ts` | `getClient()` | gRPC 接続シングルトン管理 | Temporal gRPC (temporal:7233) |
| `web-ui/src/index.ts` | `GET /api/status/:workflowId` | ワークフロー Query 呼び出し・レスポンス整形 | `getClient()` / HTTP クライアント |
| `web-ui/package.json` | — | `@temporalio/client@^1.16.2` 追加 | bun install |
| `docker-compose.yaml` | `web-ui.environment` | `TEMPORAL_HOST=temporal:7233` 注入 | コンテナ起動 |
| `workflows/sop_workflow.py` | `SopGenerationWorkflow.get_status()` | Query ハンドラ（変更なし・参照のみ） | Temporal Server |

## C. 設計の意図とクリティカル・ポイント

### 設計の意図
- Python 側の `query_client.py` が `Client.connect → get_workflow_handle → handle.query` のパターンを採用しているため、TypeScript でも同一パターンに揃えた
- `clientPromise` によるシングルトン: リクエスト毎に新規 gRPC 接続を確立するとオーバーヘッドが大きいため、モジュールレベルで Promise をキャッシュし再利用する

### クリティカル・ポイント

1. **Alpine + @temporalio/client 互換性**: `@temporalio/client@1.16.2` は `oven/bun:1-alpine` (musl libc) 上でも動作する（事前検証済み）。base image の変更は不要。
2. **エラー判定の二重チェック**: gRPC status code 5 (NOT_FOUND) と message 文字列の両方で `not found` を判定しているため、SDK バージョンによる挙動差異に対して堅牢。
3. **protobufjs の postinstall ブロック**: `bun install` 時に `protobufjs` の postinstall がブロックされるが、Query 機能には影響しないことを確認済み。

## 検証結果

```bash
# ヘルスチェック
$ curl http://localhost:3000/health
{"status":"ok"}

# 存在しないワークフロー → 404
$ curl -w "\nHTTP_STATUS:%{http_code}" http://localhost:3000/api/status/nonexistent-workflow-id
{"error":"Workflow not found","workflowId":"nonexistent-workflow-id"}
HTTP_STATUS:404

# 実ワークフロー (sop-df8be811) → 全フィールド正常返却
$ curl http://localhost:3000/api/status/sop-df8be811
{
  "approved_phases": ["outline"],
  "attempt_in_phase": 0,
  "current_output": "...",
  "current_phase": "draft",
  "fix_attempt": 0,
  "phase_label": "...",
  "pr_approved": false,
  "pr_url": null,
  "status": "awaiting_approval",
  "validation_result": null
}
```
