# Plan: ワークフロー一覧 API + フロントエンドドロップダウン

## Context

ダッシュボードで Workflow ID を手入力する必要があり不便。
`GET /api/workflows` を追加し、フロントエンドにドロップダウンを設けて選択だけで操作できるようにする。

## 変更ファイル

1. `web-ui/src/index.ts` — 新エンドポイント追加
2. `web-ui/public/index.html` — セクション追加 + JS ロジック追加

## 事前確認（既存コード調査結果）

- `client.workflow.list({ pageSize })` が AsyncIterable を返す（Python で疎通確認済み）
- ステータスは数値 proto enum: `1=RUNNING, 2=COMPLETED, 3=FAILED, 4=CANCELLED, 5=TERMINATED, 6=CONTINUED_AS_NEW, 7=TIMED_OUT`
- 既存パターン: `getClient()` シングルトン、try/catch エラー返却

## 1. バックエンド（`web-ui/src/index.ts`）

`GET /api/workflows?limit=N`（デフォルト 30・上限 100）

```typescript
const STATUS_LABEL: Record<number, string> = {
  1: "RUNNING", 2: "COMPLETED", 3: "FAILED",
  4: "CANCELLED", 5: "TERMINATED",
  6: "CONTINUED_AS_NEW", 7: "TIMED_OUT",
};

app.get("/api/workflows", async (c) => {
  const limit = Math.min(Number(c.req.query("limit") ?? 30), 100);
  const client = await getClient();
  const items = [];
  for await (const wf of client.workflow.list({ pageSize: limit })) {
    items.push({
      workflowId:   wf.workflowId,
      status:       STATUS_LABEL[wf.status as unknown as number] ?? "UNKNOWN",
      startTime:    wf.startTime?.toISOString() ?? null,
      closeTime:    wf.closeTime?.toISOString() ?? null,
      workflowType: wf.type,
    });
  }
  return c.json(items);
});
```

## 2. フロントエンド（`web-ui/public/index.html`）

### 追加 HTML（既存 Section ① の直前）

`<select id="workflowSelect">` ドロップダウンと「↻ 更新」ボタン。

### 追加 JS

- `loadWorkflowList()`: `/api/workflows?limit=30` を fetch → select に option 生成
  - option 表示: `workflowId  🟡 実行中  2026-05-26 10:20`（日本語ロケール）
- `workflowSelect.change`: 選択 → `workflowIdInput.value = id` → `fetchStatus()` 自動実行
- `refreshListBtn.click`: `loadWorkflowList()` を呼ぶ
- `window.load`: `loadWorkflowList()` を呼ぶ

## 3. 検証

1. `docker compose build web-ui && docker compose up -d web-ui`
2. `curl -s http://localhost:3000/api/workflows | python3 -m json.tool | head -30`
3. ブラウザで http://localhost:3000 → ドロップダウン確認 → 選択して自動取得確認
