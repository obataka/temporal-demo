# 案B：ラウンド数 × temperature 動的チューニング 実装結果

作成日: 2026-06-05  
対象設計書: `docs/spike_next_features.md` 案 B 節  
計画書: `plan/2026-06-05-01-temperature-tuning-plan.md`

---

## A. System Interaction Flow

```
sop_generation_workflow._call_fix(sop_text, failures, human_feedback)
  │  self._fix_attempt を第 4 引数として追加
  ▼
fix_sop_with_crew_activity(sop_text, failures, human_feedback, attempt)
  │  _TEMPERATURE_BY_ROUND[attempt] → temperature を決定
  │  LLM(model, api_key, temperature=temperature) を生成
  │  _build_sop_crew(sop_text, failures, human_feedback, llm, attempt)
  │    _URGENCY_PREFIX_BY_ROUND[attempt] → urgency を決定
  │    task_write.description の末尾に urgency を注入
  │    Crew(writer, reviewer, tasks=[task_write, task_review]) を返す
  ▼
crew.kickoff() → LLMResult(text=corrected_sop, agent_logs=reviewer_log, ...)
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `activities/fix_sop_activity.py` | `_TEMPERATURE_BY_ROUND` | attempt → temperature のルックアップテーブル | `fix_sop_with_crew_activity` |
| `activities/fix_sop_activity.py` | `_URGENCY_PREFIX_BY_ROUND` | attempt → urgency 文字列のルックアップテーブル | `_build_sop_crew` |
| `activities/fix_sop_activity.py` | `_build_sop_crew` | `attempt` を受け取り urgency を task_write に注入して Crew を構築 | `fix_sop_with_crew_activity` |
| `activities/fix_sop_activity.py` | `fix_sop_with_crew_activity` | `attempt` を受け取り temperature 計算後 LLM を生成、`_build_sop_crew` に attempt をリレー | `sop_workflow._call_fix` |
| `workflows/sop_workflow.py` | `_call_fix` | `self._fix_attempt` を `args` 末尾に追加して渡す | `fix_sop_with_crew_activity` |
| `tests/test_fix_sop_activity.py` | 新規 4 件 + 既存修正 1 件 | temperature/urgency テーブル値検証・attempt リレー確認・後方互換確認 | — |

---

## C. 設計の意図とクリティカル・ポイント

### 設計の意図

差し戻しが繰り返されるたびに LLM が「同じ答えを繰り返す」問題を、Activity 内部の温度テーブルと urgency プレフィックスで解決する。ワークフロー側は純粋な整数 `self._fix_attempt` を渡すだけで、非決定論的な温度計算は Activity 内部に閉じているため Temporal の決定論制約に違反しない。

### クリティカル・ポイント（最大 3 点）

1. **`attempt` はデフォルト値 `0` で後方互換を維持**  
   `fix_sop_with_crew_activity` と `_build_sop_crew` の両方に `attempt: int = 0` を付与。既存の呼び出し元（旧ワークフロー実行中のリプレイを含む）は変更なしで動作する。

2. **temperature の決定と LLM 生成は Activity 内部に完全に閉じている**  
   ワークフロー内で temperature を計算すると Temporal の非決定論制約に違反する。`_TEMPERATURE_BY_ROUND.get(attempt, 0.9)` は Activity 内部の純粋な辞書引きなので安全。

3. **既存テスト `test_fix_sop_with_crew_activity_passes_args_to_crew` の引数数変化**  
   `_build_sop_crew` のシグネチャに `attempt` が増えたため、`assert_called_once_with` の末尾に `0`（デフォルト値）を追加している。このテストの修正を忘れると既存テストが FAIL するため要注意。

---

## テスト結果

```
collected 49 items （既存 45 件 + 新規 4 件）

49 passed in 1.80s
```

デグレードなし。全件一発で Green。
