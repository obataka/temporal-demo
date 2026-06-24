# Plan: Vercel キャッチオールルートへの切り替えによる 404 完全解消

## Context（2問題の同時解消）

**問題1: `unknown` ランタイム**
`web-ui/api/index.ts` に `export default { port: 3000, fetch: app.fetch }` が残っている。これは Bun HTTP サーバーの起動形式で、Vercel がランタイムを `unknown` と判定する原因。

**問題2: 404（パスマッチ失敗）**
`rewrites` で `/api/contact` → `/api/index` にリライトすると Hono が受け取るパスが `/api/index` になり `app.post("/api/contact", ...)` にマッチしない。

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/api/[[...route]].ts` | 新規作成 |
| `web-ui/api/index.ts` | 削除 |
| `vercel.json` | `{}` に簡略化 |
| `web-ui/src/index.ts` | 変更なし |

## 実装手順

### Step 1: `web-ui/api/[[...route]].ts` の作成
`api/index.ts` の内容から以下のみ削除:
```typescript
// Bun HTTP server (local Docker)
export default { port: 3000, fetch: app.fetch };
```

### Step 2: `web-ui/api/index.ts` を削除

### Step 3: `vercel.json` を `{}` に変更

### Step 4: `npx tsc --noEmit` で ExitCode 0 確認

## 期待される結果

- Vercel Functions: `/api/[[...route]]` が `Node24` で表示
- Function ログカウントが増加
- `/api/contact` POST が成功
