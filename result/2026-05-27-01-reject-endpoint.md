# result: POST /api/reject エンドポイント追加

実施日: 2026-05-27

---

## A. System Interaction Flow

```
ブラウザ
  → POST /api/reject  { workflowId, feedbackComment }
    → Hono ハンドラ (web-ui/src/index.ts)
      → バリデーション (400 if missing)
      → client.workflow.getHandle(workflowId)
        → handle.signal("reject_with_feedback", { comment: feedbackComment })
          → Temporal Server → Python ワークフロー の reject_with_feedback ハンドラ
  ← 200 { success: true }
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/src/index.ts` | `app.post("/api/reject", ...)` 追加 | リクエストを受け取り reject_with_feedback Signal を送信 | Temporal Server（gRPC） |

## C. Change Intent & Critical Points

### 設計の意図
`POST /api/approve` と同一の構造を踏襲し、差分を最小限に抑えた。
Signal 引数を `{ comment: feedbackComment }` のオブジェクト形式で渡すことで、
Python 側の Signal ハンドラが辞書として受け取れる形式に合わせている。

### クリティカル・ポイント（最大3点）

1. **Signal 引数の形式**: `handle.signal("reject_with_feedback", { comment: feedbackComment })` の第2引数はオブジェクト。Python 側が `info.signal_args[0]["comment"]` でアクセスする前提。
2. **feedbackComment の空文字チェック**: `!feedbackComment` は空文字列 `""` も弾く。空のフィードバックを送っても AI に意味がないため意図的な仕様。
3. **console.error の追加**: `/api/approve` にはなかったが、差し戻しはデバッグの機会が多いと判断してサーバーログへのエラー出力を追加した。

## D. 検証結果

- `docker compose up --build web-ui -d` → ビルドエラーなし、コンテナ起動成功
- `curl http://localhost:3000/health` → `{"status":"ok"}` を確認
