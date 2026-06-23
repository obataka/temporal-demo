# エージェントステータスバッジ追加

## A. System Interaction Flow

```
index.html (④ AI エージェント思考ログ セクション)
  ├── ヘッダー行（h2 + agentLogsBadge）
  ├── [NEW] エージェントステータスバッジ行
  │     ├── #badge-writer  （Writer エージェント用）
  │     └── #badge-reviewer（Reviewer エージェント用）
  └── #agentLogsContainer（漆黒ログコンソール）
```

## B. Responsibility Matrix

| ファイルパス | 要素 / ID | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/public/index.html` | `#badge-writer` | Writer エージェントの思考状態表示（初期：非アクティブ灰色） | 将来の JS ポーリングロジック |
| `web-ui/public/index.html` | `#badge-reviewer` | Reviewer エージェントの思考状態表示（初期：非アクティブ灰色） | 将来の JS ポーリングロジック |

## C. Change Intent & Critical Points

**設計の意図**: バッジは初期状態を「非アクティブ」固定にし、将来の JS から CSS クラスを差し替えてアクティブ状態を表現できる拡張点として設計した。

### クリティカル・ポイント
1. **挿入位置**: `#agentLogsContainer` の直前・同一セクション内に配置。他のセクションを崩さない。
2. **Tailwind クラス構成**: `font-mono text-xs` + `bg-slate-800 text-slate-500 border border-slate-700` で漆黒コンソールと色調を統一した非アクティブ状態。
3. **select-none**: バッジテキストがドラッグ選択されないよう `select-none` を付与し、誤操作を防止。

## 検証結果
- Python `html.parser` によるタグ開閉チェック: **OK（エラーなし）**
- `grep` による挿入位置確認: `badge-writer` (L110) → `badge-reviewer` (L115) → `agentLogsContainer` (L122) の順で正常配置
