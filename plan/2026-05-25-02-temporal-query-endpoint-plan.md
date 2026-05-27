# Plan: GET /api/status/:workflowId エンドポイント実装

## Context
`web-ui` Hono サーバーに Temporal ワークフローの状態を返す REST API を追加する。
Python 側の `query_client.py` が `Client.connect → get_workflow_handle → handle.query("get_status")` で同一操作を行っており、
TypeScript でも同じパターンを採用する。

## 技術的確認済み事項
- `@temporalio/client@1.16.2` は `oven/bun:1-alpine` で動作する（import OK・Client インスタンス生成 OK）
- `protobufjs` の postinstall がブロックされるが機能に影響なし
- Alpine のままで OK（Dockerfile の base image 変更不要）

---

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/package.json` | `@temporalio/client` 追加 |
| `web-ui/src/index.ts` | シングルトン Client + `/api/status/:workflowId` エンドポイント追加 |
| `docker-compose.yaml` | web-ui サービスに `TEMPORAL_HOST` 環境変数追加 |

---

## 実装詳細

### 1. `web-ui/package.json`
```json
{
  "name": "web-ui",
  "version": "0.0.1",
  "scripts": { "start": "bun run src/index.ts" },
  "dependencies": {
    "hono": "^4.7.0",
    "@temporalio/client": "^1.16.2"
  }
}
```

### 2. `web-ui/src/index.ts`
シングルトンパターンで gRPC 接続を確立し、`/api/status/:workflowId` で `get_status` クエリを呼ぶ。

- `clientPromise` によるシングルトン: コンテナ起動時に一度だけ gRPC 接続を確立し、リクエスト毎に再接続しない
- エラー判定: gRPC status code 5 (NOT_FOUND) または message 文字列で 404 を返す
- `get_status` クエリの返却型は `sop_workflow.py:105-117` に基づく（status / current_phase / phase_label / attempt_in_phase / current_output / approved_phases / fix_attempt / validation_result / pr_url / pr_approved）

### 3. `docker-compose.yaml` (web-ui サービスへ追記)
```yaml
web-ui:
  environment:
    - TEMPORAL_HOST=temporal:7233
```

---

## 検証手順

1. `docker compose up --build web-ui -d`
2. `curl http://localhost:3000/health` → `{"status":"ok"}`
3. 存在しない ID でエラー確認: `curl http://localhost:3000/api/status/nonexistent` → `{"error":"Workflow not found",...}` (404)
4. （任意）実ワークフロー起動後に `curl http://localhost:3000/api/status/<実際のID>` で全フィールド確認
