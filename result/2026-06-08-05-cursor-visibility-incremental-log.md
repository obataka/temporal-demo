# カーソル可視性修正 + インクリメンタルログ表示

## A. System Interaction Flow

```
修正①: カーソル可視性
  showTypingCursor()
    agentLogsPlaceholder.add('hidden')   ← [NEW] プレースホルダーを隠す
    → <span>_</span> を append → 視認可能
  hideTypingCursor()
    typingCursor.remove() → null
    agentLogsContent.contains('hidden') なら  ← [NEW] プレースホルダー復元
      agentLogsPlaceholder.remove('hidden')

修正②: インクリメンタルログ
  sop_workflow.py
    _call_fix_decomposed()
      _agent_status_log = "[Writer] 修正案を生成中..."   ← [NEW]
      await writer_task_activity(...)
      _agent_status_log = "[Reviewer] セキュリティ・品質チェック中..."  ← [NEW]
      await reviewer_task_activity(...)
      _agent_status_log = ""   ← [NEW]
    get_status() → { ..., agent_status_log: self._agent_status_log }  ← [NEW]

  index.html fetchStatus()
    activeAgent    = data.active_agent ?? data.activeAgent ?? null
    agentLogs      = data.agentLogs ?? ''
    agentStatusLog = data.agent_status_log ?? data.agentStatusLog ?? ''
    displayLogs = active中 かつ statusLog あり → 末尾付加  ← [NEW]
    updateAgentLogs(displayLogs)
    updateAgentBadges(activeAgent)
```

## B. Responsibility Matrix

| ファイルパス | 要素 / メソッド | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `workflows/sop_workflow.py` | `_agent_status_log` (L98) | Activity 実行中の暫定ステータス文保持 | `get_status()` |
| `workflows/sop_workflow.py` | `_call_fix_decomposed` (L410,419,428) | Writer/Reviewer 各 Activity 前後に設定・クリア | `get_status()` |
| `workflows/sop_workflow.py` | `get_status()` (L151) | `agent_status_log` を Query レスポンスに追加 | Hono API |
| `web-ui/public/index.html` | `showTypingCursor()` (L215) | プレースホルダー隠蔽を追加 | `agentLogsPlaceholder` |
| `web-ui/public/index.html` | `hideTypingCursor()` (L228) | ログ本文がない場合はプレースホルダー復元 | `agentLogsContent` |
| `web-ui/public/index.html` | `fetchStatus` 成功ハンドラ (L341-350) | `agentStatusLog` を `displayLogs` に合成して表示 | `updateAgentLogs` |

## C. Change Intent & Critical Points

**設計の意図**: `_agent_status_log` は Activity が実行中のみ保持する「揮発性ステータス文」。
完了後は `""` にリセットされるため、フロントエンドは次ポーリングで自動的に本来の `agentLogs` に切り替わる。

### クリティカル・ポイント
1. **Temporal 決定論との整合性**: `_agent_status_log` への代入は外部入力に依存しない定数文字列なのでリプレイ安全
2. **`displayLogs` の合成ルール**: `agentLogs` が空なら `agentStatusLog` のみ、空でなければ `\n\n---\n\n` で末尾付加。2サイクル目も過去ログが消えない
3. **プレースホルダー復元条件**: `hideTypingCursor` は `agentLogsContent.classList.contains('hidden')` を確認してからプレースホルダーを戻す。ログがある状態でプレースホルダーが再表示される副作用を防ぐ

## 検証結果
- JS 構文チェック: **OK**
- Python 構文チェック: **OK**
- Worker 再ビルド・起動: **OK** (`temporal_connected` + `worker_started` 確認)
