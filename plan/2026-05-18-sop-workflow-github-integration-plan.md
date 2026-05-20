# SopWorkflow への GitHubActivity 結合 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sop_generation_workflow` の末尾（Phase 4 バリデーション Green 直後）に `GitHubActivity.create_pull_request` を呼び出す Phase 5 を追加し、最終 SOP が自動的に GitHub PR として出力されるようにする。

**Architecture:** `run()` の第3引数に `GitHubParams | None`（オプショナル）を追加する後方互換設計。`None` の場合は GitHub フェーズをスキップするため、既存の全テスト（35件）はそのまま通過する。

**Tech Stack:** 既存スタックの延長。`GitHubActivity.create_pull_request` は本日実装済み。

---

## File Structure

| ファイル | 操作 | 内容 |
|:---|:---|:---|
| `core/models.py` | 修正 | `GitHubParams` dataclass を追記 |
| `workflows/sop_workflow.py` | 修正 | `run()` 第3引数追加・Phase 5 呼び出し・`_call_github_pr()` 追加 |
| `tests/test_models.py` | 修正 | `GitHubParams` のテストを追記 |

---

## Task 1: `GitHubParams` dataclass を `core/models.py` に追加

**Files:**
- Modify: `core/models.py`（末尾に追記）

- [ ] **Step 1: テスト追加（`tests/test_models.py` 末尾に追記）**

```python
# tests/test_models.py に追記
from core.models import GitHubParams


class TestGitHubParams:

    def test_required_fields(self):
        """必須フィールドが正しく設定されることを確認する。"""
        params = GitHubParams(
            repository="owner/repo",
            base_branch="main",
            feature_branch="auto-fix/sop-1",
        )
        assert params.repository == "owner/repo"
        assert params.base_branch == "main"
        assert params.feature_branch == "auto-fix/sop-1"

    def test_file_path_default(self):
        """file_path のデフォルト値が 'docs/sop.md' であることを確認する。"""
        params = GitHubParams(
            repository="owner/repo",
            base_branch="main",
            feature_branch="auto-fix/sop-1",
        )
        assert params.file_path == "docs/sop.md"

    def test_file_path_override(self):
        """file_path をカスタム値で上書きできることを確認する。"""
        params = GitHubParams(
            repository="owner/repo",
            base_branch="main",
            feature_branch="auto-fix/sop-1",
            file_path="output/my-sop.md",
        )
        assert params.file_path == "output/my-sop.md"
```

- [ ] **Step 2: テスト失敗確認**

```bash
.venv/bin/pytest tests/test_models.py -v
```
期待: `ImportError: cannot import name 'GitHubParams'`

- [ ] **Step 3: `GitHubParams` を `core/models.py` 末尾に追記**

```python
@dataclass
class GitHubParams:
    """GitHub PR 作成に必要なメタデータ。sop_generation_workflow の run() に渡す。"""
    repository: str       # "owner/repo"
    base_branch: str      # "main"
    feature_branch: str   # "auto-fix/sop-xxx"
    file_path: str = "docs/sop.md"  # リポジトリ内の保存先パス
```

- [ ] **Step 4: テスト通過確認**

```bash
.venv/bin/pytest tests/test_models.py -v
```
期待: 既存テスト + 新規3件 = すべて passed

- [ ] **Step 5: コミット**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat: add GitHubParams dataclass to core/models"
```

---

## Task 2: `sop_workflow.py` の拡張

**Files:**
- Modify: `workflows/sop_workflow.py`

変更箇所は5点。順番に適用する。

### 2-A: import 追加

`workflow.unsafe.imports_passed_through()` ブロックに `GitHubActivity` と `GitHubParams` を追加。

```python
# 変更前
with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
    from activities.validate_sop_activity import validate_sop_activity
    from activities.fix_sop_activity import fix_sop_activity

# 変更後
with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
    from activities.validate_sop_activity import validate_sop_activity
    from activities.fix_sop_activity import fix_sop_activity
    from activities.github_activity import GitHubActivity

from core.models import SOPRequest, LLMResult, ValidationResult, GitHubParams
```

（`GitHubParams` は Sandbox-safe dataclass なので `imports_passed_through()` 外でよい）

### 2-B: `PHASE_LABELS` に Phase 5 を追加

```python
PHASE_LABELS = {
    "outline":        "フェーズ1: 章立て提案",
    "draft":          "フェーズ2: 詳細執筆",
    "review":         "フェーズ3: 最終レビュー",
    "autonomous_fix": "フェーズ4: 自律修正",
    "github_pr":      "フェーズ5: GitHub PR作成",  # ← 追加
}
```

### 2-C: `__init__` に `_pr_url` 状態変数を追加

```python
# 自律修正ループ状態
self._fix_attempt: int = 0
self._validation_result: dict | None = None
self._pr_url: str | None = None   # ← 追加
```

### 2-D: `get_status()` に `pr_url` を追加

```python
@workflow.query
def get_status(self) -> dict:
    return {
        "status": self._status,
        "current_phase": self._current_phase,
        "phase_label": PHASE_LABELS.get(self._current_phase, self._current_phase),
        "attempt_in_phase": self._attempt_in_phase,
        "current_output": self._current_output,
        "approved_phases": list(self._approved.keys()),
        "fix_attempt": self._fix_attempt,
        "validation_result": self._validation_result,
        "pr_url": self._pr_url,   # ← 追加
    }
```

### 2-E: `run()` の引数拡張・Phase 5 追加・戻り値拡張

```python
@workflow.run
async def run(
    self,
    topic: str,
    source_code: str,
    github_params: GitHubParams | None = None,   # ← 追加
) -> dict:
    ...
    # （Phase 4 の末尾、self._status = "completed" の直前に挿入）

    # ── Phase 5: GitHub PR 作成（github_params が指定された場合のみ）─────────
    if github_params is not None:
        self._current_phase = "github_pr"
        self._status = "creating_pr"
        pr_result = await self._call_github_pr(
            sop_text=final_sop,
            topic=topic,
            github_params=github_params,
        )
        self._pr_url = pr_result["pr_url"]

    self._status = "completed"
    self._current_phase = "completed"

    return {
        "topic": topic,
        "outline": self._approved.get("outline", ""),
        "draft": self._approved.get("draft", ""),
        "review": self._approved.get("review", ""),
        "history": self._history,
        "pr_url": self._pr_url,   # ← 追加（github_params=None なら None）
    }
```

### 2-F: `_call_github_pr()` ヘルパーメソッドを追加

```python
async def _call_github_pr(
    self,
    sop_text: str,
    topic: str,
    github_params: GitHubParams,
) -> dict:
    """
    GitHubActivity.create_pull_request を実行して PR URL を返す。

    :param sop_text: 最終承認済み SOP 全文
    :param topic: SOP のトピック名（PR タイトル/コミットメッセージに使用）
    :param github_params: GitHub 操作に必要なメタデータ
    :returns: {"pr_url": "https://github.com/.../pull/N"}
    """
    params = {
        "repository":     github_params.repository,
        "base_branch":    github_params.base_branch,
        "feature_branch": github_params.feature_branch,
        "file_path":      github_params.file_path,
        "file_content":   sop_text,
        "commit_message": f"docs: auto-generated SOP for {topic}",
        "pr_title":       f"[Auto SOP] {topic}",
        "pr_body":        (
            f"このPRは `sop_generation_workflow` により自動生成されました。\n\n"
            f"**トピック:** {topic}\n\n"
            f"バリデーション（{MAX_FIX_ATTEMPTS}回以内）を通過した最終版SOPです。"
        ),
    }
    return await workflow.execute_activity(
        GitHubActivity.create_pull_request,
        params,
        start_to_close_timeout=timedelta(minutes=7),
        retry_policy=LLM_RETRY_POLICY,
    )
```

- [ ] **Step 1: 上記5点の変更を `workflows/sop_workflow.py` に適用する**

- [ ] **Step 2: import チェック（構文エラーがないことを確認）**

```bash
.venv/bin/python -c "from workflows.sop_workflow import sop_generation_workflow; print('OK')"
```
期待: `OK`

- [ ] **Step 3: 全テスト通過確認（リグレッション）**

```bash
.venv/bin/pytest tests/ -v
```
期待: 35 passed（既存35件がすべて通過すること）

- [ ] **Step 4: コミット**

```bash
git add workflows/sop_workflow.py
git commit -m "feat: add Phase 5 GitHub PR creation to sop_generation_workflow"
```

---

## 検証手順

1. **モデルテスト**: `pytest tests/test_models.py -v` → GitHubParams 3件追加
2. **リグレッション**: `pytest tests/ -v` → 35 → 38 passed
3. **import 確認**: `python -c "from workflows.sop_workflow import sop_generation_workflow; print('OK')"`
4. **明日の実戦テスト**: `github_params=GitHubParams(repository="...", base_branch="main", feature_branch="auto-fix/test")` を渡して PR が実際に作成されることを確認
