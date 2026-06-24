# Plan: Vercel unknown ランタイム修正

## Context

`web-ui/api/index.ts` が `import { serveStatic } from "hono/bun"` を含んでいるため、Vercel のビルドシステムが Bun 固有のインポートを検出し、ランタイムを `unknown` と判定している。`@temporalio/client` は gRPC ネイティブモジュールを使用するため Node.js ランタイムが必須だが、runtime が `unknown` のため関数が正常に実行されず 404 になっている。

Vercel 環境では静的ファイルは `public/` ディレクトリを自動的に配信するため `serveStatic` ミドルウェアは不要。`src/index.ts`（Bun/Docker 用）は変更しない。

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/api/index.ts` | `hono/bun` インポートと `serveStatic` 使用箇所を削除 |
| `web-ui/tsconfig.json` | 新規作成（Vercel Node.js 向け設定） |
| `web-ui/src/index.ts` | **変更なし**（Bun/Docker 用として維持） |

## 実装手順

### Step 1: `web-ui/api/index.ts` の修正

削除する行:
```typescript
import { serveStatic } from "hono/bun";
app.use("/*", serveStatic({ root: "./public" }));
```

### Step 2: `web-ui/tsconfig.json` の新規作成

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true
  },
  "include": ["api/**/*.ts", "src/**/*.ts"]
}
```

### Step 3: TypeScript コンパイル確認

```bash
cd web-ui && npx tsc --noEmit
```

## 検証

1. `npx tsc --noEmit` が ExitCode 0
2. デプロイ後、Vercel Resources → Functions でランタイムが `Node` と表示される
3. Vercel Logs → Function カウントが増える
4. `lp.html` フォーム送信が成功する
