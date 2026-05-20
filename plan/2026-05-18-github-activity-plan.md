# GitHub PR Creation Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `activities/github_activity.py` に `GitHubActivity` クラスを新規実装し、SOP 修正結果を GitHub リポジトリへ Push して PR を自動作成する。

**Architecture:** クラスベース Temporal Activity。`subprocess` + `git` CLI でリポジトリ操作、`gh` CLI で PR 作成。私有メソッド3本（`_clone_or_update_repo`, `_commit_and_push`, `_submit_pr`）に責務を分割。ブランチ force-push + 既存 PR 検出で完全冪等性を保証。

**Tech Stack:** Python 3.13, `temporalio`, `subprocess`, `git` CLI, `gh` CLI (`/opt/homebrew/bin/gh`), `pathlib`, `tempfile`

**Dependency Decision（事前確認済み）:**
- `GitPython` → 未インストール → `subprocess + git CLI` で代替
- `PyGithub` → 未インストール → `subprocess + gh CLI` で代替
- 新規パッケージインストール不要

---

## File Structure

| ファイル | 操作 | 責務 |
|:---|:---|:---|
| `activities/github_activity.py` | 新規作成 | `GitHubActivity` クラス、4メソッド |
| `tests/test_github_activity.py` | 新規作成 | 全メソッドのユニットテスト（subprocess モック） |
| `worker.py` | 修正（L67-76） | `GitHubActivity().create_pull_request` を activities リストに追加 |

---

## 完成形コード設計

### `activities/github_activity.py` の骨組み

```python
class GitHubActivity:

    _REPO_BASE = Path(tempfile.gettempdir()) / "temporal_github"  # テストで差し替え可能

    @activity.defn
    async def create_pull_request(self, params: dict) -> dict:
        # params: repository, base_branch, feature_branch,
        #         commit_message, pr_title, pr_body, file_path, file_content
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise EnvironmentError("GITHUB_TOKEN が設定されていません。")
        repo_dir = self._clone_or_update_repo(params["repository"], token)
        self._checkout_branch(repo_dir, params["feature_branch"])
        self._write_content(repo_dir, params["file_path"], params["file_content"])
        self._commit_and_push(repo_dir, params["commit_message"], params["feature_branch"])
        pr_url = self._submit_pr(...)
        return {"pr_url": pr_url}

    def _clone_or_update_repo(self, repository, token) -> Path:   # clone or fetch
    def _checkout_branch(self, repo_dir, branch) -> None:         # git checkout -B
    def _write_content(self, repo_dir, file_path, content) -> None:  # Path.write_text
    def _commit_and_push(self, repo_dir, message, branch) -> None:   # add→commit→force-push
    def _submit_pr(self, repository, base, head, title, body) -> str: # gh pr create or list
```

---

## Task 1: `_clone_or_update_repo` — TDD

**Files:**
- Create: `activities/github_activity.py`
- Create: `tests/test_github_activity.py`

- [ ] **Step 1: テスト作成**

```python
# tests/test_github_activity.py
import os
import pytest
from unittest.mock import patch, call, MagicMock
from pathlib import Path
from activities.github_activity import GitHubActivity


@pytest.fixture
def ga(tmp_path):
    inst = GitHubActivity()
    inst._REPO_BASE = tmp_path / "repos"
    return inst


class TestCloneOrUpdateRepo:

    def test_clones_when_dir_not_exists(self, ga, tmp_path):
        """リポジトリが未クローンの場合、git clone を実行する。"""
        with patch("subprocess.run") as mock_run:
            result = ga._clone_or_update_repo("owner/repo", "tok123")
        clone_url = "https://tok123@github.com/owner/repo.git"
        mock_run.assert_called_once_with(
            ["git", "clone", clone_url, str(result)],
            check=True, capture_output=True
        )

    def test_updates_when_dir_exists(self, ga, tmp_path):
        """リポジトリが既にクローン済みの場合、remote set-url と fetch を実行する。"""
        repo_dir = ga._REPO_BASE / "owner_repo"
        repo_dir.mkdir(parents=True)
        with patch("subprocess.run") as mock_run:
            ga._clone_or_update_repo("owner/repo", "tok456")
        calls = mock_run.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0][1:3] == ["-C", str(repo_dir)]
        assert "remote" in calls[0][0][0]
        assert "fetch" in calls[1][0][0]

    def test_returns_repo_dir_path(self, ga):
        """戻り値が Path オブジェクトであることを確認する。"""
        with patch("subprocess.run"):
            result = ga._clone_or_update_repo("owner/repo", "tok")
        assert isinstance(result, Path)
        assert "owner_repo" in str(result)
```

- [ ] **Step 2: テスト失敗確認**

```bash
cd /Users/t-obara/workspace/temporal-demo
.venv/bin/pytest tests/test_github_activity.py::TestCloneOrUpdateRepo -v
```
期待: `ImportError: cannot import name 'GitHubActivity'`

- [ ] **Step 3: 最小実装（クラス骨格 + `_clone_or_update_repo`）**

```python
# activities/github_activity.py
"""
GitHub PR 作成 Activity — git CLI と gh CLI を用いてリポジトリを操作し Pull Request を開通する。
"""
import os
import subprocess
import tempfile
from pathlib import Path

from temporalio import activity


class GitHubActivity:
    """
    Temporal Activity クラス。GitHub への Push と PR 作成を担う。

    認証情報は環境変数 GITHUB_TOKEN から取得する。
    git 操作は subprocess + git CLI、PR 作成は gh CLI を使用する。
    """

    _REPO_BASE: Path = Path(tempfile.gettempdir()) / "temporal_github"

    def _clone_or_update_repo(self, repository: str, token: str) -> Path:
        """
        リポジトリをローカルにクローンするか、既存なら最新化する。

        :param repository: "owner/repo" 形式のリポジトリ名
        :param token: GitHub Personal Access Token
        :returns: ローカルリポジトリディレクトリの Path
        """
        repo_dir = self._REPO_BASE / repository.replace("/", "_")
        clone_url = f"https://{token}@github.com/{repository}.git"

        if repo_dir.exists():
            subprocess.run(
                ["git", "-C", str(repo_dir), "remote", "set-url", "origin", clone_url],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_dir), "fetch", "--all"],
                check=True, capture_output=True,
            )
        else:
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", clone_url, str(repo_dir)],
                check=True, capture_output=True,
            )
        return repo_dir
```

- [ ] **Step 4: テスト通過確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestCloneOrUpdateRepo -v
```
期待: `3 passed`

- [ ] **Step 5: コミット**

```bash
git add activities/github_activity.py tests/test_github_activity.py
git commit -m "feat: add GitHubActivity skeleton and _clone_or_update_repo"
```

---

## Task 2: `_checkout_branch` と `_write_content`

- [ ] **Step 1: テスト追加**

```python
class TestCheckoutBranch:

    def test_checkout_creates_or_resets_branch(self, ga, tmp_path):
        """git checkout -B でブランチを作成または上書きする。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        with patch("subprocess.run") as mock_run:
            ga._checkout_branch(repo_dir, "auto-fix/issue-123")
        mock_run.assert_called_once_with(
            ["git", "-C", str(repo_dir), "checkout", "-B", "auto-fix/issue-123"],
            check=True, capture_output=True,
        )


class TestWriteContent:

    def test_writes_file_to_repo(self, ga, tmp_path):
        """指定パスにコンテンツを書き込む。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ga._write_content(repo_dir, "docs/sop.md", "# SOP Content")
        assert (repo_dir / "docs" / "sop.md").read_text() == "# SOP Content"

    def test_creates_parent_dirs(self, ga, tmp_path):
        """ネストしたディレクトリが存在しなくても作成する。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ga._write_content(repo_dir, "a/b/c/file.md", "content")
        assert (repo_dir / "a" / "b" / "c" / "file.md").exists()
```

- [ ] **Step 2: テスト失敗確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestCheckoutBranch tests/test_github_activity.py::TestWriteContent -v
```
期待: `AttributeError: 'GitHubActivity' object has no attribute '_checkout_branch'`

- [ ] **Step 3: 実装追加**（`_checkout_branch`, `_write_content` を `GitHubActivity` クラスに追加）

```python
    def _checkout_branch(self, repo_dir: Path, branch: str) -> None:
        """
        feature ブランチをチェックアウトする（既存なら上書きリセット）。

        :param repo_dir: ローカルのリポジトリディレクトリ
        :param branch: チェックアウトするブランチ名
        """
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "-B", branch],
            check=True, capture_output=True,
        )

    def _write_content(self, repo_dir: Path, file_path: str, content: str) -> None:
        """
        リポジトリ内の指定パスにコンテンツを書き込む（親ディレクトリを自動作成）。

        :param repo_dir: ローカルのリポジトリディレクトリ
        :param file_path: リポジトリルートからの相対ファイルパス
        :param content: 書き込むコンテンツ文字列
        """
        target = repo_dir / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
```

- [ ] **Step 4: テスト通過確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestCheckoutBranch tests/test_github_activity.py::TestWriteContent -v
```
期待: `3 passed`

- [ ] **Step 5: コミット**

```bash
git add activities/github_activity.py tests/test_github_activity.py
git commit -m "feat: add _checkout_branch and _write_content to GitHubActivity"
```

---

## Task 3: `_commit_and_push` — 冪等性の核心

- [ ] **Step 1: テスト追加**

```python
class TestCommitAndPush:

    def test_commits_and_force_pushes_when_diff_exists(self, ga, tmp_path):
        """差分がある場合: add → commit → force-push の順で実行する。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        diff_result = MagicMock()
        diff_result.returncode = 1  # 差分あり

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(),    # git add
                diff_result,    # git diff --cached --quiet
                MagicMock(),    # git commit
                MagicMock(),    # git push --force
            ]
            ga._commit_and_push(repo_dir, "fix: auto-correct SOP", "auto-fix/issue-1")

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls[0][2:4] == ["-C", str(repo_dir)]
        assert "add" in calls[0]
        assert "commit" in calls[2]
        assert "--force" in calls[3]

    def test_skips_commit_when_no_diff(self, ga, tmp_path):
        """差分がない場合: commit をスキップして force-push のみ実行する。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        diff_result = MagicMock()
        diff_result.returncode = 0  # 差分なし

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(),    # git add
                diff_result,    # git diff --cached --quiet
                MagicMock(),    # git push --force (commit はスキップ)
            ]
            ga._commit_and_push(repo_dir, "msg", "branch")

        assert mock_run.call_count == 3
        push_call = mock_run.call_args_list[2][0][0]
        assert "--force" in push_call
```

- [ ] **Step 2: テスト失敗確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestCommitAndPush -v
```

- [ ] **Step 3: 実装追加**

```python
    def _commit_and_push(self, repo_dir: Path, message: str, branch: str) -> None:
        """
        全変更をステージング・コミットし、強制プッシュする。

        差分がない場合はコミットをスキップし force-push のみ実行する（冪等性保証）。

        :param repo_dir: ローカルのリポジトリディレクトリ
        :param message: コミットメッセージ
        :param branch: プッシュするブランチ名
        """
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", "-A"],
            check=True, capture_output=True,
        )
        diff = subprocess.run(
            ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "-C", str(repo_dir), "commit", "-m", message],
                check=True, capture_output=True,
            )
        subprocess.run(
            ["git", "-C", str(repo_dir), "push", "--force", "origin", branch],
            check=True, capture_output=True,
        )
```

- [ ] **Step 4: テスト通過確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestCommitAndPush -v
```
期待: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add activities/github_activity.py tests/test_github_activity.py
git commit -m "feat: add _commit_and_push with idempotent force-push"
```

---

## Task 4: `_submit_pr` — PR 作成・重複防止

- [ ] **Step 1: テスト追加**

```python
class TestSubmitPr:

    def test_creates_new_pr_when_none_exists(self, ga):
        """既存 PR がない場合、gh pr create を実行して URL を返す。"""
        check_result = MagicMock(stdout="", returncode=0)
        create_result = MagicMock(stdout="https://github.com/owner/repo/pull/42\n", returncode=0)

        with patch("subprocess.run", side_effect=[check_result, create_result]):
            url = ga._submit_pr("owner/repo", "main", "auto-fix/1", "title", "body")

        assert url == "https://github.com/owner/repo/pull/42"

    def test_returns_existing_pr_url_without_creating(self, ga):
        """同ブランチの PR が既に存在する場合、新規作成せず既存 URL を返す。"""
        check_result = MagicMock(
            stdout="https://github.com/owner/repo/pull/10\n", returncode=0
        )

        with patch("subprocess.run", return_value=check_result) as mock_run:
            url = ga._submit_pr("owner/repo", "main", "auto-fix/1", "title", "body")

        assert url == "https://github.com/owner/repo/pull/10"
        assert mock_run.call_count == 1  # create は呼ばれない
```

- [ ] **Step 2: テスト失敗確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestSubmitPr -v
```

- [ ] **Step 3: 実装追加**

```python
    def _submit_pr(
        self,
        repository: str,
        base: str,
        head: str,
        title: str,
        body: str,
    ) -> str:
        """
        gh CLI で PR を作成する。同ブランチの PR が既存なら URL をそのまま返す。

        :param repository: "owner/repo" 形式のリポジトリ名
        :param base: マージ先ブランチ名
        :param head: feature ブランチ名
        :param title: PR タイトル
        :param body: PR 本文
        :returns: PR の URL 文字列
        """
        check = subprocess.run(
            ["gh", "pr", "list", "--head", head, "--repo", repository,
             "--json", "url", "--jq", ".[0].url"],
            capture_output=True, text=True,
        )
        existing_url = check.stdout.strip()
        if existing_url:
            return existing_url

        result = subprocess.run(
            ["gh", "pr", "create",
             "--repo", repository,
             "--base", base,
             "--head", head,
             "--title", title,
             "--body", body],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()
```

- [ ] **Step 4: テスト通過確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestSubmitPr -v
```
期待: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add activities/github_activity.py tests/test_github_activity.py
git commit -m "feat: add _submit_pr with idempotent PR deduplication"
```

---

## Task 5: `create_pull_request` — メインアクティビティ統合

- [ ] **Step 1: テスト追加**

```python
class TestCreatePullRequest:

    @pytest.mark.asyncio
    async def test_full_flow_returns_pr_url(self, ga):
        """全サブメソッドが正しい順序で呼ばれ、pr_url を返す。"""
        from pathlib import Path
        params = {
            "repository": "owner/repo",
            "base_branch": "main",
            "feature_branch": "auto-fix/1",
            "commit_message": "fix: SOP",
            "pr_title": "Auto-fix SOP",
            "pr_body": "Automated correction",
            "file_path": "docs/sop.md",
            "file_content": "# SOP",
        }
        with (
            patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}),
            patch.object(ga, "_clone_or_update_repo", return_value=Path("/tmp/repo")) as m_clone,
            patch.object(ga, "_checkout_branch") as m_checkout,
            patch.object(ga, "_write_content") as m_write,
            patch.object(ga, "_commit_and_push") as m_push,
            patch.object(ga, "_submit_pr", return_value="https://github.com/owner/repo/pull/1") as m_pr,
        ):
            result = await ga.create_pull_request(params)

        assert result == {"pr_url": "https://github.com/owner/repo/pull/1"}
        m_clone.assert_called_once_with("owner/repo", "tok")
        m_checkout.assert_called_once_with(Path("/tmp/repo"), "auto-fix/1")
        m_write.assert_called_once_with(Path("/tmp/repo"), "docs/sop.md", "# SOP")
        m_push.assert_called_once_with(Path("/tmp/repo"), "fix: SOP", "auto-fix/1")

    @pytest.mark.asyncio
    async def test_raises_when_github_token_missing(self, ga):
        """GITHUB_TOKEN が未設定の場合、EnvironmentError を送出する。"""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(EnvironmentError, match="GITHUB_TOKEN"),
        ):
            await ga.create_pull_request({})
```

- [ ] **Step 2: テスト失敗確認**

```bash
.venv/bin/pytest tests/test_github_activity.py::TestCreatePullRequest -v
```

- [ ] **Step 3: `create_pull_request` 実装追加**

```python
    @activity.defn
    async def create_pull_request(self, params: dict) -> dict:
        """
        SOP または修正コードをリポジトリへ Push し、Pull Request を作成する。

        :param params: repository / base_branch / feature_branch / commit_message /
                       pr_title / pr_body / file_path / file_content を含む辞書
        :returns: {"pr_url": "https://github.com/.../pull/N"}
        :raises EnvironmentError: GITHUB_TOKEN が未設定の場合
        :raises subprocess.CalledProcessError: git / gh 操作失敗時
        """
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise EnvironmentError("GITHUB_TOKEN が設定されていません。")

        repo_dir = self._clone_or_update_repo(params["repository"], token)
        self._checkout_branch(repo_dir, params["feature_branch"])
        self._write_content(repo_dir, params["file_path"], params["file_content"])
        self._commit_and_push(repo_dir, params["commit_message"], params["feature_branch"])
        pr_url = self._submit_pr(
            params["repository"],
            params["base_branch"],
            params["feature_branch"],
            params["pr_title"],
            params["pr_body"],
        )
        return {"pr_url": pr_url}
```

- [ ] **Step 4: 全テスト通過確認**

```bash
.venv/bin/pytest tests/test_github_activity.py -v
```
期待: `12 passed`（全テスト Green）

- [ ] **Step 5: コミット**

```bash
git add activities/github_activity.py tests/test_github_activity.py
git commit -m "feat: implement create_pull_request activity method"
```

---

## Task 6: Worker への登録

**Files:**
- Modify: `worker.py:23-77`

- [ ] **Step 1: `worker.py` に import と登録を追加**

```python
# worker.py に追加（既存 import 群の末尾）
from activities.github_activity import GitHubActivity

# main() 内の Worker(...) 呼び出し直前
_github_activity = GitHubActivity()

# activities=[ ... ] の末尾に追加
_github_activity.create_pull_request,
```

- [ ] **Step 2: 全テスト通過確認（リグレッション）**

```bash
.venv/bin/pytest tests/ -v
```
期待: 既存 23 + 新規 12 = `35 passed`

- [ ] **Step 3: コミット**

```bash
git add worker.py
git commit -m "feat: register GitHubActivity.create_pull_request in worker"
```

---

## 検証手順

1. **ユニットテスト**: `pytest tests/test_github_activity.py -v` → 12 passed
2. **リグレッション確認**: `pytest tests/ -v` → 35 passed
3. **静的解析**: `.venv/bin/python -c "from activities.github_activity import GitHubActivity; print('OK')"` → OK
