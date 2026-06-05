# agentLogs 結合実装

**実施日時:** 2026-06-02  
**テスト結果:** 45件 / 45件 PASS

---

## A. System Interaction Flow

```
fix_sop_with_crew_activity()
  → crew.kickoff()
      tasks_output[0].raw  → LLMResult.text      (Writer の修正済み SOP)
      tasks_output[1].raw  → LLMResult.agent_logs (Reviewer の出力ログ) ← 追加

sop_generation_workflow.run()
  → _call_fix() の返値 fix_result
      fix_result.agent_logs が空でなければ self._agent_logs.append()  ← 追加（2箇所）

sop_generation_workflow.get_status()
  → {"agent_logs": "\n\n---\n\n".join(self._agent_logs)}  ← 追加
     （ログ未発生時は ""）
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `core/models.py` | `LLMResult` | `agent_logs: str = ""` フィールド追加（デフォルト空文字） | 全 Activity の返り値 |
| `activities/fix_sop_activity.py` | `fix_sop_with_crew_activity` | `tasks_output[1].raw` を `agent_logs` に格納して返す | `sop_generation_workflow._call_fix` |
| `workflows/sop_workflow.py` | `__init__` | `self._agent_logs: list[str] = []` の初期化追加 | — |
| `workflows/sop_workflow.py` | `run` | `_call_fix()` 返値の `agent_logs` を `self._agent_logs` に蓄積（2箇所） | `fix_sop_with_crew_activity` |
| `workflows/sop_workflow.py` | `get_status` | `"agent_logs"` キーを返却 dict に追加 | Hono API / デモスクリプト |
| `tests/test_fix_sop_activity.py` | 新規2件 | Reviewer ログ格納・1件時の空文字を検証 | — |

---

## C. 設計の意図とクリティカルポイント

**設計の意図:** `LLMResult` に `agent_logs` をデフォルト空文字で追加することで、既存の `fix_sop_activity`（Gemini 単体版）や他の Activity の返り値に影響を与えず、CrewAI パスのみ Reviewer ログを流せるようにした。

**クリティカルポイント（最大3点）:**

1. **後方互換性**: `agent_logs: str = ""` をデフォルトフィールドとして末尾に追加しているため、既存の `LLMResult(text=..., model=..., ...)` 形式の構築コードは変更不要。

2. **2箇所の収集漏れに注意**: `run()` 内で `_call_fix()` は「人間フィードバック注入パス」と「通常バリデーションループ」の2箇所で呼ばれる。どちらも `agent_logs` を収集しないとログが欠落する。

3. **Hono 側キー名**: `get_status` は `"agent_logs"` (snake_case) で返す。Hono 側が `agentLogs` (camelCase) を期待する場合は API 層での変換が必要（本実装の範囲外）。
