# agentLogs フロントエンド可視化

**実施日時:** 2026-06-02  
**変更ファイル:** `web-ui/public/index.html` のみ

---

## A. System Interaction Flow

```
setInterval(5000)
  → fetchStatus()
      GET /api/status/:workflowId
        → Hono: handle.query("get_status")
            → sop_generation_workflow.get_status()
                → {"agent_logs": "Reviewer出力..."}
        ← {agentLogs: "Reviewer出力..."}   ← snake_case→camelCase 変換済み
      → updateAgentLogs(data.agentLogs)
          → agentLogsContent.textContent = logs
          → agentLogsContainer.scrollTop = scrollHeight  (末尾オートスクロール)
      → data.status === "completed" → stopPolling()
      → それ以外                   → startPolling() (二重起動防止付き)

rejectWorkflow()
  POST /api/reject
  → 成功 → agentLogsBadge.classList.remove('hidden')  ("更新中" バッジ表示)

stopPolling()
  → agentLogsBadge.classList.add('hidden')
```

---

## B. Responsibility Matrix

| 箇所 | 変更内容 | 目的 |
|:---|:---|:---|
| HTML section ④ | `agentLogsContainer` / `agentLogsPlaceholder` / `agentLogsContent` / `agentLogsBadge` を追加 | ダーク系コンソール UI の配置 |
| JS 変数宣言 | 上記4要素の ref + `pollingTimer = null` を追加 | DOM 参照とタイマー管理 |
| `updateAgentLogs(logs)` | 新規関数 — logs の有無でプレースホルダー/コンテンツを切替・末尾スクロール | ログ描画ロジックの集約 |
| `startPolling()` / `stopPolling()` | 新規関数 — `setInterval` / `clearInterval` の二重起動防止ラッパー | ポーリング制御 |
| `fetchStatus()` | `updateAgentLogs(data.agentLogs ?? '')` 呼び出し + ポーリング制御を追加 | ステータス取得に連動したログ更新 |
| `rejectWorkflow()` | 送信成功後に `agentLogsBadge` を表示 | 差し戻し中の更新中インジケーター |
| `workflowSelect` change | `stopPolling()` を追加（ワークフロー切替時にタイマーをリセット） | 別ワークフローへの切替で二重ポーリング防止 |

---

## C. 設計の意図とクリティカルポイント

**設計の意図:** `fetchStatus()` を単一の真実の源として、agentLogs 更新・ポーリング制御・ボタン制御をすべて同関数内に集約した。既存の手動取得フローとポーリングが同一コードパスを通ることで、動作の一貫性を確保した。

**クリティカルポイント（最大3点）:**

1. **二重ポーリング防止**: `startPolling()` は `pollingTimer` が null のときのみ `setInterval` を張る。ワークフロー切替時は `stopPolling()` でリセットしてから再開する。これがないと 5 秒ごとに並列リクエストが増殖する。

2. **`agentLogs` キー名**: Hono API は Python 側の `agent_logs` を `agentLogs` (camelCase) に変換して返す（`index.ts:53-58` の既存ロジック）。フロントエンドは `data.agentLogs` のみ参照すれば十分。

3. **完了検知の2重条件**: `data.status === 'completed'` と `data.current_phase === 'completed'` の両方を確認している。ワークフロー完了時にどちらのフィールドが先に確定するかは実行タイミングに依存するため、どちらか一方の確認だけでは漏れが生じる可能性がある。

## 検証結果

- `docker compose up --build -d web-ui` でコンテナ再ビルド完了
- `curl http://localhost:3000/` でコンソールエリア (`agentLogsContainer`, `bg-slate-900` 等) の全 HTML 要素と JS ロジックが正しく配信されていることを確認
- `node -e` による JS 構文検査: **構文エラーなし**
