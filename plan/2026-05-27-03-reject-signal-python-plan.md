# Plan: reject_with_feedback Signal ハンドラの追加

## Context
フロントエンドの `POST /api/reject` が送る `reject_with_feedback` Signal を
Python ワークフロー側で受け取れるよう `workflows/sop_workflow.py` を拡張する。
Phase 5 の PR 承認待機が承認/差し戻しの両シグナルで解除できるようにし、
差し戻し時はステータスを `"rejected"` に更新して早期リターンする。

---

## Pre-Implementation Audit（CLAUDE.md 要件）

| 項目 | 判定 | 根拠 |
|---|---|---|
| Temporal Resilience | ✅ | Signal ハンドラはフラグ代入のみ。非決定的コードなし |
| Idempotency | ✅ | 同じ Signal を再受信しても同値を上書きするだけ |
| Error Handling | ✅ | 差し戻しは意図的な終了。`ApplicationError` を投げず早期リターンが適切 |

---

## 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `workflows/sop_workflow.py` | Signal ハンドラ追加、wait_condition 拡張、早期リターン追加 |

---

## 変更詳細

### 1. `__init__` にメンバ変数を追加
```python
self._human_feedback: str = ""   # reject_with_feedback Signal で受け取ったコメント
```

### 2. `PHASE_LABELS` に "rejected" を追加
```python
"rejected": "差し戻し済み",
```

### 3. Signal ハンドラを追加（`approve_pr` の直後）
```python
@workflow.signal
def reject_with_feedback(self, input_data: dict) -> None:
    """
    人間からの修正指示を受け取り、PR 承認待機を差し戻しとして解除する。

    :param input_data: {"comment": "修正指示テキスト"} 形式の辞書
    """
    self._human_feedback = (
        input_data.get("comment", "") if isinstance(input_data, dict) else str(input_data)
    )
```

### 4. `get_status()` に `human_feedback` を追加
```python
"human_feedback": self._human_feedback,
```

### 5. Phase 5 の `wait_condition` を拡張（現行 :242）
```python
# 変更前
await workflow.wait_condition(lambda: self._pr_approved)

# 変更後
await workflow.wait_condition(
    lambda: self._pr_approved or bool(self._human_feedback)
)

if self._human_feedback:
    self._status = "rejected"
    self._current_phase = "rejected"
    workflow.logger.info(
        "差し戻しシグナル受信 — フィードバック: %s", self._human_feedback
    )
    return {
        "topic": topic,
        "outline": self._approved.get("outline", ""),
        "draft":   self._approved.get("draft", ""),
        "review":  self._approved.get("review", ""),
        "history": self._history,
        "pr_url":  self._pr_url,
        "rejected": True,
        "human_feedback": self._human_feedback,
    }
# ここから下は既存の PR 作成処理（self._status = "creating_pr" ...）
```

### 6. モジュール docstring を更新
Signal 一覧に `reject_with_feedback(input_data: dict)` を追記する。

---

## 検証手順
1. `pytest tests/ -v` で全テストが GREEN であることを確認（既存 40 件のデグレードなし）
