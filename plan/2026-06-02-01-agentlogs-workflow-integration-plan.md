# Plan: agentLogs 結合実装

## Context
Hono API 側に先行実装済みの `agentLogs` 受け皿に向けて、Temporal ワークフロー側から
CrewAI の Reviewer 出力（思考ログ）を `get_status` クエリで返せるようにする。

## 変更ファイル（4ファイル）

### 1. `core/models.py`
`LLMResult` dataclass にデフォルト空文字のフィールドを末尾追加。

```python
agent_logs: str = ""   # Reviewer の出力ログ（CrewAI）
```

デフォルトあり → 既存の呼び出し側はすべてキーワード引数のため後方互換。

### 2. `activities/fix_sop_activity.py`
`fix_sop_with_crew_activity` の返り値生成部分に Reviewer 出力を詰める。

```python
reviewer_log = ""
if len(crew_output.tasks_output) > 1:
    reviewer_log = crew_output.tasks_output[1].raw or ""

return LLMResult(
    text=corrected_sop,
    ...
    agent_logs=reviewer_log,
)
```

### 3. `workflows/sop_workflow.py`

**`__init__`** に追加:
```python
self._agent_logs: list[str] = []
```

**`get_status`** の返却 dict に追加:
```python
"agent_logs": "\n\n---\n\n".join(self._agent_logs) if self._agent_logs else "",
```

**`run()`** — `_call_fix()` を呼ぶ2箇所（人間フィードバック注入パスと通常ループ）の直後:
```python
fix_result = await self._call_fix(...)
if fix_result.agent_logs:
    self._agent_logs.append(fix_result.agent_logs)
```

### 4. `tests/test_fix_sop_activity.py`
既存 43 件を壊さず 2 件追加（合計 45 件）:

- `test_fix_sop_with_crew_activity_returns_agent_logs`
  `tasks_output[1].raw` が `result.agent_logs` に入ることを確認。

- `test_fix_sop_with_crew_activity_agent_logs_empty_when_single_task_output`
  `tasks_output` が1件のみの場合、`agent_logs == ""` を確認。

## 検証
```
docker exec temporal-worker python -m pytest tests/ -v 2>&1 | tail -20
```
全件 PASS（45 件）を確認して完了。
