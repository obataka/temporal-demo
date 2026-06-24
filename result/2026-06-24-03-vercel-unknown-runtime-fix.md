# Vercel unknown ランタイム修正

## A. 原因

`web-ui/api/index.ts` に `import { serveStatic } from "hono/bun"` が含まれていた。
Vercel のビルドシステムが Bun 固有のインポートを検出し、ランタイムを `unknown` と判定。
ランタイムが不明なため関数が正常に実行されず 404 になっていた。

## B. Responsibility Matrix

| ファイル | 変更内容 | 目的 |
|:---|:---|:---|
| `web-ui/api/index.ts` | `hono/bun` インポートと `app.use("/*", serveStatic(...))` を削除 | Vercel が Node.js ランタイムを正しく認識できるようにする |
| `web-ui/tsconfig.json` | 新規作成（Vercel Node.js 向け設定） | TypeScript を正しくコンパイルさせる |
| `web-ui/src/index.ts` | 変更なし | Bun/Docker ローカル用として維持 |

## C. Critical Points

1. **`hono/bun` は Vercel 環境で使用不可** — Vercel 上では静的ファイルは `public/` ディレクトリを自動配信するため `serveStatic` ミドルウェア自体が不要。
2. **`src/index.ts` は変更しない** — Bun/Docker ローカル環境は `serveStatic` が必要なため維持。
3. **`@temporalio/client` は Node.js 必須** — gRPC ネイティブモジュールを使用するため Edge Runtime では動作しない。

## 検証結果

```
$ npx tsc --noEmit
Exit code: 0 ✅
```
