# result: reject_with_feedback Signal ハンドラの追加（Python）

実施日: 2026-05-27

---

## A. System Interaction Flow

```
TypeScript (Hono)
  → handle.signal("reject_with_feedback", { comment: "..." })
    → Temporal Server
      → sop_generation_workflow.reject_with_feedback(input_data)
          → self._human_feedback = input_data.get("comment", "")

[Phase 5 待機中]
  wait_condition: self._pr_approved OR bool(self._human_feedback)
    ┌ self._human_feedback が真
    │   → status = "rejected", current_phase = "rejected"
    │   → logger.info("差し戻しシグナル受信 — フィードバック: ...")
    │   → return { ..., "rejected": True, "human_feedback": "..." }  ← 早期リターン
    └ self._pr_approved が真
        → 既存の PR 作成処理へ進む（変更なし）
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `workflows/sop_workflow.py` | `__init__`: `_human_feedback` 追加 | 差し戻しコメントの保持 | `reject_with_feedback` ハンドラ |
| `workflows/sop_workflow.py` | `reject_with_feedback()` 追加 | Signal を受信してコメントを保持 | `wait_condition` |
| `workflows/sop_workflow.py` | `get_status()` 拡張 | Query で `human_feedback` を公開 | Hono `/api/status` |
| `workflows/sop_workflow.py` | Phase 5 `wait_condition` 拡張 | 承認/差し戻し両条件で待機解除 | `approve_pr`, `reject_with_feedback` |
| `tests/test_fix_sop_activity.py` | モデル名の期待値を修正 | 既存テストのデグレ解消 | — |

## C. Change Intent & Critical Points

### 設計の意図
既存の `_pr_approved` フラグパターンを踏襲し、`_human_feedback` 文字列フラグを追加することで
`wait_condition` の分岐を最小限の変更で実現した。
差し戻し時は `ApplicationError` を投げず早期リターンとし、
ワークフローが正常完了（`COMPLETED`）として記録されるようにしている。

### クリティカル・ポイント（最大3点）

1. **早期リターンの選択**: 差し戻しを `ApplicationError` ではなく return で終了させることで、
   ワークフローのステータスが `FAILED` でなく `COMPLETED` になる。
   再試行や補償トランザクションが不要な意図的終了にはこの設計が適切。
2. **`isinstance(input_data, dict)` ガード**: TypeScript SDK から送られるオブジェクトが
   デシリアライズされた形式に依存しないよう、辞書以外の場合は `str()` にフォールバックしている。
3. **`require_approval=False` 時は無影響**: `if github_params.require_approval:` ブロック内のみ
   変更しているため、差し戻し Signal が届いても `require_approval=False` のワークフローは
   そのまま PR 作成処理に進む。

## D. 副次的な修正

`test_fix_activity_returns_llm_result` が `gemini-2.5-flash` を期待していたが、
activity 側は LESSON.md Run 3 の対応で `gemini-2.5-flash-lite` に変更済みだった。
テストの期待値を実態に合わせて修正し、40 passed を達成した。

## E. 検証結果

```
pytest tests/ -v → 40 passed in 1.20s
```
