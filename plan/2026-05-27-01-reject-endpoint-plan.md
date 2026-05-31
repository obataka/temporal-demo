# Plan: POST /api/reject エンドポイント追加

## Context
差し戻し機能のバックエンドとして、ブラウザから AI への追加修正指示を Temporal Signal 経由で送る
`POST /api/reject` エンドポイントを実装する。
既存の `POST /api/approve` と同一のパターンに従う。

## 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `web-ui/src/index.ts` | `POST /api/reject` ハンドラを追加 |

## 実装詳細

### リクエスト仕様
```json
{ "workflowId": "...", "feedbackComment": "..." }
```

### バリデーション（400）
- `workflowId` が空 → `{ "error": "workflowId is required" }`
- `feedbackComment` が空文字列または未指定 → `{ "error": "feedbackComment is required" }`

### 正常系
```typescript
await handle.signal("reject_with_feedback", { comment: feedbackComment });
return c.json({ success: true });
```

### エラーハンドリング（approve と同一ロジック）
- gRPC NOT_FOUND（code 5 または message に "not found"）→ 404
- その他 → 500

### 挿入位置
`app.post("/api/approve", ...)` ブロックの直後（`app.use("/*", ...)` の前）

## 検証手順
1. `docker compose up --build webui -d` でコンテナを再ビルド・起動
2. ログに型エラー・起動エラーがないことを確認
3. `/health` エンドポイントが 200 を返すことで起動成功を確認
