# 静的ファイル配信 + ダッシュボード HTML 雛形

## A. System Interaction Flow

```
ブラウザ
  → GET /                          (Hono serveStatic)
      → ./public/index.html を返却
  → GET /health                    (既存 API ルート — 引き続き動作)
  → GET /api/status/:workflowId    (既存 API ルート — 引き続き動作)
  → POST /api/approve              (既存 API ルート — 引き続き動作)
```

ルート優先順: API ルート (`/health`, `/api/*`) → `/*` (serveStatic フォールバック)

## B. Responsibility Matrix

| ファイルパス | クラス/関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/src/index.ts` | `serveStatic` ミドルウェア | `./public/` 以下の静的ファイルを配信 | ブラウザ |
| `web-ui/public/index.html` | — | ダッシュボード雛形（Tailwind CDN）| ブラウザ |
| `web-ui/Dockerfile` | `COPY public ./public` | ビルド時に public/ をイメージへ含める | docker build |

## C. 設計の意図とクリティカル・ポイント

### 設計の意図
- `serveStatic` を API ルートの**後**に `/*` でマウントすることで、既存エンドポイントの優先度を維持
- `hono/bun` の `serveStatic` を採用（Node.js 系の `@hono/node-server/serve-static` は Bun では不要）

### クリティカル・ポイント

1. **Dockerfile への `COPY public ./public` 追加が必須**: 追加しないとコンテナ内に `public/` が存在せず、`/` へのアクセスで 404 になる
2. **serveStatic の `root` は実行時のカレントディレクトリ相対**: `CMD ["bun", "run", "src/index.ts"]` で `WORKDIR /app` が起点になるため `root: "./public"` は `/app/public/` を指す
3. **3要素の ID**: `workflowIdInput` / `fetchStatusBtn` / `statusBadge` / `sopPreview` / `approveBtn` — 今後 JS でこれらを操作して API と繋ぐ想定

## 検証結果

```bash
# HTML 配信確認
$ curl -s http://localhost:3000/ | head -3
<!DOCTYPE html>
<html lang="ja">
<head>

# API ルート継続動作確認
$ curl http://localhost:3000/health
{"status":"ok"}

# コンテナログ
Started development server: http://localhost:3000
```

ブラウザで `http://localhost:3000` を開くと Tailwind CSS が適用されたダッシュボード画面が表示される。
