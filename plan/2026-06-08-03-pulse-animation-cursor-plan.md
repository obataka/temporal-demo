# Plan: 明滅アニメーション + タイピングカーソル実装

## Context
前タスクで `active_agent` によるバッジ色切替が完成した。
今回はその上に「生き物感」を与える 2 つのビジュアルエフェクトを追加する。
- エフェクト①: アクティブバッジの小丸に `animate-pulse` を付与して明滅
- エフェクト②: ログコンソール末尾にターミナルカーソル `_` を動的生成・消去

## 変更ファイル
- `web-ui/public/index.html`（`<script>` ブロックのみ）

---

## エフェクト①: バッジ明滅（BADGE_STATES 拡張）

`animate-pulse` を writer / reviewer の `dot` 配列に追加するだけで、
`updateAgentBadges` の既存の "全削除→追加" ロジックがそのまま機能する。
（`allDot` は `Object.values(BADGE_STATES).flatMap(s => s.dot)` で自動生成されるため
 `animate-pulse` も削除対象に含まれ、inactive 時の消し忘れが起きない）

```js
const BADGE_STATES = {
  inactive: { badge: ['bg-slate-800',   'text-slate-500',  'border-slate-700'],  dot: ['bg-slate-600']                    },
  writer:   { badge: ['bg-emerald-950', 'text-emerald-400','border-emerald-500'], dot: ['bg-emerald-400', 'animate-pulse'] },
  reviewer: { badge: ['bg-amber-950',   'text-amber-400',  'border-amber-500'],   dot: ['bg-amber-400',   'animate-pulse'] },
};
```

`updateAgentBadges` 本体の変更: **不要**（既存ロジックで自動対応）

---

## エフェクト②: タイピングカーソル

### 変数（`pollingTimer` の直後に追加）
```js
let typingCursor = null;
```

### `showTypingCursor()` / `hideTypingCursor()` 関数（`updateAgentBadges` の直後に追加）
```js
function showTypingCursor() {
  if (typingCursor) return;
  typingCursor = document.createElement('span');
  typingCursor.className = 'block font-mono text-xs text-slate-400 animate-pulse mt-1 select-none';
  typingCursor.textContent = '_';
  agentLogsContainer.appendChild(typingCursor);
  agentLogsContainer.scrollTop = agentLogsContainer.scrollHeight;
}

function hideTypingCursor() {
  if (!typingCursor) return;
  typingCursor.remove();
  typingCursor = null;
}
```

### `updateAgentBadges` の末尾に呼び出しを追加
```js
// タイピングカーソル制御
if (agent !== null) {
  showTypingCursor();
} else {
  hideTypingCursor();
}
```

---

## Null 安全性チェック

| 操作 | ガード |
|------|--------|
| `showTypingCursor` 重複生成 | `if (typingCursor) return` |
| `hideTypingCursor` 未生成時 remove | `if (!typingCursor) return` |
| `writerEl.querySelector('span')` | badge-writer は常に DOM に存在し子 span も固定構造 |
| `animate-pulse` 消し忘れ | `allDot` に含まれ `classList.remove(...allDot)` で毎回消える |

## 検証方法
1. Node.js `new Function(scriptBlock)` で構文チェック
2. `grep -n "animate-pulse\|typingCursor\|showTypingCursor\|hideTypingCursor"` で挿入確認
