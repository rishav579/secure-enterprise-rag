"""Unit tests for the reranker service.

Validates:
  - NullReranker returns top_k candidates in existing order
  - FlashRankReranker falls back gracefully to NullReranker when unavailable
  - Reranker cannot add new candidates beyond the input list
  - Reranker failure does not raise; returns RRF-ordered fallback
"""

import uuid
import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.retrieval.fusion import FusedCandidate
from backend.app.services.retrieval.reranker import NullReranker, FlashRankReranker


def _make_candidates(n: int) -> list[FusedCandidate]:
    return [
        FusedCandidate(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            tenant_id="t1",
            chunk_index=i,
            content=f"chunk content {i}",
            chunk_metadata={"page_number": 1},
            filename="doc.pdf",
            rrf_score=1.0 / (60 + i + 1),
        )
        for i in range(n)
    ]


def test_null_reranker_preserves_order_and_truncates():
    candidates = _make_candidates(10)
    nr = NullReranker()
    result = nr.rerank("query", candidates, top_k=5)
    assert len(result) == 5
    for i, c in enumerate(result):
        assert c.chunk_id == candidates[i].chunk_id


def test_null_reranker_empty_input():
    assert NullReranker().rerank("q", [], top_k=5) == []


def test_null_reranker_top_k_larger_than_input():
    candidates = _make_candidates(3)
    result = NullReranker().rerank("q", candidates, top_k=10)
    assert len(result) == 3


def test_flashrank_reranker_fallback_when_unavailable():
    """If flashrank import fails, FlashRankReranker should fall back to NullReranker behavior."""
    with patch.dict("sys.modules", {"flashrank": None}):
        rr = FlashRankReranker()
        candidates = _make_candidates(5)
        result = rr.rerank("test query", candidates, top_k=3)
        assert len(result) == 3
        # Should preserve original order (NullReranker fallback)
        for i, c in enumerate(result):
            assert c.chunk_id == candidates[i].chunk_id


def test_flashrank_reranker_failure_at_inference_time():
    """If flashrank raises during rerank(), fallback to NullReranker silently."""
    candidates = _make_candidates(5)
    rr = FlashRankReranker()
    # Force _ranker to a mock that raises
    mock_ranker = MagicMock()
    mock_ranker.rerank.side_effect = RuntimeError("ONNX error")
    rr._ranker = mock_ranker

    result = rr.rerank("test query", candidates, top_k=3)
    # Must not raise; must return top_k candidates in fallback order
    assert len(result) == 3


def test_reranker_cannot_add_candidates():
    """Reranker output must be a subset of input candidates."""
    candidates = _make_candidates(5)
    nr = NullReranker()
    result = nr.rerank("q", candidates, top_k=10)
    input_ids = {c.chunk_id for c in candidates}
    output_ids = {c.chunk_id for c in result}
    assert output_ids.issubset(input_ids)
