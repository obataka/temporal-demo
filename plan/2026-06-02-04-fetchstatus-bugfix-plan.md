# Plan: fetchStatus バグ修正 2件

## Context
報告された2つの問題を修正する。変更ファイルは `web-ui/public/index.html` のみ。

## 問題1: "ネットワークエラー" トーストがポーリング時に毎回出る

**根本原因:**
- `catch (_)` があらゆる例外を "ネットワークエラー" として表示
- ポーリング（5秒毎）も同じ `fetchStatus()` を呼ぶため、初期化中の一時的エラーが5秒ごとにトーストとして出続ける
- 入力欄が空のままポーリングが発火すると "ID を入力してください" warning も5秒ごとに出る副次バグあり

**修正:** `fetchStatus(silent = false)` にパラメータ追加
- `silent=true` のとき: トースト非表示・console.warn のみ
- ポーリング側: `fetchStatus(true)` に変更
- 手動ボタン: `fetchStatus()` のまま（silent=false デフォルト）

## 問題2: ポーリング更新でスクロール位置が末尾に強制移動

**根本原因:** `updateAgentLogs()` が常に `scrollTop = scrollHeight` で末尾スクロール

**修正:** コンテンツ更新「前」に末尾付近（50px以内）か判定し、末尾付近のときのみスクロール

```javascript
const isNearBottom =
  agentLogsContainer.scrollHeight - agentLogsContainer.scrollTop
  <= agentLogsContainer.clientHeight + 50;

// ... textContent 更新後 ...

if (isNearBottom) {
  agentLogsContainer.scrollTop = agentLogsContainer.scrollHeight;
}
```

## 検証
1. `docker compose up --build -d web-ui`
2. ブラウザでコンソールエリアを上スクロール → ポーリングで位置維持を確認
3. トーストが不要なタイミングで出ないことを確認
