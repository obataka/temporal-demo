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


# ─── fix_sop_with_crew_activity (CrewAI 2 エージェント版) ────────────────────


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_raises_without_api_key(monkeypatch):
    """GEMINI_API_KEY 未設定時に EnvironmentError が発生することを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
        await fix_sop_with_crew_activity("SOP テキスト", ["失敗理由"])


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_returns_llm_result():
    """CrewAI が応答した場合に LLMResult が正しく返ることを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity

    mock_task_output = MagicMock()
    mock_task_output.raw = "CrewAI による修正済み SOP"

    mock_crew_output = MagicMock()
    mock_crew_output.tasks_output = [mock_task_output]
    mock_crew_output.token_usage.total_tokens = 500

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = mock_crew_output

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("crewai.LLM"):
            with patch(
                "activities.fix_sop_activity._build_sop_crew",
                return_value=mock_crew,
            ):
                result = await fix_sop_with_crew_activity(
                    "元の SOP",
                    ["文字数不足: 200文字"],
                    "セキュリティ項目を追加してください",
                )

    assert isinstance(result, LLMResult)
    assert result.text == "CrewAI による修正済み SOP"
    assert result.model == "gemini/gemini-2.5-flash"
    assert result.total_tokens == 500
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_passes_args_to_crew():
    """sop_text・failures・human_feedback が _build_sop_crew に正しく渡ることを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity
    from unittest.mock import ANY

    mock_crew_output = MagicMock()
    mock_crew_output.tasks_output = [MagicMock(raw="修正済み")]
    mock_crew_output.token_usage.total_tokens = 100

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = mock_crew_output

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("crewai.LLM"):
            with patch(
                "activities.fix_sop_activity._build_sop_crew",
                return_value=mock_crew,
            ) as mock_build:
                await fix_sop_with_crew_activity(
                    "対象 SOP",
                    ["失敗項目A"],
                    "セキュリティ項目を追加してください",
                )

    mock_build.assert_called_once_with(
        "対象 SOP",
        ["失敗項目A"],
        "セキュリティ項目を追加してください",
        ANY,
        0,  # attempt デフォルト値
    )


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_returns_agent_logs():
    """tasks_output[1].raw（Reviewer 出力）が LLMResult.agent_logs に格納されることを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity

    mock_writer_output = MagicMock()
    mock_writer_output.raw = "修正済み SOP"
    mock_reviewer_output = MagicMock()
    mock_reviewer_output.raw = "【Reviewer】セキュリティ上の懸念: 認証フロー欠如（重大度: 高）"

    mock_crew_output = MagicMock()
    mock_crew_output.tasks_output = [mock_writer_output, mock_reviewer_output]
    mock_crew_output.token_usage.total_tokens = 600

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = mock_crew_output

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("crewai.LLM"):
            with patch(
                "activities.fix_sop_activity._build_sop_crew",
                return_value=mock_crew,
            ):
                result = await fix_sop_with_crew_activity("元の SOP", ["文字数不足"])

    assert result.text == "修正済み SOP"
    assert "Reviewer" in result.agent_logs
    assert "認証フロー欠如" in result.agent_logs


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_agent_logs_empty_when_single_task_output():
    """tasks_output が Writer の1件のみの場合、agent_logs が空文字になることを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity

    mock_writer_output = MagicMock()
    mock_writer_output.raw = "修正済み SOP（レビューなし）"

    mock_crew_output = MagicMock()
    mock_crew_output.tasks_output = [mock_writer_output]
    mock_crew_output.token_usage.total_tokens = 200

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = mock_crew_output

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("crewai.LLM"):
            with patch(
                "activities.fix_sop_activity._build_sop_crew",
                return_value=mock_crew,
            ):
                result = await fix_sop_with_crew_activity("元の SOP", [])

    assert result.agent_logs == ""


# ─── temperature / urgency 動的チューニング ──────────────────────────────────


def test_temperature_by_round_table():
    """_TEMPERATURE_BY_ROUND の値が設計書通りであることを確認。"""
    from activities.fix_sop_activity import _TEMPERATURE_BY_ROUND

    assert _TEMPERATURE_BY_ROUND[0] == 0.3
    assert _TEMPERATURE_BY_ROUND[1] == 0.6
    assert _TEMPERATURE_BY_ROUND[2] == 0.9
    # 未定義キーは .get(attempt, 0.9) でフォールバックするため、テーブル外の値は存在しない
    assert 3 not in _TEMPERATURE_BY_ROUND


def test_urgency_prefix_by_round_table():
    """_URGENCY_PREFIX_BY_ROUND の構造を確認。"""
    from activities.fix_sop_activity import _URGENCY_PREFIX_BY_ROUND

    assert _URGENCY_PREFIX_BY_ROUND[0] == ""
    assert "重要" in _URGENCY_PREFIX_BY_ROUND[1]
    assert "最終修正" in _URGENCY_PREFIX_BY_ROUND[2]


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_passes_attempt_to_build_crew():
    """attempt=2 を渡したとき _build_sop_crew に attempt=2 がリレーされることを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity
    from unittest.mock import ANY

    mock_crew_output = MagicMock()
    mock_crew_output.tasks_output = [MagicMock(raw="修正済み")]
    mock_crew_output.token_usage.total_tokens = 100

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = mock_crew_output

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("crewai.LLM"):
            with patch(
                "activities.fix_sop_activity._build_sop_crew",
                return_value=mock_crew,
            ) as mock_build:
                await fix_sop_with_crew_activity(
                    "対象 SOP",
                    ["失敗項目A"],
                    "",
                    2,
                )

    mock_build.assert_called_once_with(
        "対象 SOP",
        ["失敗項目A"],
        "",
        ANY,
        2,
    )


@pytest.mark.asyncio
async def test_fix_sop_with_crew_activity_backward_compatible_without_attempt():
    """attempt 引数を省略したとき（デフォルト 0）正常に動作することを確認。"""
    from activities.fix_sop_activity import fix_sop_with_crew_activity

    mock_crew_output = MagicMock()
    mock_crew_output.tasks_output = [MagicMock(raw="後方互換テスト用 SOP")]
    mock_crew_output.token_usage.total_tokens = 50

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = mock_crew_output

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("crewai.LLM"):
            with patch(
                "activities.fix_sop_activity._build_sop_crew",
                return_value=mock_crew,
            ):
                result = await fix_sop_with_crew_activity("SOP", ["失敗"])

    assert isinstance(result, LLMResult)
    assert result.text == "後方互換テスト用 SOP"
