"""Reciprocal Rank Fusion (RRF) over lexical and vector candidate lists.

RRF score for chunk d:
    score(d) = sum over method m in {lexical, vector}:
                   1 / (K_RRF + rank_m(d))

where rank is 1-indexed and K_RRF = 60 (standard TREC benchmark constant).

RRF scores are NOT interchangeable with cosine similarity scores. The maximum
possible RRF score when a chunk appears in both retrievers at rank 1 each is
2 / (60 + 1) ≈ 0.0328.

If a chunk appears in only one retriever, it gets contribution from that retriever
only. Missing retriever position contributes 0 to the sum.

Tie-breaking: primary = rrf_score DESC, secondary = vector_similarity DESC
(lower distance means higher similarity), tertiary = chunk_id ASC (deterministic).
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.app.services.retrieval.lexical import LexicalSearchResult
from backend.app.services.retrieval.vector import VectorSearchResult

_RRF_K = 60  # Standard TREC 2009 constant


@dataclass
class FusedCandidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    tenant_id: str
    chunk_index: int
    content: str
    chunk_metadata: dict
    filename: str
    # Score breakdown — each is Optional because a chunk may come from only one retriever
    lexical_rank: Optional[int] = None
    lexical_score: Optional[float] = None
    vector_rank: Optional[int] = None
    vector_distance: Optional[float] = None
    vector_similarity: Optional[float] = None
    rrf_score: float = 0.0
    retrieval_methods: List[str] = field(default_factory=list)
    # Post-reranking score (populated downstream)
    reranker_score: Optional[float] = None


def fuse_rrf(
    lexical_results: List[LexicalSearchResult],
    vector_results: List[VectorSearchResult],
    k: int = 20,
) -> List[FusedCandidate]:
    """Merge lexical and vector candidates via Reciprocal Rank Fusion.

    Returns at most k candidates, sorted by rrf_score DESC, then
    vector_similarity DESC, then chunk_id ASC for determinism.
    """
    index: Dict[uuid.UUID, FusedCandidate] = {}

    for r in lexical_results:
        cid = r.chunk_id
        if cid not in index:
            index[cid] = FusedCandidate(
                chunk_id=cid,
                document_id=r.document_id,
                tenant_id=r.tenant_id,
                chunk_index=r.chunk_index,
                content=r.content,
                chunk_metadata=r.chunk_metadata,
                filename=r.filename,
            )
        c = index[cid]
        c.lexical_rank = r.lexical_rank
        c.lexical_score = r.lexical_score
        c.rrf_score += 1.0 / (_RRF_K + r.lexical_rank)
        if "lexical" not in c.retrieval_methods:
            c.retrieval_methods.append("lexical")

    for r in vector_results:
        cid = r.chunk_id
        if cid not in index:
            index[cid] = FusedCandidate(
                chunk_id=cid,
                document_id=r.document_id,
                tenant_id=r.tenant_id,
                chunk_index=r.chunk_index,
                content=r.content,
                chunk_metadata=r.chunk_metadata,
                filename=r.filename,
            )
        c = index[cid]
        c.vector_rank = r.vector_rank
        c.vector_distance = r.vector_distance
        c.vector_similarity = r.vector_similarity
        c.rrf_score += 1.0 / (_RRF_K + r.vector_rank)
        if "vector" not in c.retrieval_methods:
            c.retrieval_methods.append("vector")

    merged = sorted(
        index.values(),
        key=lambda c: (
            -c.rrf_score,
            -(c.vector_similarity if c.vector_similarity is not None else -999.0),
            str(c.chunk_id),  # deterministic tie-breaker
        ),
    )
    return merged[:k]
