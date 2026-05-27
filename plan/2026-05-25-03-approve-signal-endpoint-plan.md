# Plan: POST /api/approve エンドポイント実装

## Context
`web-ui` Hono サーバーに、Temporal ワークフローへ `approve_pr` シグナルを送信する
REST API を追加する。フロントエンドから人間の承認操作を受け付けるための口。

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `web-ui/src/index.ts` | `POST /api/approve` エンドポイントを追加するのみ |

package.json・docker-compose.yaml・Dockerfile の変更は不要。

---

## 実装詳細

### 追加するエンドポイント（`web-ui/src/index.ts` へ追記）

- JSON ボディから `workflowId` を取り出す
- `workflowId` 欠落 → 400（バリデーション）
- `getClient()` → `getHandle(workflowId)` → `handle.signal("approve_pr")`
- 成功 → 200 `{"success": true}`
- ワークフロー未存在・完了済み → 404（Temporal は完了済みへのシグナルも gRPC NOT_FOUND で返す）
- その他 → 500
- `getClient()` とエラー判定ロジックは既存パターン（GET /api/status）をそのまま流用

---

## 検証手順

1. `docker compose up --build web-ui -d`
2. `docker compose logs temporal-web-ui` でインポート/型エラーなし確認
3. `workflowId` なし POST → 400
4. 存在しない ID で POST → 404
