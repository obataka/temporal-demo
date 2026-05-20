# 概要ドキュメント: Human-in-the-Loop ガバナンス — Phase 5 PR 承認 Signal の追加

**作成日:** 2026-05-20  
**タスク:** `sop_generation_workflow` Phase 5 直前に `approve_pr` Signal による人間承認ゲートを追加

---

## A. System Interaction Flow

```
[require_approval=False（デフォルト）]
Phase 4 完了 → Phase 5: creating_pr → PR 作成 → completed
                ↑ Signal 不要。既存動作と完全に同じ。

[require_approval=True]
Phase 4 完了 → Phase 5: awaiting_pr_approval
                         ↑ workflow.wait_condition(lambda: self._pr_approved)
                         │
                外部クライアント: handle.signal("approve_pr")
                         │
                         ↓ _pr_approved = True → wait_condition 解除
              Phase 5: creating_pr → PR 作成 → completed
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `core/models.py` | `GitHubParams.require_approval` | 承認ゲートの on/off を制御するフラグ（デフォルト False） | `sop_generation_workflow.run()` |
| `workflows/sop_workflow.py` | `__init__._pr_approved` | 承認状態を保持するインスタンス変数 | `approve_pr` Signal, `wait_condition` |
| `workflows/sop_workflow.py` | `approve_pr()` | 承認 Signal ハンドラ。`_pr_approved = True` をセットする | 外部クライアント（`handle.signal("approve_pr")`） |
| `workflows/sop_workflow.py` | `run()` Phase 5 ブロック | `require_approval=True` 時のみ wait_condition で一時停止 | `approve_pr` Signal |
| `workflows/sop_workflow.py` | `get_status()` | `pr_approved` を返してクライアントが承認待ち状態を検知可能にする | 外部クライアント（Query） |
| `tests/test_github_activity.py` | `test_commits_and_force_pushes_when_diff_exists` | git config 2コマンド追加に合わせて mock side_effect を更新 | `GitHubActivity._commit_and_push` |
| `tests/test_models.py` | `test_require_approval_*` | `require_approval` フィールドのデフォルト値と設定可能性を検証 | `GitHubParams` |

---

## C. 設計の意図とクリティカルポイント

### なぜこの設計か
- `require_approval: bool = False` をデフォルトにすることで、既存の全呼び出し（`sop_github_test.py` 含む）を無変更で後方互換にした
- Signal ハンドラ `approve_pr()` はパラメータなしのシンプルな設計にし、フラグセットのみを行う（冪等）

### クリティカルポイント（最大3点）

1. **`require_approval=False` がデフォルト** — 既存のテスト・スクリプトは `GitHubParams` に `require_approval` を指定しないため、承認待ちは発生しない。ガバナンスを有効にするには `GitHubParams(require_approval=True)` を明示する必要がある。

2. **`get_status()` の `pr_approved` で状態を検知** — クライアントは `status == "awaiting_pr_approval"` または `pr_approved == False` でゲート中を検知し、準備ができたら `handle.signal("approve_pr")` を送信する。

3. **テスト修正が必要だった** — `_commit_and_push` に `git config` 2コマンドを追加したことで、`test_commits_and_force_pushes_when_diff_exists` の `mock.side_effect` が足りなくなった。呼び出しインデックスも `calls[2/3]` → `calls[4/5]` に更新した。

---

## テスト結果

```
31 passed（環境依存の既存失敗2ファイルを除外）
新規追加: test_require_approval_default, test_require_approval_can_be_enabled
```

既存失敗（私の変更と無関係）:
- `test_observability.py` — `prometheus_client` 未インストール
- `test_fix_sop_activity.py` — `google-genai` 未インストール（ローカル環境の問題）
