# Plan: Vercel api/ ディレクトリ対応リストラクチャリング

## Context

Vercel の Root Directory を `web-ui` に設定した状態で、古い `builds` + `routes` 形式の `vercel.json` を使っているため、`/api/contact` などへの POST リクエストが 404 になっている。Vercel は `api/` ディレクトリ内のファイルをサーバーレス関数として自動認識するため、そのファイルベースルーティング規約に合わせる。

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/api/index.ts` | 新規作成（`src/index.ts` のコピー） |
| `vercel.json`（リポジトリルート） | 旧形式 → 新形式に書き換え |
| `web-ui/src/index.ts` | **変更なし**（ローカル Docker/Bun 用として維持） |

## 実装手順

### Step 1: `web-ui/api/index.ts` の作成

- `web-ui/src/index.ts` の内容をそのままコピー
- **インポートパスの変更は不要**（すべて npm パッケージからのインポートのみ。ローカル相対パスなし）
- `export const GET = handle(app)` / `export const POST = handle(app)` は既存のまま維持（Vercel の Named Exports 規約に適合済み）
- `export default { port: 3000, fetch: app.fetch }` も維持（Bun ローカル用）

### Step 2: ルートの `vercel.json` 書き換え

現在:
```json
{
  "builds": [{ "src": "src/index.ts", "use": "@vercel/node" }],
  "routes": [{ "src": "/api/(.*)", "dest": "src/index.ts" }]
}
```

変更後:
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api" }
  ]
}
```

- `builds` / `routes` は旧形式（Vercel v1）。`rewrites` は現行の推奨形式
- `destination: "/api"` → Root Directory が `web-ui` のとき、`web-ui/api/index.ts` を指す

### Step 3: TypeScript コンパイル確認

```bash
cd web-ui && npx tsc --noEmit
```

ExitCode 0 を確認する。

## 注意点

- `serveStatic({ root: "./public" })` は `hono/bun` からのインポートで、Vercel の Node.js ランタイムでは動作しない可能性があるが、これは既存の問題であり今回のスコープ外
- `web-ui/src/index.ts` は削除しない（`Dockerfile` の `bun run src/index.ts` が依存）
- `package.json` の変更は不要

## 検証

1. `npx tsc --noEmit` が ExitCode 0 で終了する
2. `web-ui/api/index.ts` が存在し、全 API ルートを含んでいる
3. `vercel.json` が `rewrites` 形式になっている
