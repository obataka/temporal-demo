"""
モック Activity を使った Observability のテスト。
Temporal サーバ・API キー不要で実行できる。
"""

import asyncio
import json
import pytest
import structlog

from core.models import LLMResult
from core.observability import log_llm_interaction


# --------------------------------------------------------------------------- #
# log_llm_interaction のテスト                                                 #
# --------------------------------------------------------------------------- #

def test_log_llm_interaction_success(capsys):
    """成功時に JSON ログが出力され、必須フィールドが含まれることを確認。"""
    result = LLMResult(
        text="テスト応答",
        model="test-model",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        latency_ms=123.4,
    )

    with log_llm_interaction("test-model", "テストプロンプト") as result_box:
        result_box.append(result)

    captured = capsys.readouterr()
    log = json.loads(captured.out.strip())

    assert log["status"] == "success"
    assert log["model"] == "test-model"
    assert log["input_tokens"] == 100
    assert log["output_tokens"] == 200
    assert log["total_tokens"] == 300
    assert "latency_ms" in log
    assert "prompt_summary" in log
    assert "output_summary" in log


def test_log_llm_interaction_error(capsys):
    """例外発生時に error ログが出力され、例外が再送出されることを確認。"""
    with pytest.raises(RuntimeError, match="テストエラー"):
        with log_llm_interaction("test-model", "テストプロンプト"):
            raise RuntimeError("テストエラー")

    captured = capsys.readouterr()
    log = json.loads(captured.out.strip())

    assert log["status"] == "error"
    assert "テストエラー" in log["error"]
    assert "latency_ms" in log


def test_prompt_summary_truncated(capsys):
    """120文字超のプロンプトが切り詰められることを確認。"""
    long_prompt = "あ" * 200
    result = LLMResult(
        text="応答", model="test-model",
        input_tokens=10, output_tokens=10, total_tokens=20, latency_ms=1.0
    )

    with log_llm_interaction("test-model", long_prompt) as result_box:
        result_box.append(result)

    captured = capsys.readouterr()
    log = json.loads(captured.out.strip())
    assert log["prompt_summary"].endswith("…")


# --------------------------------------------------------------------------- #
# Mock Activity のテスト                                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_mock_activity_returns_llm_result(capsys):
    """Mock Activity が LLMResult を返し、JSON ログが出力されることを確認。"""
    from activities.mock_activity import call_mock_llm_activity

    result = await call_mock_llm_activity("テストプロンプト")

    assert result.model == "mock-llm-v1"
    assert result.input_tokens > 0
    assert result.output_tokens > 0
    assert result.total_tokens == result.input_tokens + result.output_tokens
    assert result.latency_ms > 0
    assert len(result.text) > 0

    # JSON ログが出力されているか確認
    captured = capsys.readouterr()
    log = json.loads(captured.out.strip())
    assert log["status"] == "success"
    assert log["model"] == "mock-llm-v1"
