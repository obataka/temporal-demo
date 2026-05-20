# 計画: Human-in-the-Loop ガバナンス — Phase 5 PR 承認 Signal の追加

## Context
`sop_generation_workflow` の Phase 5（GitHub PR 作成）に人間の承認ゲートを追加する。
`GitHubParams.require_approval=True` の場合のみ `approve_pr` Signal を待機し、
デフォルト `False` で既存コード・テストへの影響ゼロを保証する。

---

## 変更ファイル一覧

| ファイル | 操作 | 概要 |
|---|---|---|
| `core/models.py` | **修正** | `GitHubParams` に `require_approval: bool = False` を追加 |
| `workflows/sop_workflow.py` | **修正** | `_pr_approved` 変数・`approve_pr` Signal・wait condition・docstring 更新 |
| `tests/test_models.py` | **修正** | `require_approval` のデフォルト値と有効化テストを追加 |

---

## 各ファイルの変更詳細

### 1. `core/models.py` — `GitHubParams` にフラグ追加

```python
@dataclass
class GitHubParams:
    repository: str
    base_branch: str
    feature_branch: str
    file_path: str = "docs/sop.md"
    require_approval: bool = False  # True: PR 作成前に approve_pr Signal を待つ
```

デフォルト `False` なので既存の全呼び出しは無変更で動作する。

---

### 2. `workflows/sop_workflow.py` — 4箇所の変更

**A. モジュール docstring に追記**（Signals セクション）
```
approve_pr()
    require_approval=True 時、Phase 5 直前に呼び出して PR 作成を解放する
```

**B. `__init__` にインスタンス変数を追加**
```python
self._pr_approved: bool = False
```

**C. Signal ハンドラを追加**（`approve_step` の直後）
```python
@workflow.signal
def approve_pr(self) -> None:
    """Phase 5 PR 作成を承認する。require_approval=True 時のみ使用する。"""
    self._pr_approved = True
```

**D. Phase 5 ブロックに wait condition を挿入**
```python
if github_params is not None:
    self._current_phase = "github_pr"
    if github_params.require_approval:          # ガバナンスゲート
        self._status = "awaiting_pr_approval"
        await workflow.wait_condition(lambda: self._pr_approved)
    self._status = "creating_pr"
    pr_result = await self._call_github_pr(...)
    self._pr_url = pr_result["pr_url"]
```

**E. `get_status()` に `pr_approved` を追加**

---

### 3. `tests/test_models.py` — テスト2件追加

`require_approval` のデフォルト `False` と `True` 設定の確認テスト。

---

## 事前監査チェック
- **Temporal Resilience**: Signal ハンドラは同期、wait_condition は非決定的要素なし ✅
- **Idempotency**: `approve_pr` は `_pr_approved = True` の冪等な代入のみ ✅
- **後方互換性**: `require_approval` デフォルト `False` → 既存コード無変更 ✅

## 検証
```bash
pytest tests/ -v
```
38 passed → 40 passed（新規2テスト追加）になることを確認する。
