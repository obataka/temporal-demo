# Plan: 静的ファイル配信 + ダッシュボード HTML 雛形

## Context
`web-ui` Hono サーバーに静的ファイル配信を追加し、ブラウザから `/` にアクセスすると
ダッシュボード画面が表示されるようにする。

## 事前確認済み事項
- `serveStatic` は `hono/bun` から import 可能（Alpine 上で動作確認済み）
- Dockerfile が現在 `src/` のみコピーしているため `public/` の追加が必要

---

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/src/index.ts` | `serveStatic` を追加（API ルートの後に `/*` でマウント） |
| `web-ui/public/index.html` | 新規作成（Tailwind CDN + ダッシュボード雛形） |
| `web-ui/Dockerfile` | `COPY public ./public` を追加 |

---

## 実装詳細

### 1. `web-ui/src/index.ts`
`import { serveStatic } from "hono/bun"` を追加し、
既存 API ルートの後に `app.use("/*", serveStatic({ root: "./public" }))` を追記。
API ルートが優先され、それ以外は public/ から配信される。

### 2. `web-ui/public/index.html`
Tailwind CSS CDN + 3要素のシングルカラムレイアウト：
- ワークフローID 入力エリア
- ステータス + SOP プレビューエリア
- 「GitHub PR 作成を承認する」ボタン

### 3. `web-ui/Dockerfile`
`COPY public ./public` を `COPY src ./src` の後に追加。

---

## 検証手順
1. `docker compose up --build web-ui -d`
2. `docker logs temporal-web-ui` でエラーなし確認
3. `curl http://localhost:3000/` で HTML 返却確認
4. ブラウザで `http://localhost:3000` を開き画面表示確認
5. `curl http://localhost:3000/health` → `{"status":"ok"}` で API 継続動作確認
