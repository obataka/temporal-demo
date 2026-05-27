# Bun + Hono Web UI サーバー構築

## A. System Interaction Flow

```
Docker Compose
  └── web-ui サービス (port 3000)
        └── oven/bun:1-alpine コンテナ
              └── bun run src/index.ts
                    └── Hono app
                          └── GET /health → {"status":"ok"}
```

ネットワーク: `temporal-network`（Temporal サーバーと同一ネットワーク）

## B. Responsibility Matrix

| ファイルパス | クラス/関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/src/index.ts` | Hono app / `/health` | ヘルスチェックエンドポイント | HTTP クライアント |
| `web-ui/package.json` | — | Bun プロジェクト設定・依存関係（hono ^4.7.0） | `bun install` |
| `web-ui/Dockerfile` | — | `oven/bun:1-alpine` ベースのコンテナイメージ定義 | docker compose build |
| `docker-compose.yaml` | `web-ui` サービス | ポート 3000 マッピング・temporal-network 接続 | temporal サーバー |
| `docker-compose.yaml` | `grafana` サービス | ポートを 3000→3001 に変更（競合解消） | prometheus |

## C. 設計の意図とクリティカル・ポイント

### 設計の意図
- `Bun.serve()` ではなく `export default { port, fetch }` を採用。Bun のネイティブサーバー形式であり、Hono の公式推奨パターン。
- `bun.lockb*`（glob）で COPY することで、ロックファイル未生成状態でも `--frozen-lockfile` が機能する（ロックファイルがない場合は通常インストールにフォールバックされる）。
- Grafana のポートを `3001:3000` に変更したため、Grafana へのアクセス URL が `http://localhost:3001` に変わった。

### クリティカル・ポイント

1. **Grafana アクセス URL の変更**: Grafana は `http://localhost:3001` でアクセスする（旧: 3000）。
2. **temporal-network への所属**: `web-ui` は `temporal-network` に接続済みのため、コンテナ内から `temporal:7233` へ直接アクセス可能。
3. **`restart: unless-stopped`**: `on-failure` ではなく `unless-stopped` を採用。手動停止後に自動再起動しないよう制御。

## 検証結果

```
$ curl http://localhost:3000/health
{"status":"ok"}
```

コンテナステータス: `Up`（`0.0.0.0:3000->3000/tcp`）
