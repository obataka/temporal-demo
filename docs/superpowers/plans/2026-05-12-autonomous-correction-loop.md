# Autonomous Correction Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sop_generation_workflow` の review フェーズ完了後に、ルールベース検証と AI 修正の自律ループ（最大3回）を追加する。

**Architecture:** Workflow 内に `while fix_attempt < 3` のループを追加し、`validate_sop_activity`（ルールベース・冪等）と `fix_sop_activity`（Gemini 呼び出し）の2つの新規 Activity を逐次実行する。ループカウンタは Workflow インスタンス変数として管理され、Worker 再起動後も Temporal の Event History から自動復元される。全ての非決定的処理（Gemini 呼び出し）は Activity に閉じ込める。

**Tech Stack:** Python 3.13, Temporal Python SDK (`temporalio`), Gemini 2.5 Flash (`google-genai`), pytest 9.0 + pytest-asyncio (STRICT mode), unittest.mock

---

## File Map

| ファイル | 種別 | 変更内容 |
| :--- | :--- | :--- |
| `core/models.py` | 修正 | `ValidationResult` データクラス追加 |
| `activities/validate_sop_activity.py` | **新規** | ルールベース SOP 検証 Activity |
| `activities/fix_sop_activity.py` | **新規** | Gemini による自律修正 Activity |
| `workflows/sop_workflow.py` | 修正 | Phase 4 ループ・状態変数・Query 更新 |
| `worker.py` | 修正 | 2 Activity を Worker に登録 |
| `tests/test_models.py` | **新規** | `ValidationResult` の単体テスト |
| `tests/test_validate_sop_activity.py` | **新規** | 検証 Activity の単体テスト |
| `tests/test_fix_sop_activity.py` | **新規** | 修正 Activity の単体テスト（Gemini モック）|

---

## Task 1: `ValidationResult` を `core/models.py` に追加

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_models.py` (新規)

- [ ] **Step 1: テストを書く**

`tests/test_models.py` を新規作成:

```python
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
```

- [ ] **Step 2: テストを実行して FAIL を確認**

```bash
source .venv/bin/activate && python -m pytest tests/test_models.py -v
```

期待: `ImportError` または `AttributeError`（`ValidationResult` 未定義）

- [ ] **Step 3: `core/models.py` の末尾に `ValidationResult` を追加**

`core/models.py` の最終行（`feedback: Optional[str] = None` の後）に追記:

```python
@dataclass
class ValidationResult:
    """SOP 品質検証の結果。validate_sop_activity が返す。"""
    passed: bool
    failures: list[str]
    score: dict
```

- [ ] **Step 4: テストを実行して PASS を確認**

```bash
source .venv/bin/activate && python -m pytest tests/test_models.py -v
```

期待: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat: add ValidationResult dataclass to core/models"
```

---

## Task 2: `validate_sop_activity` を作成

**Files:**
- Create: `activities/validate_sop_activity.py`
- Test: `tests/test_validate_sop_activity.py` (新規)

- [ ] **Step 1: テストを書く**

`tests/test_validate_sop_activity.py` を新規作成:

```python
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
```

- [ ] **Step 2: テストを実行して FAIL を確認**

```bash
source .venv/bin/activate && python -m pytest tests/test_validate_sop_activity.py -v
```

期待: `ImportError`（`validate_sop_activity` 未作成）

- [ ] **Step 3: `activities/validate_sop_activity.py` を作成**

```python
"""
SOP 品質検証 Activity — ルールベースで SOP テキストを検証する。

ステートレスな純粋関数として実装し、同一入力に対して常に同一結果を返す（冪等）。
外部 API・ファイル IO を持たないため、リトライポリシー不要。

Rules:
    min_word_count    : 文字数 ≥ 500
    required_sections : ## 見出し ≥ 3 個
    has_code_block    : バッククォート3つのブロックが 1 個以上
    no_placeholder    : TODO / TBD / [TODO] を含まない
"""

import re

from temporalio import activity

from core.models import ValidationResult

_MIN_CHARS = 500
_MIN_SECTIONS = 3


def _run_rules(sop_text: str) -> tuple[list[str], dict]:
    """
    4つのルールを評価し、失敗リストとスコア dict を返す。

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
```

- [ ] **Step 4: テストを実行して PASS を確認**

```bash
source .venv/bin/activate && python -m pytest tests/test_validate_sop_activity.py -v
```

期待: `9 passed`

- [ ] **Step 5: コミット**

```bash
git add activities/validate_sop_activity.py tests/test_validate_sop_activity.py
git commit -m "feat: add validate_sop_activity with rule-based SOP quality checks"
```

---

## Task 3: `fix_sop_activity` を作成

**Files:**
- Create: `activities/fix_sop_activity.py`
- Test: `tests/test_fix_sop_activity.py` (新規)

- [ ] **Step 1: テストを書く**

`tests/test_fix_sop_activity.py` を新規作成:

```python
"""
fix_sop_activity の単体テスト。
Gemini クライアントをモックして API キー・ネットワーク不要で実行する。
"""

import pytest
from unittest.mock import patch, MagicMock
from core.models import LLMResult


def test_build_prompt_includes_failures():
    """プロンプトに failures と sop_text が両方含まれることを確認。"""
    from activities.fix_sop_activity import _build_prompt

    failures = ["文字数不足: 200文字 (最低500文字必要)", "セクション数不足: 1個"]
    prompt = _build_prompt("元のSOPテキスト", failures)

    assert "文字数不足: 200文字" in prompt
    assert "セクション数不足: 1個" in prompt
    assert "元のSOPテキスト" in prompt


def test_build_prompt_formats_failures_as_list():
    """failures が箇条書き形式でプロンプトに含まれることを確認。"""
    from activities.fix_sop_activity import _build_prompt

    prompt = _build_prompt("SOP", ["問題A", "問題B"])
    assert "- 問題A" in prompt
    assert "- 問題B" in prompt


@pytest.mark.asyncio
async def test_fix_activity_raises_without_api_key(monkeypatch):
    """GEMINI_API_KEY 未設定時に EnvironmentError が発生することを確認。"""
    from activities.fix_sop_activity import fix_sop_activity

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
        await fix_sop_activity("SOP テキスト", ["失敗理由"])


@pytest.mark.asyncio
async def test_fix_activity_returns_llm_result():
    """Gemini が応答した場合に LLMResult が正しく返ることを確認。"""
    from activities.fix_sop_activity import fix_sop_activity

    mock_response = MagicMock()
    mock_response.text = "修正済み SOP テキスト"
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 200
    mock_response.usage_metadata.total_token_count = 300

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_response

            result = await fix_sop_activity("元のSOP", ["文字数不足: 200文字"])

    assert isinstance(result, LLMResult)
    assert result.text == "修正済み SOP テキスト"
    assert result.total_tokens == 300
    assert result.model == "gemini-2.5-flash"
    assert result.input_tokens == 100
    assert result.output_tokens == 200


@pytest.mark.asyncio
async def test_fix_activity_passes_failures_to_gemini():
    """failures の内容が Gemini への contents に含まれることを確認。"""
    from activities.fix_sop_activity import fix_sop_activity

    captured_contents: list[str] = []

    mock_response = MagicMock()
    mock_response.text = "修正済み"
    mock_response.usage_metadata.prompt_token_count = 10
    mock_response.usage_metadata.candidates_token_count = 20
    mock_response.usage_metadata.total_token_count = 30

    def capture_call(**kwargs):
        captured_contents.append(kwargs.get("contents", ""))
        return mock_response

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.side_effect = capture_call

            await fix_sop_activity("元のSOP", ["セクション数不足: 1個"])

    assert len(captured_contents) == 1
    assert "セクション数不足: 1個" in captured_contents[0]
```

- [ ] **Step 2: テストを実行して FAIL を確認**

```bash
source .venv/bin/activate && python -m pytest tests/test_fix_sop_activity.py -v
```

期待: `ImportError`（`fix_sop_activity` 未作成）

- [ ] **Step 3: `activities/fix_sop_activity.py` を作成**

```python
"""
SOP 自律修正 Activity — バリデーション失敗項目を Gemini に渡して修正版を生成する。

failures リストをプロンプトに注入し、最小限の変更で全指摘を解消した
改善版 SOP を Gemini 2.5 Flash に生成させる。
"""

import os
import time

from temporalio import activity

from core.models import LLMResult

_MODEL = "gemini-2.5-flash"

_SYSTEM_INSTRUCTION = (
    "あなたは SOP 品質改善の専門家です。"
    "提供された SOP ドキュメントの問題点リストを確認し、"
    "全ての問題を解消した改善版 SOP を Markdown 形式で出力してください。"
    "内容の本質は変えず、最小限の修正で問題を解消してください。"
    "改善理由の説明は不要です。改善版 SOP のみを出力してください。"
)


def _build_prompt(sop_text: str, failures: list[str]) -> str:
    """
    SOP テキストと失敗リストから修正依頼プロンプトを構築する。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :returns: Gemini に送信するプロンプト文字列
    """
    failures_str = "\n".join(f"- {f}" for f in failures)
    return (
        f"## 修正が必要な問題点\n{failures_str}\n\n"
        f"## 修正対象の SOP\n{sop_text}\n\n"
        "---\n上記の問題点を全て解消した改善版 SOP を出力してください。"
    )


@activity.defn
async def fix_sop_activity(sop_text: str, failures: list[str]) -> LLMResult:
    """
    バリデーション失敗項目を修正した SOP を Gemini に生成させる。

    :param sop_text: 修正対象の SOP 全文
    :param failures: validate_sop_activity が返した失敗メッセージのリスト
    :returns: 修正済み SOP を含む LLMResult
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)
    contents = _build_prompt(sop_text, failures)

    start = time.monotonic()
    response = client.models.generate_content(
        model=_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_INSTRUCTION),
    )
    latency_ms = (time.monotonic() - start) * 1000

    usage = response.usage_metadata
    return LLMResult(
        text=response.text,
        model=_MODEL,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        total_tokens=getattr(usage, "total_token_count", 0) or 0,
        latency_ms=round(latency_ms, 2),
    )
```

- [ ] **Step 4: テストを実行して PASS を確認**

```bash
source .venv/bin/activate && python -m pytest tests/test_fix_sop_activity.py -v
```

期待: `5 passed`

- [ ] **Step 5: コミット**

```bash
git add activities/fix_sop_activity.py tests/test_fix_sop_activity.py
git commit -m "feat: add fix_sop_activity for AI-powered SOP correction"
```

---

## Task 4: `sop_generation_workflow.py` に Phase 4 を追加

**Files:**
- Modify: `workflows/sop_workflow.py`

- [ ] **Step 1: インポートを3箇所更新する**

**1a. `from core.models` の行を修正** (`workflows/sop_workflow.py:27`):

変更前:
```python
from core.models import SOPRequest, LLMResult
```
変更後:
```python
from core.models import SOPRequest, LLMResult, ValidationResult
```

**1b. `ApplicationError` のインポートを追加** (`workflows/sop_workflow.py:25` の下に追記):

```python
from temporalio.exceptions import ApplicationError
```

**1c. `workflow.unsafe.imports_passed_through()` ブロックを拡張** (`workflows/sop_workflow.py:29-31`):

変更前:
```python
with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
```
変更後:
```python
with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
    from activities.validate_sop_activity import validate_sop_activity
    from activities.fix_sop_activity import fix_sop_activity
```

- [ ] **Step 2: 定数 `MAX_FIX_ATTEMPTS` と `PHASE_LABELS` 更新を追加する**

`PHASE_LABELS` の辞書 (`workflows/sop_workflow.py:34-38`) を修正し、`MAX_FIX_ATTEMPTS` を追加:

変更前:
```python
PHASE_LABELS = {
    "outline": "フェーズ1: 章立て提案",
    "draft":   "フェーズ2: 詳細執筆",
    "review":  "フェーズ3: 最終レビュー",
}
```
変更後:
```python
PHASE_LABELS = {
    "outline":        "フェーズ1: 章立て提案",
    "draft":          "フェーズ2: 詳細執筆",
    "review":         "フェーズ3: 最終レビュー",
    "autonomous_fix": "フェーズ4: 自律修正",
}

MAX_FIX_ATTEMPTS = 3
```

- [ ] **Step 3: `__init__` に状態変数を2つ追加する**

`__init__` の末尾 (`_history: list[dict] = []` の後) に追加:

```python
        # 自律修正ループ状態
        self._fix_attempt: int = 0
        self._validation_result: dict | None = None
```

- [ ] **Step 4: `get_status()` に2フィールド追加する**

`get_status()` の return dict (`workflows/sop_workflow.py:77-84`) を修正:

変更前:
```python
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "phase_label": PHASE_LABELS.get(self._current_phase, self._current_phase),
            "attempt_in_phase": self._attempt_in_phase,
            "current_output": self._current_output,
            "approved_phases": list(self._approved.keys()),
        }
```
変更後:
```python
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "phase_label": PHASE_LABELS.get(self._current_phase, self._current_phase),
            "attempt_in_phase": self._attempt_in_phase,
            "current_output": self._current_output,
            "approved_phases": list(self._approved.keys()),
            "fix_attempt": self._fix_attempt,
            "validation_result": self._validation_result,
        }
```

- [ ] **Step 5: `run()` に Phase 4 ループを追加する**

`run()` の末尾 (`workflows/sop_workflow.py:152-161`)、現在の `self._status = "completed"` の直前に Phase 4 を挿入:

変更前:
```python
        self._status = "completed"
        self._current_phase = "completed"

        return {
            "topic": topic,
            "outline": self._approved.get("outline", ""),
            "draft": self._approved.get("draft", ""),
            "review": self._approved.get("review", ""),
            "history": self._history,
        }
```
変更後:
```python
        # ── Phase 4: 自律修正ループ ────────────────────────────────────────────
        self._current_phase = "autonomous_fix"
        final_sop = self._approved["review"]

        while self._fix_attempt < MAX_FIX_ATTEMPTS:
            self._status = "validating"
            v_result = await self._call_validate(final_sop)
            self._validation_result = {
                "passed": v_result.passed,
                "failures": v_result.failures,
                "score": v_result.score,
            }

            if v_result.passed:
                self._approved["review"] = final_sop
                break

            self._status = "fixing"
            fix_result = await self._call_fix(final_sop, v_result.failures)
            final_sop = fix_result.text
            self._history.append({
                "phase": "autonomous_fix",
                "phase_label": PHASE_LABELS["autonomous_fix"],
                "attempt": self._fix_attempt,
                "failures": v_result.failures,
                "output": fix_result.text,
                "tokens": fix_result.total_tokens,
                "latency_ms": fix_result.latency_ms,
                "approved": False,
            })
            self._fix_attempt += 1
        else:
            raise ApplicationError(
                "自律修正失敗: 最大試行回数超過",
                non_retryable=True,
            )

        self._status = "completed"
        self._current_phase = "completed"

        return {
            "topic": topic,
            "outline": self._approved.get("outline", ""),
            "draft": self._approved.get("draft", ""),
            "review": self._approved.get("review", ""),
            "history": self._history,
        }
```

- [ ] **Step 6: `_call_validate` と `_call_fix` メソッドを追加する**

`_call_llm` メソッド (`workflows/sop_workflow.py:163-169`) の末尾に追記:

```python
    async def _call_validate(self, sop_text: str) -> ValidationResult:
        """
        validate_sop_activity を実行して ValidationResult を返す。

        :param sop_text: 検証対象の SOP 全文
        :returns: 検証結果
        """
        return await workflow.execute_activity(
            validate_sop_activity,
            sop_text,
            start_to_close_timeout=timedelta(seconds=30),
        )

    async def _call_fix(self, sop_text: str, failures: list[str]) -> LLMResult:
        """
        fix_sop_activity を実行して修正済み SOP を返す。

        :param sop_text: 修正対象の SOP 全文
        :param failures: validate_sop_activity が返した失敗メッセージのリスト
        :returns: 修正済み SOP を含む LLMResult
        """
        return await workflow.execute_activity(
            fix_sop_activity,
            args=[sop_text, failures],
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=LLM_RETRY_POLICY,
        )
```

- [ ] **Step 7: インポートエラーがないことを確認**

```bash
source .venv/bin/activate && python -c "from workflows.sop_workflow import sop_generation_workflow; print('OK')"
```

期待: `OK`

- [ ] **Step 8: 全既存テストが引き続き PASS することを確認**

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

期待: 全テスト PASS（新規テスト含む）

- [ ] **Step 9: コミット**

```bash
git add workflows/sop_workflow.py
git commit -m "feat: add Phase 4 autonomous correction loop to sop_generation_workflow"
```

---

## Task 5: `worker.py` に Activity を登録

**Files:**
- Modify: `worker.py`

- [ ] **Step 1: インポートを追加する**

`worker.py` の Activity インポート群 (`worker.py:25-26`) に2行追加:

変更前:
```python
from activities.crew_activity import merge_reviews_activity, run_agent_activity
from activities.sop_activity import generate_sop_phase_activity
```
変更後:
```python
from activities.crew_activity import merge_reviews_activity, run_agent_activity
from activities.fix_sop_activity import fix_sop_activity
from activities.sop_activity import generate_sop_phase_activity
from activities.validate_sop_activity import validate_sop_activity
```

- [ ] **Step 2: Worker の `activities` リストに登録する**

`worker.py:65` の `activities=[...]` に追加:

変更前:
```python
        activities=[call_llm_activity, call_llm_with_context_activity, call_mock_llm_activity, generate_sop_phase_activity, run_agent_activity, merge_reviews_activity],
```
変更後:
```python
        activities=[
            call_llm_activity,
            call_llm_with_context_activity,
            call_mock_llm_activity,
            generate_sop_phase_activity,
            validate_sop_activity,
            fix_sop_activity,
            run_agent_activity,
            merge_reviews_activity,
        ],
```

- [ ] **Step 3: インポートエラーがないことを確認**

```bash
source .venv/bin/activate && python -c "import worker; print('OK')"
```

期待: `OK`

- [ ] **Step 4: 全テスト PASS を確認**

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

期待: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add worker.py
git commit -m "feat: register validate_sop_activity and fix_sop_activity in worker"
```

---

## セルフレビュー結果

**Spec coverage チェック:**
- ✅ `ValidationResult` データクラス → Task 1
- ✅ `validate_sop_activity`（4ルール） → Task 2
- ✅ `fix_sop_activity`（Gemini 呼び出し） → Task 3
- ✅ Phase 4 ループ（while-else、最大3回） → Task 4
- ✅ `get_status()` に `fix_attempt` / `validation_result` 追加 → Task 4
- ✅ `self._approved["review"]` を fix 後の最終版で更新 → Task 4
- ✅ `worker.py` への Activity 登録 → Task 5
- ✅ `ApplicationError(non_retryable=True)` で終了 → Task 4

**Placeholder scan:** なし

**Type consistency チェック:**
- `validate_sop_activity(sop_text: str) -> ValidationResult` — Task 2 定義, Task 4 呼び出し ✅
- `fix_sop_activity(sop_text: str, failures: list[str]) -> LLMResult` — Task 3 定義, Task 4 呼び出し ✅
- `_call_validate(self, sop_text: str) -> ValidationResult` — Task 4 定義・使用 ✅
- `_call_fix(self, sop_text: str, failures: list[str]) -> LLMResult` — Task 4 定義・使用 ✅
