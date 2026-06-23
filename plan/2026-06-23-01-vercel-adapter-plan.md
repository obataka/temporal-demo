# Plan: Vercel Serverless Functions 対応

## Context
現在の `web-ui/src/index.ts` は Bun 専用の `hono/bun` アダプターを使用しており、Vercel の Node.js ランタイムでは動作しない。  
`hono/vercel` アダプターへ切り替え、`vercel.json` でルーティングを設定して Vercel Serverless Functions として動作させる。

---

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|:---|:---|:---|
| `web-ui/src/index.ts` | 修正 | Bun依存を除去、hono/vercel アダプターに差し替え |
| `vercel.json` | 新規 | `/api/*` → `web-ui/src/index.ts` のルーティング設定 |

---

## Step 1: `web-ui/src/index.ts` の修正

### 削除
```typescript
import { serveStatic } from "hono/bun"; // Bun専用・Node.jsで動作しない
// ...
app.use("/*", serveStatic({ root: "./public" })); // Vercel がCDNで静的ファイルを配信するため不要
export default { port: 3000, fetch: app.fetch }; // Bun専用起動形式
```

### 追加
```typescript
import { handle } from 'hono/vercel'
// ...（既存ルーティングはそのまま）...
export const POST = handle(app)
export const GET = handle(app)
```

> `handle()` は Hono v4.x に同梱済み（追加パッケージ不要）。

---

## Step 2: `vercel.json` の新規作成（プロジェクトルート）

`builds` + `routes` 構文でルーティングを設定する。  
`rewrites` は `api/` ディレクトリ外のファイルへのルーティングができないため、`builds`/`routes` を使用。

```json
{
  "builds": [
    {
      "src": "web-ui/src/index.ts",
      "use": "@vercel/node"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/web-ui/src/index.ts"
    }
  ]
}
```

---

## 注意点

- **静的ファイル配信**: `serveStatic` 削除後、`web-ui/public/` 内のファイルは Vercel の CDN が自動配信する（Vercel ダッシュボードの Root Directory を `web-ui/` に設定すること）。
- **ローカル Bun 開発**: `export default { port, fetch }` を削除するため、`bun run src/index.ts` での直接起動は不可となる。Docker Compose の `web-ui` サービスは影響を受ける可能性がある（本 plan のスコープ外）。
- **Temporal gRPC接続**: Vercel Serverless では `clientPromise` のシングルトンはコールドスタートごとにリセットされる。接続再確立は自動だが、初回リクエストにレイテンシが生じる（本 plan のスコープ外）。

---

## 検証方法

1. TypeScript 構文チェック: `cd web-ui && npx tsc --noEmit`（tsconfig.json が存在すれば）
2. Vercel CLI でのローカル動作確認: `vercel dev`（vercel CLI インストール済みの場合）
3. デプロイ後: `curl https://<project>.vercel.app/api/contact -X POST -H "Content-Type: application/json" -d '{"name":"test","company":"test","email":"test@test.com"}'` → `400` または `200` が返ること
