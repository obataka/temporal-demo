# Dashboard JavaScript ロジック実装

## A. System Interaction Flow

```
ブラウザ
  → fetchStatusBtn.click
      → GET /api/status/:workflowId  (web-ui/src/index.ts)
          → Temporal Query "get_status"  (workflows/sop_workflow.py)
          ← { current_phase, phase_label, status, current_output }
      ← statusBadge 更新 / sopPreview 更新
         status==="awaiting_pr_approval" → approveBtn 有効化

  → approveBtn.click
      → POST /api/approve { workflowId }  (web-ui/src/index.ts)
          → Temporal Signal "approve_pr"  (workflows/sop_workflow.py)
      ← showToast("承認を送信しました")
         approveBtn 再無効化
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/public/index.html` | `<script>` ブロック追加 | API 連携・UI 制御の全ロジック | `/api/status`, `/api/approve` |
| `web-ui/public/index.html` | `approveBtn` に `disabled` 属性追加 | 初期状態を無効化 | JS で動的制御 |
| `web-ui/public/index.html` | `#toastContainer` div 追加 | トースト通知の描画コンテナ | `showToast()` |

## C. 実装した関数一覧

| 関数名 | 役割 |
| :--- | :--- |
| `showToast(message, type)` | success/error/warning トーストを 3 秒表示 |
| `applyBadgeStyle(phase, status)` | ステータスに応じた Tailwind クラスをバッジに適用 |
| `setApproveEnabled(enabled)` | 承認ボタンの有効/無効とスタイルを切替 |
| `fetchStatus()` | GET /api/status/:id → バッジ・プレビュー・ボタン更新 |
| `approveWorkflow()` | POST /api/approve → トースト表示・ボタン無効化 |

## D. 設計の意図・クリティカルポイント

1. **`currentWorkflowId` の保持**: `fetchStatus()` 成功時に変数へ保存し、`approveWorkflow()` はそれを参照する。入力欄を空にした後でも承認が送れるように分離した。

2. **承認後の再無効化**: 承認成功後は `setApproveEnabled(false)` を呼んでボタンを無効化する。二重送信防止（Signal の重複送信は冪等でないため）。

3. **バッジ色のクラス衝突回避**: `applyBadgeStyle()` 冒頭で既存の色クラスを全削除してから新しいクラスを付与する。Tailwind の purge 問題を避けるため CDN 版を使用しているためクラスは動的に生成可能。

## E. 検証結果

- `node --check` による JS 構文チェック: **エラーなし（RC: 0）**
- `curl http://localhost:3000/health`: `{"status":"ok"}`
- `curl http://localhost:3000/api/status/nonexistent`: `{"error":"Workflow not found",...}` (404)
- Docker コンテナ再ビルド・再起動後、HTML にスクリプト関数 22 ブロックが確認済み
