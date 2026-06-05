# Plan: fix_sop_activity.py に CrewAI 協調ロジックを組み込む（土台実装）

## Context

`agent_test.py` で実証した Writer + Reviewer の 2 エージェント協調を、
既存の Temporal Activity `fix_sop_activity` に組み込む。
既存ワークフロー（`sop_workflow.py`）は変更せず、
将来の差し替えを容易にする「土台」として新しい Activity 関数を追加する。

---

## 既存インターフェース確認（変更禁止）

```python
# sop_workflow.py:358-363 の呼び出し方
return await workflow.execute_activity(
    fix_sop_activity,
    args=[sop_text, failures, human_feedback],
    start_to_close_timeout=timedelta(minutes=7),
    retry_policy=LLM_RETRY_POLICY,
)
```

```python
# 現シグネチャ（崩さない）
@activity.defn
async def fix_sop_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
) -> LLMResult:
```

---

## 実装方針

### 変更ファイル: `activities/fix_sop_activity.py`

**追加するもの（既存コードは一切変更しない）:**

#### 1. 定数追加
```python
_CREW_MODEL = "gemini/gemini-2.5-flash"   # crew_activity.py と同一
```

#### 2. プライベートヘルパー `_build_sop_crew(sop_text, failures, human_feedback, llm) -> Crew`

- Writer（SOP 修正担当）: `sop_text + failures + human_feedback` を受け取り修正済み SOP を出力
- Reviewer（セキュリティ・規律レビュー担当）: Writer の出力を `context=[task_write]` で参照し指摘を出力
- `crew_activity.py` の `Agent/Task/Crew` パターンをそのまま踏襲
- `allow_delegation=False`, `verbose=False`

#### 3. 新規 Activity `fix_sop_with_crew_activity`

- シグネチャ: `fix_sop_activity` と同一（`sop_text, failures, human_feedback=""` → `LLMResult`）
- `asyncio.to_thread(crew.kickoff)` で同期ブロッキングを回避
- `LLMResult.text` = `crew_output.tasks_output[0].raw`（Writer の修正済み SOP）
- `LLMResult.model` = `_CREW_MODEL`
- `LLMResult.total_tokens` = `crew_output.token_usage.total_tokens`（`getattr` でデフォルト 0）
- `input_tokens` / `output_tokens` は 0（CrewAI はタスク単位の内訳を返さないため）

---

## 再利用するパターン

| ソース | 再利用箇所 |
|---|---|
| `activities/crew_activity.py:26` | `_CREW_MODEL = "gemini/gemini-2.5-flash"` |
| `activities/crew_activity.py:120-153` | `Agent/Task/Crew` 構築パターン |
| `activities/crew_activity.py:157` | `asyncio.to_thread(crew.kickoff)` |
| `activities/crew_activity.py:160-162` | `token_usage` の `getattr` 取得 |
| `workflows/agent_test.py` | Writer/Reviewer のロール・ゴール・バックストーリー定義 |

---

## 変更ファイル一覧

| ファイル | 操作 | 内容 |
|---|---|---|
| `activities/fix_sop_activity.py` | 追記（既存行は不変） | `_CREW_MODEL` 定数、`_build_sop_crew` ヘルパー、`fix_sop_with_crew_activity` Activity |

※ `sop_workflow.py`・`worker.py`・`core/models.py`・`requirements.txt` への変更なし。

---

## 実装後の確認手順

1. ホストからコンテナへファイルをコピー:
   ```bash
   docker cp activities/fix_sop_activity.py temporal-worker:/app/activities/fix_sop_activity.py
   ```
2. 構文チェック:
   ```bash
   docker exec temporal-worker python3 -m py_compile activities/fix_sop_activity.py && echo OK
   ```
3. ExitCode 0 かつ "OK" が出力されることを確認
