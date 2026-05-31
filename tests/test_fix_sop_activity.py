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
    """failures が�条書き形式でプロンプトに含まれることを確認。"""
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
    assert result.model == "gemini-2.5-flash-lite"
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
