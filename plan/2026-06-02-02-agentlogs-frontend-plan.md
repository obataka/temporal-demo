# Plan: agentLogs フロントエンド可視化

## Context
Temporal ワークフローの `get_status` → Hono `/api/status/:workflowId` → フロントエンドの
データパスは開通済み。API は `agentLogs` (camelCase) を返す。
フロントエンドにコンソール風の表示エリアを追加し、定周期ポーリングでリアルタイム更新する。

## 変更ファイル（1ファイル）

`web-ui/public/index.html` のみ変更。

---

### HTML — section ④ を追加（section ③ アクションの直下）

ダーク系コンソール風デザイン:
- `bg-slate-900 rounded-lg p-4 max-h-60 overflow-y-auto`
- ログ本文: `font-mono text-xs text-slate-200 whitespace-pre-wrap`
- プレースホルダー: `font-mono text-xs text-slate-500`
- ヘッダーに「更新中」バッジ（差し戻し中のみ表示）

---

### JavaScript — 追加・変更

**① 要素参照を冒頭に追加**
`agentLogsContainer`, `agentLogsPlaceholder`, `agentLogsContent`, `agentLogsBadge`

**② `updateAgentLogs(logs)` 関数を新設**
- logs が空の場合: placeholder 表示 / content 非表示
- logs がある場合: placeholder 非表示 / content に textContent セット → `scrollTop = scrollHeight` で末尾スクロール

**③ `fetchStatus()` 内で `updateAgentLogs(data.agentLogs ?? '')` を呼ぶ**

**④ ポーリング制御**
- `startPolling()` : `setInterval(fetchStatus, 5000)` — 二重起動防止付き
- `stopPolling()` : `clearInterval` でタイマー解除
- `fetchStatus()` 内で `completed` / `failed` 検知時に `stopPolling()`、それ以外は `startPolling()`
- ワークフロー選択・ID 入力時に `startPolling()` 呼び出し

**⑤ 差し戻し後の「更新中」バッジ表示制御**
- 差し戻し成功後: バッジ表示
- 完了 / ポーリング停止時: バッジ非表示

---

## 検証
1. `docker compose up --build -d web-ui`
2. `http://localhost:3000` をブラウザで開く
3. ワークフロー選択 → コンソールエリアが描画されることを確認
4. JS エラーなし・レイアウト崩れなしを目視確認
