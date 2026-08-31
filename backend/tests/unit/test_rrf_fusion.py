"""Unit tests for RRF fusion algorithm.

Validates:
  - RRF score formula: 1/(60+rank)
  - Overlap boosting: chunks in both lists score higher than single-list chunks
  - Missing retriever handling: chunk from only one list still scored correctly
  - Deterministic tie-breaking: same inputs → same order
  - top-k truncation
  - Score semantics: rrf_score is NOT vector_similarity (different ranges)
"""

import uuid
import pytest
from backend.app.services.retrieval.fusion import fuse_rrf, _RRF_K
from backend.app.services.retrieval.lexical import LexicalSearchResult
from backend.app.services.retrieval.vector import VectorSearchResult


def _lex(chunk_id: uuid.UUID, rank: int, score: float = 0.5) -> LexicalSearchResult:
    return LexicalSearchResult(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        tenant_id="t",
        chunk_index=0,
        content="text",
        chunk_metadata={},
        filename="f.pdf",
        lexical_rank=rank,
        lexical_score=score,
    )


def _vec(chunk_id: uuid.UUID, rank: int, dist: float = 0.1) -> VectorSearchResult:
    return VectorSearchResult(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        tenant_id="t",
        chunk_index=0,
        content="text",
        chunk_metadata={},
        filename="f.pdf",
        vector_rank=rank,
        vector_distance=dist,
        vector_similarity=1.0 - dist,
    )


def test_rrf_single_list_only_lexical():
    cid = uuid.uuid4()
    result = fuse_rrf([_lex(cid, 1)], [])
    assert len(result) == 1
    assert result[0].chunk_id == cid
    expected = 1.0 / (_RRF_K + 1)
    assert abs(result[0].rrf_score - expected) < 1e-9
    assert result[0].lexical_rank == 1
    assert result[0].vector_rank is None
    assert "lexical" in result[0].retrieval_methods
    assert "vector" not in result[0].retrieval_methods


def test_rrf_single_list_only_vector():
    cid = uuid.uuid4()
    result = fuse_rrf([], [_vec(cid, 1)])
    assert len(result) == 1
    expected = 1.0 / (_RRF_K + 1)
    assert abs(result[0].rrf_score - expected) < 1e-9
    assert "vector" in result[0].retrieval_methods


def test_rrf_overlap_boosting():
    """Chunk appearing in both lists must outscore chunks in only one list."""
    shared_id = uuid.uuid4()
    lex_only_id = uuid.uuid4()
    vec_only_id = uuid.uuid4()

    lex = [_lex(shared_id, 1), _lex(lex_only_id, 2)]
    vec = [_vec(shared_id, 1), _vec(vec_only_id, 2)]

    results = fuse_rrf(lex, vec)
    by_id = {r.chunk_id: r for r in results}

    shared_score = by_id[shared_id].rrf_score
    lex_only_score = by_id[lex_only_id].rrf_score
    vec_only_score = by_id[vec_only_id].rrf_score

    assert shared_score > lex_only_score, "Overlap chunk must score higher than lex-only"
    assert shared_score > vec_only_score, "Overlap chunk must score higher than vec-only"
    assert results[0].chunk_id == shared_id


def test_rrf_score_not_cosine_similarity():
    """RRF score and vector_similarity occupy different ranges and are not interchangeable."""
    cid = uuid.uuid4()
    results = fuse_rrf([_lex(cid, 1)], [_vec(cid, 1, dist=0.05)])
    r = results[0]
    # RRF max when rank-1 in both: 2/(60+1) ≈ 0.0328
    assert r.rrf_score < 0.1, "RRF scores are small rank-based values"
    assert r.vector_similarity is not None
    assert r.vector_similarity > 0.9, "Similarity is near 1.0 for dist=0.05"
    # They must not be equal
    assert abs(r.rrf_score - r.vector_similarity) > 0.8


def test_rrf_topk_truncation():
    chunk_ids = [uuid.uuid4() for _ in range(10)]
    lex = [_lex(cid, i + 1) for i, cid in enumerate(chunk_ids)]
    results = fuse_rrf(lex, [], k=5)
    assert len(results) == 5


def test_rrf_deterministic():
    """Identical inputs must produce identical ordering."""
    ids = [uuid.uuid4() for _ in range(5)]
    lex = [_lex(cid, i + 1) for i, cid in enumerate(ids)]
    vec = [_vec(cid, i + 1) for i, cid in enumerate(reversed(ids))]
    r1 = [c.chunk_id for c in fuse_rrf(lex, vec)]
    r2 = [c.chunk_id for c in fuse_rrf(lex, vec)]
    assert r1 == r2


def test_rrf_empty_both():
    assert fuse_rrf([], []) == []
