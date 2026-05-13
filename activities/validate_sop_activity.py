"""
SOP 品質検証 Activity — ルールベースで SOP テキストを検証する。

ステートレスな純粋関数として実装し、同一入力に対して常に同一結果を返す（冪等）。
外部 API・ファイル IO を持たないため、リトライポリシー不要。

Rules:
    min_word_count      : 文字数 ≥ 500
    required_sections   : ## 見出し ≥ 3 個
    has_code_block      : バッククォート3つのブロックが 1 個以上
    no_placeholder      : TODO / TBD / [TODO] を含まない
    no_prohibited_terms : 未定 / 確認中 / 作成中 / 仮 を含まない
"""

import re

from temporalio import activity

from core.models import ValidationResult

_MIN_CHARS = 500
_MIN_SECTIONS = 3

_PROHIBITED_TERMS = ["未定", "確認中", "作成中", "仮"]


def _run_rules(sop_text: str) -> tuple[list[str], dict]:
    """
    5つのルールを評価し、失敗リストとスコア dict を返す。

    :param sop_text: 検証対象の SOP 全文
    :returns: (failures, score) のタプル
    """
    failures: list[str] = []
    score: dict = {}

    char_count = len(sop_text)
    score["char_count"] = char_count
    if char_count < _MIN_CHARS:
        failures.append(f"文字数不足: {char_count}文字 (最低{_MIN_CHARS}文字必要)")

    section_count = len(re.findall(r"^## ", sop_text, re.MULTILINE))
    score["section_count"] = section_count
    if section_count < _MIN_SECTIONS:
        failures.append(f"セクション数不足: {section_count}個 (最低{_MIN_SECTIONS}個必要)")

    backtick_count = len(re.findall(r"```", sop_text))
    score["code_block_count"] = backtick_count // 2
    if backtick_count < 2:
        failures.append("コードブロックが存在しない")

    if re.search(r"\bTODO\b|\bTBD\b|\[TODO\]", sop_text, re.IGNORECASE):
        failures.append("未完成プレースホルダーが含まれる (TODO / TBD / [TODO])")

    found = [t for t in _PROHIBITED_TERMS if t in sop_text]
    if found:
        failures.append(f"禁止用語が含まれる: {', '.join(found)}")

    return failures, score


@activity.defn
async def validate_sop_activity(sop_text: str) -> ValidationResult:
    """
    SOP テキストをルールベースで検証し ValidationResult を返す。

    :param sop_text: 検証対象の SOP 全文
    :returns: 検証結果（passed, failures, score）
    """
    failures, score = _run_rules(sop_text)
    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
        score=score,
    )
