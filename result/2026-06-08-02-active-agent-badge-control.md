# active_agent バッジ動的制御

## A. System Interaction Flow

```
fetchStatus() 成功ハンドラ（L308〜）
  ├── updateAgentLogs(...)
  ├── updateAgentBadges(data.active_agent ?? data.activeAgent ?? null)  ← [NEW]
  │     ├── BADGE_STATES 定数で全クラスを管理
  │     ├── classList.remove() で全ステートをリセット
  │     └── agent 値に応じて writer / reviewer / inactive を適用
  └── setApproveEnabled / setRejectEnabled
```

## B. Responsibility Matrix

| ファイルパス | 要素 / 関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/public/index.html` | `BADGE_STATES` (L152) | 3 状態（inactive / writer / reviewer）のクラスセット定数 | `updateAgentBadges` |
| `web-ui/public/index.html` | `updateAgentBadges(agent)` (L182) | バッジ本体・ドットの classList を一括切替 | `fetchStatus` から呼出 |
| `web-ui/public/index.html` | `fetchStatus` 成功ハンドラ (L316) | `active_agent ?? activeAgent ?? null` を抽出して渡す | `updateAgentBadges` |

## C. Change Intent & Critical Points

**設計の意図**: 状態クラスを定数オブジェクトに集約し、
`classList.remove(全クラス) → classList.add(対象クラス)` のパターンで
副作用なくトグルできるようにした。

### クリティカル・ポイント
1. **ディフェンシブフォールバック**: `data.active_agent ?? data.activeAgent ?? null` により
   Python（snake_case）・Hono 中継（camelCase）・未送信（null）のすべてに対応。
2. **ドットの個別制御**: バッジ親要素の `text-*` は子 span には伝播しないため、
   `writerEl.querySelector('span')` でドット span を個別に取得して `bg-*` も切替。
3. **全クラス一括削除**: `Object.values(BADGE_STATES).flatMap(s => s.badge)` で定数から
   削除対象クラスを自動生成しているため、状態追加時に削除リストのメンテが不要。

## 検証結果
- Node.js `new Function(scriptBlock)` による構文チェック: **OK（エラーなし）**
- `grep` による挿入確認:
  - `BADGE_STATES` 定義: L152
  - `updateAgentBadges` 関数: L182
  - `fetchStatus` 内呼び出し: L316
