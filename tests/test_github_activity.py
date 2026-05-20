"""
GitHubActivity のユニットテスト。

subprocess.run をモックすることで外部依存なしに全メソッドを検証する。
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from activities.github_activity import GitHubActivity


@pytest.fixture
def ga(tmp_path):
    """
    テスト用 GitHubActivity インスタンス。_REPO_BASE を tmp_path に向ける。

    :param tmp_path: pytest が提供する一時ディレクトリ
    :returns: テスト用 GitHubActivity インスタンス
    """
    inst = GitHubActivity()
    inst._REPO_BASE = tmp_path / "repos"
    return inst


# ─── _clone_or_update_repo ───────────────────────────────────────────────────

class TestCloneOrUpdateRepo:

    def test_clones_when_dir_not_exists(self, ga):
        """リポジトリが未クローンの場合、git clone を実行する。"""
        with patch("subprocess.run") as mock_run:
            result = ga._clone_or_update_repo("owner/repo", "tok123")
        clone_url = "https://tok123@github.com/owner/repo.git"
        mock_run.assert_called_once_with(
            ["git", "clone", clone_url, str(result)],
            check=True, capture_output=True,
        )

    def test_updates_when_dir_exists(self, ga):
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


# ─── _checkout_branch ────────────────────────────────────────────────────────

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


# ─── _write_content ──────────────────────────────────────────────────────────

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


# ─── _commit_and_push ────────────────────────────────────────────────────────

class TestCommitAndPush:

    def test_commits_and_force_pushes_when_diff_exists(self, ga, tmp_path):
        """差分がある場合: add → commit → force-push の順で実行する。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        diff_result = MagicMock()
        diff_result.returncode = 1  # 差分あり

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(),  # git add
                diff_result,  # git diff --cached --quiet
                MagicMock(),  # git config user.email
                MagicMock(),  # git config user.name
                MagicMock(),  # git commit
                MagicMock(),  # git push --force
            ]
            ga._commit_and_push(repo_dir, "fix: auto-correct SOP", "auto-fix/issue-1")

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls[0][1:3] == ["-C", str(repo_dir)]
        assert "add" in calls[0]
        assert "commit" in calls[4]
        assert "--force" in calls[5]

    def test_skips_commit_when_no_diff(self, ga, tmp_path):
        """差分がない場合: commit をスキップして force-push のみ実行する。"""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        diff_result = MagicMock()
        diff_result.returncode = 0  # 差分なし

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(),  # git add
                diff_result,  # git diff --cached --quiet
                MagicMock(),  # git push --force（commit はスキップ）
            ]
            ga._commit_and_push(repo_dir, "msg", "branch")

        assert mock_run.call_count == 3
        push_call = mock_run.call_args_list[2][0][0]
        assert "--force" in push_call


# ─── _submit_pr ──────────────────────────────────────────────────────────────

class TestSubmitPr:

    def test_creates_new_pr_when_none_exists(self, ga):
        """既存 PR がない場合、gh pr create を実行して URL を返す。"""
        check_result = MagicMock(stdout="", returncode=0)
        create_result = MagicMock(
            stdout="https://github.com/owner/repo/pull/42\n", returncode=0
        )
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


# ─── create_pull_request ─────────────────────────────────────────────────────

class TestCreatePullRequest:

    @pytest.mark.asyncio
    async def test_full_flow_returns_pr_url(self, ga):
        """全サブメソッドが正しい順序で呼ばれ、pr_url を返す。"""
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
            patch.object(
                ga, "_submit_pr", return_value="https://github.com/owner/repo/pull/1"
            ) as m_pr,
        ):
            result = await ga.create_pull_request(params)

        assert result == {"pr_url": "https://github.com/owner/repo/pull/1"}
        m_clone.assert_called_once_with("owner/repo", "tok")
        m_checkout.assert_called_once_with(Path("/tmp/repo"), "auto-fix/1")
        m_write.assert_called_once_with(Path("/tmp/repo"), "docs/sop.md", "# SOP")
        m_push.assert_called_once_with(Path("/tmp/repo"), "fix: SOP", "auto-fix/1")
        m_pr.assert_called_once_with("owner/repo", "main", "auto-fix/1", "Auto-fix SOP", "Automated correction")

    @pytest.mark.asyncio
    async def test_raises_when_github_token_missing(self, ga):
        """GITHUB_TOKEN が未設定の場合、EnvironmentError を送出する。"""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(EnvironmentError, match="GITHUB_TOKEN"),
        ):
            await ga.create_pull_request({})
