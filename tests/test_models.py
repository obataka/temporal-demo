"""ValidationResult / GitHubParams データクラスの単体テスト。"""

from core.models import ValidationResult, GitHubParams


def test_validation_result_passed():
    """passed=True の場合、failures が空であることを確認。"""
    result = ValidationResult(passed=True, failures=[], score={"char_count": 600})
    assert result.passed is True
    assert result.failures == []
    assert result.score["char_count"] == 600


def test_validation_result_failed():
    """passed=False の場合、failures にメッセージが入ることを確認。"""
    result = ValidationResult(
        passed=False,
        failures=["文字数不足: 200文字 (最低500文字必要)"],
        score={"char_count": 200},
    )
    assert result.passed is False
    assert len(result.failures) == 1
    assert "文字数不足" in result.failures[0]


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

    def test_require_approval_default(self):
        """require_approval のデフォルト値が False であることを確認する。"""
        params = GitHubParams(
            repository="owner/repo",
            base_branch="main",
            feature_branch="auto-fix/sop-1",
        )
        assert params.require_approval is False

    def test_require_approval_can_be_enabled(self):
        """require_approval を True に設定できることを確認する。"""
        params = GitHubParams(
            repository="owner/repo",
            base_branch="main",
            feature_branch="auto-fix/sop-1",
            require_approval=True,
        )
        assert params.require_approval is True
