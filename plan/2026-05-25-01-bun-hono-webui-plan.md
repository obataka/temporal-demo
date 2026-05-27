# Plan: Bun + Hono Web UI サーバー構築

## Context
temporal-demo プロジェクトに軽量な Web UI サーバー（Bun + Hono）を追加する。
将来的なワークフロー操作 UI の基盤となる。

## 重要事項：ポート競合の解消
現在 Grafana が `3000:3000` を使用しているため、web-ui を 3000 に割り当てるには
Grafana を `3001:3000` に移動する必要がある。

---

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/package.json` | 新規作成 |
| `web-ui/src/index.ts` | 新規作成 |
| `web-ui/Dockerfile` | 新規作成 |
| `docker-compose.yaml` | grafana ポート変更 + web-ui サービス追加 |

---

## 実装詳細

### 1. `web-ui/package.json`
```json
{
  "name": "web-ui",
  "version": "0.0.1",
  "scripts": {
    "start": "bun run src/index.ts"
  },
  "dependencies": {
    "hono": "^4.7.0"
  }
}
```

### 2. `web-ui/src/index.ts`
```typescript
import { Hono } from "hono";

const app = new Hono();

app.get("/health", (c) => c.json({ status: "ok" }));

export default {
  port: 3000,
  fetch: app.fetch,
};
```
- `Bun.serve` の代わりに `export default { port, fetch }` を使用（Bun ネイティブサーバー形式）

### 3. `web-ui/Dockerfile`
```dockerfile
FROM oven/bun:1-alpine
WORKDIR /app
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile
COPY src ./src
CMD ["bun", "run", "src/index.ts"]
```
- `bun.lockb*` はロックファイルが存在しない初回ビルドでも glob で安全に扱えるよう指定

### 4. `docker-compose.yaml` の変更
**Grafana のポートを変更**（3000 → 3001）:
```yaml
grafana:
  ports:
    - 3001:3000   # 変更
```

**web-ui サービスを追加**:
```yaml
web-ui:
  container_name: temporal-web-ui
  build: ./web-ui
  networks:
    - temporal-network
  ports:
    - 3000:3000
  restart: unless-stopped
```

---

## 検証手順

1. `docker compose up --build web-ui -d` でコンテナ起動
2. `docker compose ps` でステータス確認
3. `curl http://localhost:3000/health` → `{"status":"ok"}` を確認
