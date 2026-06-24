# Vercel キャッチオールルートへの切り替え

## A. 解消した2つの問題

**問題1: `unknown` ランタイム**
`api/index.ts` に `export default { port: 3000, fetch: app.fetch }` (Bun HTTP サーバー形式) が残っており、Vercel がランタイムを判定できなかった。

**問題2: 404（Honoパスマッチ失敗）**
`rewrites` で `/api/contact` → `/api/index` にリライトすると Hono が受け取るパスが `/api/index` になり `app.post("/api/contact", ...)` にマッチしなかった。

## B. Responsibility Matrix

| ファイル | 変更内容 | 目的 |
|:---|:---|:---|
| `web-ui/api/[[...route]].ts` | 新規作成 | Vercel キャッチオールルート。全 `/api/*` を受け取り Hono がオリジナルパスでルーティング。Bun 用 `export default` を除去 |
| `web-ui/api/index.ts` | 削除 | `[[...route]].ts` に統合 |
| `vercel.json` | `{}` に変更 | キャッチオールルートで不要になったリライト設定を削除 |
| `web-ui/src/index.ts` | 変更なし | Bun/Docker 用として維持 |

## C. Critical Points

1. **`[[...route]]` は省略可キャッチオール** — `/api` 直下から `/api/contact` 等すべてのサブパスを1ファイルで処理。Vercel がリライトを介さずルーティングするのでHonoはオリジナルパスを受け取る。
2. **Bun の `export default` が `unknown` ランタイムの原因だった** — Vercel 専用の `[[...route]].ts` からは完全に除去。`src/index.ts` では維持。
3. **`vercel.json` は空でよい** — ファイルベースルーティングで完結するためリライト設定は不要。

## 検証結果

```
$ npx tsc --noEmit
Exit code: 0 ✅
```

## デプロイ後確認事項

- Vercel Deployments → Resources → Functions: `/api/[[...route]]` が `Node24` で表示されるか
- Vercel Logs → Vercel Function: フォーム送信でカウントが増えるか
