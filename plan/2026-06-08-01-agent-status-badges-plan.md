# Plan: エージェントステータスバッジ追加

## Context
マルチエージェント（Writer / Reviewer）の思考状態をリアルタイムに可視化するため、
既存の AI エージェント思考ログセクション（`#agentLogsContainer`）の直上に
2 つのステータスバッジを追加する。

## 変更ファイル
- `web-ui/public/index.html` のみ（1 ファイル）

## 変更箇所
`<!-- ④ AI エージェント思考ログ -->` セクション内、
ヘッダー `div` の閉じタグ（`agentLogsBadge` を含む行）の直後 ＝
`<div id="agentLogsContainer"...` の直前に以下を挿入する。

```html
<!-- エージェントステータスバッジ -->
<div class="flex gap-3 mb-3">
  <span id="badge-writer"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono
               bg-slate-800 text-slate-500 border border-slate-700 select-none">
    <span class="inline-block w-1.5 h-1.5 rounded-full bg-slate-600"></span>
    Writer
  </span>
  <span id="badge-reviewer"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono
               bg-slate-800 text-slate-500 border border-slate-700 select-none">
    <span class="inline-block w-1.5 h-1.5 rounded-full bg-slate-600"></span>
    Reviewer
  </span>
</div>
```

### デザイン仕様
| 属性 | 値 |
|------|-----|
| レイアウト | `flex gap-3`（横並び） |
| フォント | `font-mono text-xs` |
| 背景 | `bg-slate-800`（漆黒に近いグレー） |
| テキスト | `text-slate-500`（薄いグレー） |
| ボーダー | `border border-slate-700` |
| インジケーター | `w-1.5 h-1.5 rounded-full bg-slate-600`（小丸） |

## 検証方法
1. HTML を目視で確認（タグの閉じ忘れ・入れ子の崩れがないか）
2. `grep -n "badge-writer\|badge-reviewer"` でマークアップが正確に挿入されているか確認
