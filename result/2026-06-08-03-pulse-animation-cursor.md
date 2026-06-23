# 明滅アニメーション + タイピングカーソル実装

## A. System Interaction Flow

```
updateAgentBadges(agent)
  ├── classList.remove(allBadge / allDot)   ← animate-pulse も allDot に含まれ確実に削除
  ├── classList.add(writerState / reviewerState)  ← active 時は animate-pulse も同時追加
  ├── agent !== null → showTypingCursor()
  │     └── typingCursor が null なら <span>_ を agentLogsContainer に appendChild
  └── agent === null → hideTypingCursor()
        └── typingCursor.remove() → typingCursor = null
```

## B. Responsibility Matrix

| ファイルパス | 要素 / 変数 / 関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/public/index.html` | `BADGE_STATES` (L152) | `animate-pulse` をアクティブ状態の dot クラスに含める | `updateAgentBadges` |
| `web-ui/public/index.html` | `typingCursor` (L151) | カーソル span への参照を保持（null = 非表示） | `showTypingCursor` / `hideTypingCursor` |
| `web-ui/public/index.html` | `showTypingCursor()` (L213) | カーソル span を生成・追加・スクロール | `updateAgentBadges` から呼出 |
| `web-ui/public/index.html` | `hideTypingCursor()` (L222) | カーソル span を remove して変数を null 化 | `updateAgentBadges` から呼出 |

## C. Change Intent & Critical Points

**設計の意図**: 既存の "全クラス削除→対象クラス追加" パターンを壊さず、
`animate-pulse` を `dot` 配列に追加するだけでエフェクト①を実現。
カーソルは変数 `typingCursor` で DOM ノードへの参照を一本管理し、
生成・削除の両端にガード節を置いて二重生成・空振り削除を防止した。

### クリティカル・ポイント
1. **`animate-pulse` 消し忘れ防止**: `allDot = flatMap(s => s.dot)` に `animate-pulse` が自動的に含まれるため、
   inactive 遷移時に `classList.remove(...allDot)` で確実に除去される。手動管理不要。
2. **`typingCursor` null ガード**: `showTypingCursor` は `if (typingCursor) return` でポーリング毎の重複 append を防ぎ、
   `hideTypingCursor` は `if (!typingCursor) return` で存在しない要素への `.remove()` 呼び出しを防ぐ。
3. **カーソル初回表示時の自動スクロール**: `appendChild` 直後に `scrollTop = scrollHeight` を実行し、
   カーソルが画面外に隠れないようにした（後続ポーリングの `updateAgentLogs` も自動スクロール対象に含む）。

## 検証結果
- Node.js `new Function(scriptBlock)` 構文チェック: **OK（エラーなし）**
- `grep` による挿入確認:
  - `typingCursor` 変数: L151
  - `animate-pulse` in BADGE_STATES: L155, L156
  - `showTypingCursor` 呼び出し: L206 / 関数定義: L213
  - `hideTypingCursor` 呼び出し: L208 / 関数定義: L222
