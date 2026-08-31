"""Unit tests for the retrieval pipeline orchestrator.

Uses MockEmbeddingService and mocked DB to avoid external dependencies.
Validates:
  - Query length bounds (too short / too long)
  - NFKC normalization
  - Embedding dimension mismatch
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from backend.app.models.user import User, UserRole
from backend.app.services.embedding.mock import MockEmbeddingService
from backend.app.services.retrieval.pipeline import RetrievalPipeline, _normalize_query, _validate_query
from backend.app.services.retrieval.reranker import NullReranker


def _mock_user():
    return User(
        id=uuid.uuid4(),
        email="u@test.com",
        hashed_password="x",
        role=UserRole.EMPLOYEE,
        tenant_id="t1",
    )


def test_normalize_query_nfkc():
    """NFKC normalization should collapse fullwidth characters."""
    assert _normalize_query("ａｂｃ") == "abc"


def test_normalize_query_strips_whitespace():
    assert _normalize_query("  hello world  ") == "hello world"


def test_normalize_query_preserves_quoted_phrase():
    """Quoted phrases must survive so websearch_to_tsquery semantics work."""
    q = '"zero trust" -legacy'
    assert _normalize_query(q) == q


def test_validate_query_too_short():
    with pytest.raises(ValueError, match="at least"):
        _validate_query("a")


def test_validate_query_empty():
    with pytest.raises(ValueError, match="at least"):
        _validate_query("")


def test_validate_query_whitespace_only():
    with pytest.raises(ValueError, match="at least"):
        _validate_query("  ")


def test_validate_query_too_long():
    with pytest.raises(ValueError, match="1000"):
        _validate_query("x" * 1001)


def test_validate_query_exact_min():
    _validate_query("ab")  # should not raise


def test_validate_query_exact_max():
    _validate_query("x" * 1000)  # should not raise


@pytest.mark.asyncio
async def test_pipeline_embedding_dimension_mismatch():
    """Pipeline must reject query embeddings with wrong dimension."""
    mock_embed = MockEmbeddingService(dimension=768)
    # Patch embed_query to return wrong size
    mock_embed.embed_query = AsyncMock(return_value=[0.1] * 512)

    pipeline = RetrievalPipeline(
        embedding_service=mock_embed,
        reranker=NullReranker(),
        embedding_dim=768,
    )

    mock_db = AsyncMock()
    user = _mock_user()

    with pytest.raises(ValueError, match="dimension"):
        await pipeline.search("valid query here", user, mock_db)
