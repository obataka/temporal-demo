# 案A：ワークフロー側 active_agent 状態管理 実装結果

作成日: 2026-06-05  
対象設計書: `docs/spike_next_features.md` 案 A 節  
計画書: `plan/2026-06-05-03-active-agent-workflow-plan.md`

---

## A. System Interaction Flow

```
sop_generation_workflow._call_fix(sop_text, failures, human_feedback)
  │
  ├─ workflow.patched("split-writer-reviewer") == True（新規ワークフロー）
  │   └─ _call_fix_decomposed(sop_text, failures, human_feedback)
  │        │
  │        ├─ self._active_agent = "Writer"
  │        ├─ writer_task_activity(sop_text, failures, human_feedback, fix_attempt)
  │        │    → LLMResult(text=corrected_sop, agent_logs="")
  │        │
  │        ├─ self._active_agent = "Reviewer"
  │        ├─ reviewer_task_activity(corrected_sop)
  │        │    → LLMResult(text=review_log, agent_logs=review_log)
  │        │
  │        ├─ self._active_agent = None
  │        └─ LLMResult(text=corrected_sop, agent_logs=review_log, tokens合算)
  │
  └─ workflow.patched("split-writer-reviewer") == False（旧コード起動済みのリプレイ）
      └─ fix_sop_with_crew_activity(sop_text, failures, human_feedback, fix_attempt)
           → LLMResult（従来通り）

get_status() Query
  → {"active_agent": self._active_agent, ...}
      None | "Writer" | "Reviewer" → Hono → フロントエンド
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `workflows/sop_workflow.py` | `__init__` | `_active_agent: str \| None = None` を追加 | `get_status()`, `_call_fix_decomposed` |
| `workflows/sop_workflow.py` | `get_status()` | `"active_agent": self._active_agent` を戻り値に追加 | Hono `/api/status/:workflowId` |
| `workflows/sop_workflow.py` | `_call_fix` | `workflow.patched()` で新旧コードパスを分岐 | `_call_fix_decomposed`, `fix_sop_with_crew_activity` |
| `workflows/sop_workflow.py` | `_call_fix_decomposed` | Writer→Reviewer の 2 ステップシーケンスを実行し active_agent を更新 | `writer_task_activity`, `reviewer_task_activity` |

---

## C. 設計の意図とクリティカル・ポイント

### 設計の意図

`_active_agent` フィールドを Activity 呼び出しの間で更新することで、
ワークフローの Query ハンドラ `get_status()` が常に最新のエージェント状態を返す。
Hono の `/api/status/:workflowId` が 5 秒ポーリングでこの値を中継するため、
フロントエンドは次のポーリングサイクルで "Writer が処理中" / "Reviewer が処理中" を表示できる。

### クリティカル・ポイント（最大 3 点）

1. **`workflow.patched("split-writer-reviewer")` によるリプレイ安全性**  
   旧コードで起動済みのワークフローは、イベント履歴が `fix_sop_with_crew_activity` の呼び出しを
   記録している。新コードを適用した場合、`workflow.patched()` が `False` を返す旧ブランチへ
   フォールバックすることで、リプレイ時の非決定論エラーを防ぐ。

2. **`_active_agent` は Activity 完了後に確実に `None` にリセットされる**  
   `_call_fix_decomposed` の最後で `self._active_agent = None` を実行するため、
   修正ループ完了後の `get_status()` は `active_agent: null` を返す。
   Activity が例外で失敗した場合は例外がワークフロー側に伝播するため、
   `_active_agent` がセットされたまま Query が来ても「現在処理中のエージェント」として意味のある値を返す。

3. **合成 `LLMResult` のトークン数は Writer + Reviewer の合算**  
   Writer と Reviewer を別々の Activity として呼び出すため、それぞれのトークン使用量を
   `total_tokens` に合算して返す。`agent_logs` には Reviewer の出力のみを格納する（Writer の
   出力は `text` フィールドに格納）。

---

## テスト結果

```
collected 49 items

49 passed in 2.52s
```

デグレードなし。全 49 件一発で Green。
