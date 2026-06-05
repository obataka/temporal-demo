# 案A：Activity 分割リファクタリング 実装計画

作成日: 2026-06-05  
対象ファイル: `activities/fix_sop_activity.py`, `worker.py`  
設計根拠: `docs/spike_next_features.md` 案 A 節

---

## Context

現行の `fix_sop_with_crew_activity` は Writer と Reviewer を単一 Activity 内で実行するため、
ワークフロー側から各エージェントの状態（「Writer が執筆中」「Reviewer が監査中」）を
把握できない。両エージェントを独立した Activity に分割することで、ワークフローが
`_active_agent` フィールドを更新しながら UI へリアルタイムにステータスを伝達できるようになる。

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `activities/fix_sop_activity.py` | `writer_task_activity` と `reviewer_task_activity` を新設。`fix_sop_with_crew_activity` に非推奨コメントを追記 |
| `worker.py` | 2 つの新 Activity をインポートして登録 |

---

## 実装詳細

### 1. `writer_task_activity`（新設）

```python
@activity.defn
async def writer_task_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
    attempt: int = 0,
) -> LLMResult:
```

- `_TEMPERATURE_BY_ROUND` と `_URGENCY_PREFIX_BY_ROUND` を再利用（案 B で追加済み）
- Writer Agent + task_write（urgency 注入済み）のみの単一タスク Crew を構築
- `Crew(agents=[writer], tasks=[task_write], verbose=True)` → `crew.kickoff()`
- `LLMResult(text=writer_output, agent_logs="", ...)` を返す

### 2. `reviewer_task_activity`（新設）

```python
@activity.defn
async def reviewer_task_activity(
    corrected_sop: str,
) -> LLMResult:
```

- 温度は分析精度優先で固定 `0.3`
- `corrected_sop` を description に直接埋め込む（前工程の Writer Task の `context=[]` は不要）
- Reviewer Agent + task_review のみの単一タスク Crew を構築
- `LLMResult(text=reviewer_output, agent_logs=reviewer_output, ...)` を返す

### 3. `fix_sop_with_crew_activity` への非推奨コメント追記

Activity のデコレータ直上に以下を追記：

```python
# NOTE: 後方互換のため残存。新規実装では writer_task_activity / reviewer_task_activity を使用すること。
```

### 4. `worker.py` への登録

```python
from activities.fix_sop_activity import (
    fix_sop_activity,
    fix_sop_with_crew_activity,
    writer_task_activity,
    reviewer_task_activity,
)
```

`activities=[..., writer_task_activity, reviewer_task_activity, ...]` に追加。

---

## 再利用する既存要素

- `_TEMPERATURE_BY_ROUND`・`_URGENCY_PREFIX_BY_ROUND` — 案 B で追加済み
- Writer/Reviewer の `Agent` 定義（role/goal/backstory）— `_build_sop_crew` から抽出
- `task_review` の description/expected_output — `_build_sop_crew` から抽出
- `LLMResult` の返し方 — 既存 `fix_sop_with_crew_activity` のパターンを踏襲

---

## 検証

```bash
docker compose exec worker python3 -m py_compile activities/fix_sop_activity.py
docker compose exec worker python3 -m py_compile worker.py
```

両ファイルとも exit code 0（出力なし）であることを確認する。
