# Plan: Hono API — agentLogs フィールド中継拡張

## Context

マルチエージェントの「思考ログ」を将来フロントエンドに表示するため、
Hono の `GET /api/status/:workflowId` を拡張する。
Temporal の `get_status` クエリから `agentLogs` / `agent_logs` が返ってきた場合は
そのまま中継し、まだ返ってこない古いワークフローでは空文字を返す堅牢な枠組みを作る。

---

## 変更ファイル

`web-ui/src/index.ts` の `GET /api/status/:workflowId` ハンドラのみ修正。

---

## 現状（index.ts:45-63）

```typescript
const status = await handle.query<Record<string, unknown>>("get_status");
return c.json(status);   // ← raw 素通し、agentLogs は保証なし
```

---

## 実装方針

`status` を素通しする前に `agentLogs` フィールドを抽出・正規化して spread する:

```typescript
const status = await handle.query<Record<string, unknown>>("get_status");

// Python ワークフローは snake_case で返す可能性があるため両方チェック
const agentLogs: string =
  typeof status["agentLogs"] === "string"
    ? status["agentLogs"]
    : typeof status["agent_logs"] === "string"
    ? status["agent_logs"]
    : "";

return c.json({ ...status, agentLogs });
```

- `{ ...status, agentLogs }` — 既存フィールドを全て保持しつつ `agentLogs` を上書き/追加
- `typeof ... === "string"` — undefined・null・非文字列を安全に除外
- デフォルト `""` — 古いワークフローや未実装時に undefined にならない

---

## 変更ファイル一覧

| ファイル | 操作 | 内容 |
|---|---|---|
| `web-ui/src/index.ts` | 修正（5行追加、return 1行変更） | `agentLogs` 抽出・正規化と spread 返却 |

※ `docker-compose.yaml`・Python 側・その他ファイルへの変更なし。

---

## 実装後の確認手順

```bash
# サービス名確認済み: web-ui
docker compose up --build web-ui -d

# ヘルスチェック
curl -s http://localhost:3000/health
# 期待: {"status":"ok"}
```
