# Plan: カーソル可視性修正 + インクリメンタルログ表示

## Context
E2E 監査で 2 つの UX 問題が発覚した。
1. **カーソルが見えない**: `showTypingCursor()` が `_` を append しても
   プレースホルダー「現在、エージェントの思考ログはありません。」が残ったまま
2. **ログが一括**: `_agent_logs` は Activity 完了後にしか更新されない設計のため、
   Writer/Reviewer の実行中（最大数分間）ログコンソールが空白のまま

## 変更ファイル
- `workflows/sop_workflow.py`（バックエンド）
- `web-ui/public/index.html`（フロントエンド）

---

## 修正① カーソル可視性（index.html）

### `showTypingCursor()` に 1 行追加
`agentLogsContainer.appendChild(typingCursor)` の前に
`agentLogsPlaceholder.classList.add('hidden')` を挿入してプレースホルダーを隠す。

### `hideTypingCursor()` にプレースホルダー復元を追加
`typingCursor = null` の後に、`agentLogsContent.classList.contains('hidden')` なら
（本文ログが空）`agentLogsPlaceholder.classList.remove('hidden')` でプレースホルダーを戻す。

---

## 修正② インクリメンタルログ（sop_workflow.py + index.html）

### A. sop_workflow.py — `_agent_status_log` フィールド追加

**`__init__`:**
```python
self._agent_status_log: str = ""
```

**`_call_fix_decomposed` — 各 Activity 前後に設定・クリア:**
```python
self._active_agent = "Writer"
self._agent_status_log = "[Writer] 修正案を生成中..."
writer_result = await workflow.execute_activity(writer_task_activity, ...)

self._active_agent = "Reviewer"
self._agent_status_log = "[Reviewer] セキュリティ・品質チェック中..."
reviewer_result = await workflow.execute_activity(reviewer_task_activity, ...)

self._active_agent = None
self._agent_status_log = ""
```

**`get_status()` の return dict:**
```python
"agent_status_log": self._agent_status_log,
```

Temporal 決定論チェック: 外部入力に依存しない定数代入 → リプレイ安全 ✅

### B. index.html — fetchStatus 成功ハンドラを更新

既存の `updateAgentLogs(data.agentLogs ?? '')` と
`updateAgentBadges(data.active_agent ?? ...)` の 2 行を以下に差し替え:

```js
// agentLogs 更新（active_agent 実行中はステータスログを末尾に付加）
const activeAgent    = data.active_agent ?? data.activeAgent ?? null;
const agentLogs      = data.agentLogs ?? '';
const agentStatusLog = data.agent_status_log ?? data.agentStatusLog ?? '';

let displayLogs = agentLogs;
if (activeAgent && agentStatusLog) {
  displayLogs = agentLogs
    ? `${agentLogs}\n\n---\n\n${agentStatusLog}`
    : agentStatusLog;
}
updateAgentLogs(displayLogs);
updateAgentBadges(activeAgent);
```

---

## 期待する UI 動作（修正後）

| タイミング | ログコンソール表示 |
|---|---|
| Agent 起動直後（次ポーリング） | `[Writer] 修正案を生成中...` + `_` 点滅 |
| Writer 完了・Reviewer 開始後 | `[Reviewer] セキュリティ・品質チェック中...` + `_` 点滅 |
| 両 Agent 完了後 | Reviewer 本文ログ（`_` 消える） |
| 2 サイクル目差し戻し時 | `前回ログ\n---\n[Writer] 修正案を生成中...` + `_` 点滅 |

---

## 検証方法
1. Node.js `new Function(scriptBlock)` で構文チェック
2. `grep` で挿入箇所を確認
3. E2E: `reject_with_feedback` でサイクルを誘発しブラウザで目視確認
