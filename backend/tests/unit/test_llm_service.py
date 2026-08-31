import pytest
from unittest.mock import AsyncMock, patch

from backend.app.services.llm.base import LLMResponse, TokenUsage
from backend.app.services.llm.gemini import GeminiLLMService
from backend.app.services.llm.mock import MockLLMService


@pytest.mark.asyncio
async def test_mock_llm_service():
    mock = MockLLMService(default_response="Test answer [DOC-1]")
    resp = await mock.generate_response("System instruction", "User prompt")
    assert resp.content == "Test answer [DOC-1]"
    assert resp.token_usage.total_tokens == 185
    assert len(mock.recorded_calls) == 1
    assert mock.recorded_calls[0]["system_instruction"] == "System instruction"


def test_gemini_llm_service_requires_api_key():
    with pytest.raises(ValueError, match="API key must be provided"):
        GeminiLLMService(api_key="")


def test_gemini_llm_service_initialization():
    service = GeminiLLMService(
        api_key="fake-api-key",
        model_name="gemini-3.7-flash",
        thinking_budget=0,
    )
    assert service.model_name == "gemini-3.7-flash"
    assert service.thinking_budget == 0
