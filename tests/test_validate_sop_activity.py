"""
validate_sop_activity の単体テスト。
Temporal サーバ・API キー不要。_run_rules を直接テストする。
"""

import pytest
from core.models import ValidationResult

# 全ルールをパスする SOP テキスト（文字数 ≥ 500、## ≥ 3、コードブロック、プレースホルダーなし）
GOOD_SOP = (
    "## セクション1: 概要\n\n"
    + "あ" * 200
    + "\n\n## セクション2: 手順\n\n"
    + "い" * 200
    + "\n\n## セクション3: 注意事項\n\n"
    + "う" * 50
    + "\n\n```python\nprint('hello')\n```\n"
)


def test_good_sop_passes_all_rules():
    """全ルールを満たす SOP が failures=[] を返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    failures, score = _run_rules(GOOD_SOP)
    assert failures == []
    assert score["section_count"] >= 3
    assert score["code_block_count"] >= 1


def test_short_sop_fails_min_word_count():
    """500文字未満の SOP が文字数不足エラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    short_sop = "## s1\n短い\n## s2\n短い\n## s3\n```py\nx=1\n```"
    failures, score = _run_rules(short_sop)
    assert any("文字数不足" in f for f in failures)
    assert score["char_count"] < 500


def test_missing_sections_fails():
    """## 見出しが 3 個未満の場合にエラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    no_sections = "あ" * 600 + "\n```python\nx=1\n```"
    failures, _ = _run_rules(no_sections)
    assert any("セクション数不足" in f for f in failures)


def test_missing_code_block_fails():
    """コードブロックがない場合にエラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    no_code = (
        "## s1\n" + "あ" * 200
        + "\n## s2\n" + "い" * 200
        + "\n## s3\nコードなし"
    )
    failures, _ = _run_rules(no_code)
    assert any("コードブロック" in f for f in failures)


def test_placeholder_fails():
    """TODO が含まれる場合にエラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    with_todo = GOOD_SOP + "\nTODO: あとで書く"
    failures, _ = _run_rules(with_todo)
    assert any("プレースホルダー" in f for f in failures)


def test_tbd_placeholder_fails():
    """TBD が含まれる場合にエラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    with_tbd = GOOD_SOP + "\nTBD"
    failures, _ = _run_rules(with_tbd)
    assert any("プレースホルダー" in f for f in failures)


def test_multiple_failures_all_reported():
    """複数ルール違反が全て報告されることを確認。"""
    from activities.validate_sop_activity import _run_rules

    bad_sop = "短い TODO テキスト"
    failures, _ = _run_rules(bad_sop)
    assert len(failures) >= 3  # 文字数・セクション・コードブロック・プレースホルダー


@pytest.mark.asyncio
async def test_validate_activity_passed_returns_validation_result():
    """合格 SOP で ValidationResult(passed=True) が返ることを確認。"""
    from activities.validate_sop_activity import validate_sop_activity

    result = await validate_sop_activity(GOOD_SOP)
    assert isinstance(result, ValidationResult)
    assert result.passed is True
    assert result.failures == []


@pytest.mark.asyncio
async def test_validate_activity_failed_returns_validation_result():
    """不合格 SOP で ValidationResult(passed=False) と failures が返ることを確認。"""
    from activities.validate_sop_activity import validate_sop_activity

    result = await validate_sop_activity("短いSOP")
    assert isinstance(result, ValidationResult)
    assert result.passed is False
    assert len(result.failures) > 0


# ─── 禁止用語チェック (no_prohibited_terms) ──────────────────────────────────


def test_prohibited_term_miteii_fails():
    """「未定」を含む SOP が禁止用語エラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    sop_with_miteii = GOOD_SOP + "\nこの手順は未定です。"
    failures, _ = _run_rules(sop_with_miteii)
    assert any("禁止用語" in f for f in failures)


def test_prohibited_term_kakuninchuu_fails():
    """「確認中」を含む SOP が禁止用語エラーを返すことを確認。"""
    from activities.validate_sop_activity import _run_rules

    sop_with_kakuninchuu = GOOD_SOP + "\n担当者を確認中。"
    failures, _ = _run_rules(sop_with_kakuninchuu)
    assert any("禁止用語" in f for f in failures)


def test_good_sop_has_no_prohibited_terms():
    """禁止用語を含まない SOP がエラーなしで通ることを確認。"""
    from activities.validate_sop_activity import _run_rules

    failures, _ = _run_rules(GOOD_SOP)
    assert not any("禁止用語" in f for f in failures)
