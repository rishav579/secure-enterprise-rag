from unittest.mock import MagicMock, patch
import pytest

from backend.app.services.embedding.base import (
    EmbeddingDimensionError,
    EmbeddingProviderError,
)
from backend.app.services.embedding.gemini import GeminiEmbeddingService
from backend.app.services.embedding.mock import MockEmbeddingService


@pytest.mark.asyncio
async def test_mock_embedding_service_dimension_and_normalization():
    service = MockEmbeddingService(dimension=768)
    vectors = await service.embed_texts(["hello world", "enterprise security"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 768
    assert len(vectors[1]) == 768

    # Verify unit normalization: sqrt(sum(x^2)) ~= 1.0
    norm_0 = sum(x * x for x in vectors[0]) ** 0.5
    assert abs(norm_0 - 1.0) < 1e-4

    # Single query
    q_vec = await service.embed_query("search query")
    assert len(q_vec) == 768


@pytest.mark.asyncio
async def test_gemini_embedding_service_dimension_validation():
    # Mock client returning wrong dimension (e.g. 512 instead of 768)
    with patch("backend.app.services.embedding.gemini.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_emb = MagicMock()
        mock_emb.values = [0.1] * 512  # Mismatched 512
        mock_response.embeddings = [mock_emb]
        mock_client.models.embed_content.return_value = mock_response

        service = GeminiEmbeddingService(api_key="test-key", dimension=768)

        with pytest.raises(EmbeddingDimensionError, match="expected 768, got 512"):
            await service.embed_texts(["test text"])


@pytest.mark.asyncio
async def test_gemini_embedding_service_retry_and_success():
    with patch("backend.app.services.embedding.gemini.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_success_resp = MagicMock()
        mock_emb = MagicMock()
        mock_emb.values = [0.05] * 768
        mock_success_resp.embeddings = [mock_emb]

        # Fail first attempt, succeed on second attempt
        mock_client.models.embed_content.side_effect = [
            Exception("Transient 503 rate limit"),
            mock_success_resp,
        ]

        service = GeminiEmbeddingService(
            api_key="test-key",
            dimension=768,
            max_retries=2,
            base_delay_seconds=0.01,
        )

        vectors = await service.embed_texts(["retry test"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 768
        assert mock_client.models.embed_content.call_count == 2


@pytest.mark.asyncio
async def test_gemini_embedding_service_permanent_failure():
    with patch("backend.app.services.embedding.gemini.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Always fail
        mock_client.models.embed_content.side_effect = Exception("Persistent API Error")

        service = GeminiEmbeddingService(
            api_key="test-key",
            dimension=768,
            max_retries=2,
            base_delay_seconds=0.01,
        )

        with pytest.raises(EmbeddingProviderError, match="failed after 2 attempts"):
            await service.embed_texts(["fail test"])
