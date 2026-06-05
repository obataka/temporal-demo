# 案A：ワークフロー側 active_agent 状態管理 実装計画

作成日: 2026-06-05  
対象ファイル: `workflows/sop_workflow.py`（のみ）  
設計根拠: `docs/spike_next_features.md` 案 A 節

---

## Context

Activity 分割（前タスク）で `writer_task_activity` / `reviewer_task_activity` が用意できた。
ワークフロー側に `_active_agent` 状態フィールドを追加し、2 つの Activity の呼び出しの
合間で「Writer → Reviewer → None」と更新することで、`get_status()` Query 経由で UI が
リアルタイムにエージェントステータスを取得できるようにする。
Temporal のリプレイ安全性のため `workflow.patched()` で新旧コードパスを分岐する。

---

## 変更ファイル

`workflows/sop_workflow.py` のみ。テストファイル・Activity ファイルは変更なし。

---

## 実装詳細

### 1. インポートの追加

`fix_sop_with_crew_activity` の import に `writer_task_activity`, `reviewer_task_activity` を追加

### 2. `__init__` にフィールド追加

`self._active_agent: str | None = None`

### 3. `get_status()` に `active_agent` フィールドを追加

戻り値 dict の末尾に `"active_agent": self._active_agent`

### 4. `_call_fix_decomposed` メソッドを新設

Writer → Reviewer の 2 ステップシーケンスを実行し、`LLMResult` を返す。
active_agent を「Writer」→「Reviewer」→ None の順にセット。

### 5. `_call_fix` を `workflow.patched()` で分岐

`workflow.patched("split-writer-reviewer")` が True なら `_call_fix_decomposed` を呼ぶ。
旧コードパスは `fix_sop_with_crew_activity` を従来通り呼ぶ。

---

## 後方互換性

`workflow.patched()` により旧ワークフローのリプレイは旧コードパスを使用。
49 件のユニットテストは Activity 層のテストのため影響なし。

---

## 検証

```bash
docker compose exec worker pytest tests/ -v
```

49 件全件 PASS を確認する。
