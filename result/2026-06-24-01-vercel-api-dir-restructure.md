# Vercel api/ ディレクトリ対応リストラクチャリング

## A. System Interaction Flow

```
Vercel Deploy
  → Root Directory: web-ui
  → auto-discover: web-ui/api/index.ts  (Serverless Function)
  → vercel.json rewrites: /api/(.*) → /api
  → requests to /api/contact, /api/workflows, etc. → api/index.ts が処理
```

## B. Responsibility Matrix

| ファイルパス | 変更内容 | 処理の目的・役割 |
|:---|:---|:---|
| `web-ui/api/index.ts` | **新規作成** | Vercel サーバーレス関数エントリーポイント。全 API ルート（`/api/contact`, `/api/workflows`, `/api/status/:id`, `/api/approve`, `/api/reject`, `/health`）を含む。`hono/vercel` の `handle()` で Named Exports (`GET`, `POST`) を公開。 |
| `vercel.json`（リポジトリルート） | **書き換え** | 旧形式 `builds`+`routes` → 新形式 `rewrites` に変更。`/api/(.*)` を `/api` （= `web-ui/api/index.ts`）にルーティング。 |
| `web-ui/src/index.ts` | **変更なし** | ローカル Docker/Bun 用エントリーポイント（`Dockerfile` が `bun run src/index.ts` で参照）。 |

## C. Change Intent & Critical Points

**なぜこの設計か:**
Vercel の Root Directory を `web-ui` に設定した場合、Vercel は `web-ui/api/` ディレクトリをファイルベースルーティングでサーバーレス関数として自動認識する。旧 `builds`+`routes` 形式は Vercel v1 の設定形式であり、現行では `rewrites` が推奨される。

**クリティカル・ポイント（最大3点）:**

1. **`src/index.ts` は削除していない** — `Dockerfile` が `bun run src/index.ts` で参照しているため、Docker ローカル環境を壊さないよう維持した。

2. **`@types/ms` 不足エラーは既存問題** — `npx tsc --noEmit` で `@temporalio/common` 内部の型定義エラーが出るが、これは今回の変更前から存在する依存関係の問題。`--skipLibCheck` 付きでは ExitCode 0 を確認済み。

3. **`serveStatic({ root: "./public" })` は Vercel 非対応** — `hono/bun` の `serveStatic` は Bun ランタイム用であり、Vercel の Node.js ランタイムでは動作しない。静的ファイル配信は Vercel の静的ホスティング（`public/` フォルダ自動認識）に委ねることが望ましい。今回スコープ外のため未修正。

## 検証結果

```
$ npx tsc --noEmit --target esnext --module nodenext --moduleResolution nodenext --strict --skipLibCheck api/index.ts
Exit code: 0 ✅
```

- `web-ui/api/index.ts` 作成済み（7.7KB、全 API ルート含む）
- `vercel.json` を `rewrites` 形式に更新済み
