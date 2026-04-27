# AI ガバナンスにおける外部制御機能の価値

## 概要

Temporal の Signal/Query 機能は、単なる技術的な便利機能ではない。
「制御可能性（Controllability）」と「透明性（Transparency）」という
企業 AI ガバナンスの根幹を支える基盤インフラである。

---

## 1. Signal がガバナンスにもたらす価値

### 問題: AI の暴走をどう止めるか

従来の AI エージェントは、一度起動すると内部状態が不可視なブラックボックスとして動き続ける。
「このエージェントが不適切な方向に進んでいる」と気づいても、止める手段は「プロセスを殺す」しかなかった。

### Signal による解決策

```
企業の監査担当者
        │
        │ inject_human_feedback("規制上の理由でXXXについて言及しないこと")
        ▼
  Temporal Server  ─── イベント履歴に永続記録 ───▶  AI Agent Workflow
        │                                                   │
        │                                           次のLLM呼び出し時に
        │                                           プロンプト先頭に注入
        ▼
  監査ログ（改ざん不可）
```

| Signal | ユースケース | ガバナンス上の意義 |
|--------|-------------|-------------------|
| `inject_human_feedback` | コンプライアンス要件の注入、方針変更の即時反映 | Human-in-the-Loop の実現 |
| `update_task_priority` | コスト高騰時の低優先度タスクの後回し | 動的コスト制御 |
| `add_task` | 緊急タスクの割り込み実行 | ビジネス優先度への即時対応 |
| `stop_agent` | エージェントのグレースフル停止 | 非常停止ボタン（E-Stop） |

### なぜ「プロセスキル」では不十分か

- プロセスキルは即座だが、**処理中のタスクが失われる**
- Signal は「現在のタスクを完了してから停止」というグレースフルな制御が可能
- Signal はイベント履歴に記録されるため、**誰が・いつ・何を指示したかが監査可能**

---

## 2. Query がガバナンスにもたらす価値

### 問題: AI の現在状態をどう把握するか

従来のシステムでは、AIの現在の処理状態を把握するには：
- ログを掘り起こす（遅い、非リアルタイム）
- DBをポーリングする（DB書き込みタイムラグあり）
- エージェントにAPIを生やす（設計コストが高い）

### Query による解決策

```
リスク管理部門のダッシュボード
        │
        │ query("get_live_stats")
        ▼
  Temporal Worker ──▶ return {
                          "tasks_completed": 47,
                          "total_tokens": 125000,      ← リアルタイム（DB書き込み前）
                          "average_latency_ms": 820,
                          "recent_results": [...]
                      }
```

| Query | ユースケース | ガバナンス上の意義 |
|-------|-------------|-------------------|
| `get_status` | 現在何を処理中か確認 | AI の行動の可視化 |
| `get_live_stats` | トークン消費量のリアルタイム監視 | コスト超過の早期検知 |

### DB書き込み前のデータが重要な理由

通常のシステムでは、統計データはタスク完了後にDBに書き込まれる。
つまり、実行中のタスクのデータは観測不可能。

Query は**ワークフローのメモリ上のデータを直接参照**するため、
DBに書き込まれる前のリアルタイムデータを取得できる。
これは、トークン消費量の上限監視やコスト計算において特に重要。

---

## 3. クラッシュ耐性の監査価値

### Temporal のイベントソーシングとは

Temporal はすべての Signal・Activity の結果・Workflow の決定を
**イベントとしてデータベースに永続記録**する。

```
Event History（改ざん不可のログ）:
  #1  WorkflowExecutionStarted
  #2  ActivityTaskScheduled (LLM呼び出し)
  #3  ActivityTaskCompleted
  #4  SignalReceived: inject_human_feedback("規制対応: XXX禁止")  ← 誰が・いつ送ったか記録
  #5  ActivityTaskScheduled (フィードバック適用済みプロンプト)
  ...
```

### クラッシュ後も「指示」が保持される意義

Worker（AIエージェントの実行環境）がクラッシュしても：

1. イベント履歴はTemporalサーバー（分散DB）に保存済み
2. Worker再起動時に履歴を**決定論的に再生**
3. Signal で注入した指示は `self._human_feedback` に復元される
4. **クラッシュの前後で、エージェントの行動指針が変わらない**

これは、AI エージェントを「管理下に置く」ための根本的な保証である。

---

## 4. 企業 AI ガバナンスフレームワークとの対応

| ガバナンス要件 | Temporal の対応機能 |
|--------------|-------------------|
| 制御可能性 (Controllability) | Signal による即時制御 |
| 説明責任 (Accountability) | イベント履歴による監査証跡 |
| 透明性 (Transparency) | Query によるリアルタイム状態取得 |
| 停止可能性 (Corrigibility) | `stop_agent` シグナルによる非常停止 |
| 動的ポリシー適用 | `inject_human_feedback` による方針注入 |
| コスト制御 | `get_live_stats` + `update_task_priority` |

---

## 5. アーキテクチャの全体像

```
┌─────────────────────────────────────────────────────┐
│              Enterprise AI Governance Layer          │
│                                                      │
│  Compliance Team ──────────── Signal: inject_feedback│
│  Risk Management ──────────── Query: get_live_stats  │
│  Operations Team ──────────── Signal: stop_agent     │
│  Cost Controller ──────────── Signal: update_priority│
└──────────────────────┬──────────────────────────────┘
                       │
              Temporal Server (Event Store)
                       │
         ┌─────────────┴──────────────┐
         │    immortal_agent_workflow  │
         │  ┌─────────────────────┐   │
         │  │  Signal Handlers    │   │
         │  │  - add_task         │   │
         │  │  - inject_feedback  │   │
         │  │  - update_priority  │   │
         │  │  - stop_agent       │   │
         │  ├─────────────────────┤   │
         │  │  Query Handlers     │   │
         │  │  - get_status       │   │
         │  │  - get_live_stats   │   │
         │  ├─────────────────────┤   │
         │  │  Main Loop          │   │
         │  │  (wait → process)   │   │
         │  └──────────┬──────────┘   │
         └─────────────┼──────────────┘
                       │ Activity
                  ┌────▼────┐
                  │   LLM   │ (Gemini / Mock)
                  └─────────┘
```

---

## まとめ

Signal/Query を備えた `immortal_agent_workflow` は、
単なる「落ちても復活するエージェント」ではない。

**「いつでも人間が介入・観測・停止できる」** という
AI ガバナンスの本質的な要件を、Temporal のイベントソーシングという
堅牢な基盤の上に実装したものである。

これが、エンタープライズ AI 開発において Temporal が不可欠なインフラである理由だ。
