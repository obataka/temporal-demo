# Plan: active_agent バッジ動的制御

## Context
前タスクで配置した `#badge-writer` / `#badge-reviewer` に対し、
API レスポンスの `active_agent`（または `activeAgent`）の値に基づいて
Tailwind クラスをリアルタイムに切り替える JS ロジックを追加する。

## 変更ファイル
- `web-ui/public/index.html`（`<script>` ブロックのみ）

## 実装詳細

### 1. 定数定義（`<script>` ブロック上部の const 宣言群に追加）
```js
const BADGE_STATES = {
  inactive:  { badge: ['bg-slate-800',   'text-slate-500',  'border-slate-700'],  dot: ['bg-slate-600']  },
  writer:    { badge: ['bg-emerald-950', 'text-emerald-400','border-emerald-500'], dot: ['bg-emerald-400'] },
  reviewer:  { badge: ['bg-amber-950',   'text-amber-400',  'border-amber-500'],   dot: ['bg-amber-400']  },
};
```

### 2. `updateAgentBadges(agent)` 関数を `updateAgentLogs` の直後に追加
```js
function updateAgentBadges(agent) {
  const writerEl    = document.getElementById('badge-writer');
  const reviewerEl  = document.getElementById('badge-reviewer');
  const writerDot   = writerEl.querySelector('span');
  const reviewerDot = reviewerEl.querySelector('span');
  const allBadge = Object.values(BADGE_STATES).flatMap(s => s.badge);
  const allDot   = Object.values(BADGE_STATES).flatMap(s => s.dot);

  writerEl.classList.remove(...allBadge);
  reviewerEl.classList.remove(...allBadge);
  writerDot.classList.remove(...allDot);
  reviewerDot.classList.remove(...allDot);

  const writerState   = agent === 'Writer'   ? BADGE_STATES.writer   : BADGE_STATES.inactive;
  const reviewerState = agent === 'Reviewer' ? BADGE_STATES.reviewer : BADGE_STATES.inactive;

  writerEl.classList.add(...writerState.badge);
  writerDot.classList.add(...writerState.dot);
  reviewerEl.classList.add(...reviewerState.badge);
  reviewerDot.classList.add(...reviewerState.dot);
}
```

### 3. `fetchStatus` 成功ハンドラに呼び出しを追加（agentLogs 更新の直後）
```js
// active_agent バッジ更新（snake_case / camelCase 両対応）
const activeAgent = data.active_agent ?? data.activeAgent ?? null;
updateAgentBadges(activeAgent);
```

## ディフェンシブ実装の根拠
- `data.active_agent ?? data.activeAgent ?? null` — Python（snake_case）と Hono 中継（camelCase）の
  どちらが届いても安全にフォールバック（CLAUDE.md の「命名変換とディフェンシブ受信」ルールに準拠）
- 値が `null` / `undefined` / 想定外文字列のいずれでも `inactive` 状態に fallthrough する

## 検証方法
1. Node.js による構文チェック（`node --input-type=module < script_part.js`）
2. `grep -n "updateAgentBadges\|active_agent\|activeAgent"` で挿入箇所を確認
