# Vercel Serverless Functions 対応

## A. System Interaction Flow

```
Vercel Edge
  └── /api/* リクエスト
        └── routes (vercel.json) → web-ui/src/index.ts
              └── handle(app) [hono/vercel]
                    └── Hono Router
                          ├── GET  /health
                          ├── GET  /api/workflows     → getClient() → Temporal gRPC
                          ├── GET  /api/status/:id    → getClient() → wfHandle.query()
                          ├── POST /api/approve       → getClient() → wfHandle.signal()
                          ├── POST /api/reject        → getClient() → wfHandle.signal()
                          └── POST /api/contact       → nodemailer SMTP
```

## B. Responsibility Matrix

| ファイルパス | 変更内容 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `web-ui/src/index.ts` | 修正 | Vercel Node.js ランタイム向けエントリーポイント | `hono/vercel` handle, Temporal Client, nodemailer |
| `vercel.json` | 新規 | `/api/*` → `web-ui/src/index.ts` のルーティング定義 | Vercel Build System |
| `web-ui/package.json` | 修正（devDeps追加） | TypeScript 型チェック用 devDependencies | `typescript`, `@types/node`, `@types/nodemailer` |

## C. Change Intent & Critical Points

### 設計の意図
Bun 専用の `serveStatic` と `export default { port, fetch }` を除去し、Vercel の Node.js ランタイムが解釈できる Named Export 形式（`export const GET/POST = handle(app)`）に変更。`vercel.json` の `builds` + `routes` 構文で `api/` ディレクトリ外のファイルを Serverless Function として認識させる。

### クリティカル・ポイント（最大3点）

1. **`handle` 変数名の衝突を修正済み**  
   `import { handle } from 'hono/vercel'` 追加に伴い、内部で同名変数を使っていた `client.workflow.getHandle()` の返り値を `wfHandle` にリネーム（シャドーイングによるバグ予防）。

2. **静的ファイル配信の変更**  
   `hono/bun` の `serveStatic` を削除。Vercel デプロイ時は `web-ui/public/` を Vercel CDN が配信する（Vercel ダッシュボードで Root Directory を `web-ui/` に設定すること）。ローカル Bun 起動（Docker）は別途対応が必要。

3. **`vercel.json` は `builds` + `routes` 構文を採用**  
   現代的な `rewrites` は `api/` ディレクトリ外へのルーティングが不可なため旧構文を使用。Vercel は両方サポートしており互換性は問題なし。
