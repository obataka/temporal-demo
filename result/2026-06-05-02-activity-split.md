# 案A：Activity 分割リファクタリング 実装結果

作成日: 2026-06-05  
対象設計書: `docs/spike_next_features.md` 案 A 節  
計画書: `plan/2026-06-05-02-activity-split-plan.md`

---

## A. System Interaction Flow

```
【分割後の呼び出し構造（将来のワークフロー実装イメージ）】

sop_generation_workflow._call_fix_decomposed()
  │
  ├─ self._active_agent = "Writer"
  ├─ writer_task_activity(sop_text, failures, human_feedback, attempt)
  │    LLM(temperature=_TEMPERATURE_BY_ROUND[attempt])
  │    Crew([writer], [task_write + urgency])
  │    → LLMResult(text=corrected_sop, agent_logs="")
  │
  ├─ self._active_agent = "Reviewer"
  ├─ reviewer_task_activity(corrected_sop)
  │    LLM(temperature=0.3 固定)
  │    Crew([reviewer], [task_review with corrected_sop in description])
  │    → LLMResult(text=reviewer_output, agent_logs=reviewer_output)
  │
  └─ self._active_agent = None
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `activities/fix_sop_activity.py` | `writer_task_activity` | Writer エージェント単体を起動し修正済み SOP を返す | ワークフロー `_call_fix_decomposed`（将来） |
| `activities/fix_sop_activity.py` | `reviewer_task_activity` | Reviewer エージェント単体を起動し監査結果を返す | ワークフロー `_call_fix_decomposed`（将来） |
| `activities/fix_sop_activity.py` | `fix_sop_with_crew_activity` | 後方互換のため残存（非推奨コメント追記） | 現行 `sop_workflow._call_fix` |
| `worker.py` | `activities` リスト | 新 Activity 2 件を Temporal Worker に登録 | Temporal Server |

---

## C. 設計の意図とクリティカル・ポイント

### 設計の意図

Writer と Reviewer を独立した Activity に分離することで、ワークフロー側が
`_active_agent` フィールドを両 Activity の呼び出しの間で更新できるようになる。
これにより UI が「Writer が執筆中 / Reviewer が監査中」をリアルタイムに表示できる土台が整う。

### クリティカル・ポイント（最大 3 点）

1. **`reviewer_task_activity` は `context=[]` を使わない**  
   元の `_build_sop_crew` では Reviewer の task に `context=[task_write]` を設定し、
   同一 Crew 内の Writer 出力を自動的に参照させていた。分割後は前工程の結果を
   `corrected_sop` 引数として受け取り、description に直接埋め込む設計に変更した。

2. **`fix_sop_with_crew_activity` は削除せず非推奨コメントのみ追記**  
   実行中のワークフローがリプレイで参照する可能性があるため、シグネチャ・実装ともに変更しない。
   `writer_task_activity` / `reviewer_task_activity` への移行はワークフロー側の次スプリントで行う。

3. **`writer_task_activity` の temperature と urgency は案 B の定数テーブルを再利用**  
   `_TEMPERATURE_BY_ROUND` と `_URGENCY_PREFIX_BY_ROUND` は今回新設せず、
   案 B で追加済みのモジュールレベル定数をそのまま参照している。DRY 原則に従い重複なし。

---

## 検証結果

```
docker compose exec worker python3 -m py_compile activities/fix_sop_activity.py
→ OK（exit code 0、出力なし）

docker compose exec worker python3 -m py_compile worker.py
→ OK（exit code 0、出力なし）
```

構文エラー・インポートエラーなし。
