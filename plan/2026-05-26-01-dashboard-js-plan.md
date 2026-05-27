# Plan: Dashboard JavaScript ロジック実装

## Context

`web-ui/public/index.html` はすでに HTML/CSS として完成しているが、ボタンのクリックに対する API 連携ロジックが未実装。Hono サーバー (`web-ui/src/index.ts`) には以下のエンドポイントが実装済み：

- `GET /api/status/:workflowId` → `{ current_phase, phase_label, attempt_in_phase, status, approved_phases, current_output }`
  - `status === "awaiting_pr_approval"` のとき承認待ち
  - `current_output` に SOP テキストが入る
- `POST /api/approve` (body: `{ workflowId }`) → `{ success: true }`

## 変更ファイル

- `web-ui/public/index.html` のみ（`</body>` 直前に `<script>` ブロックを追加）

## 実装内容

### 1. DOM 初期状態制御

`approveBtn` を起動時に `disabled` 状態にし、不活性スタイルを付与。

### 2. トースト通知システム

Tailwind を使った軽量トーストを JS のみで実装。`showToast(message, type)` 関数：
- `type: 'success'` → 緑背景
- `type: 'error'` → 赤背景
- 3秒後に自動消滅

### 3. fetchStatus() — 「状態を取得」ボタン

```
fetchStatusBtn.click
  → workflowId を input から取得（空なら警告トーストで中断）
  → GET /api/status/:workflowId
  → 成功: statusBadge / sopPreview を更新
         status === "awaiting_pr_approval" → approveBtn を有効化
  → 404: 「ワークフローが見つかりません」エラートースト
  → 500: 「サーバーエラーが発生しました」エラートースト
```

statusBadge の色分け（Tailwind クラス切替）:
| current_phase | 背景/文字色 |
|---|---|
| awaiting_pr_approval / 承認待ち系 | yellow |
| completed | green |
| その他（生成中など） | indigo |

### 4. approveWorkflow() — 「承認」ボタン

```
approveBtn.click
  → POST /api/approve { workflowId }
  → 成功: 「承認を送信しました」成功トースト、approveBtn を再度 disabled に
  → 404: 「ワークフローが見つからないか、すでに完了しています」エラートースト
  → その他エラー: 「承認送信に失敗しました」エラートースト
```

### 5. ローディング状態

fetchStatusBtn クリック中はボタンテキストを「取得中…」に変えて `disabled` にし、完了後に戻す。

## 検証手順

1. `docker compose up` でサーバー起動
2. `http://localhost:3000` にアクセス
3. DevTools Console にエラーがないことを確認
4. 存在しない workflowId を入力 → 404 エラートーストが表示されること
5. 有効な workflowId を入力 → ステータス・SOP プレビューが表示されること
6. `status = awaiting_pr_approval` のとき承認ボタンが有効になること
