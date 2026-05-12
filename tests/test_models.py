"""ValidationResult データクラスの単体テスト。"""

from core.models import ValidationResult


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
