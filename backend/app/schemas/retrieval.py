import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    include_diagnostics: bool = False


class RetrievalResultItem(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    content: str
    retrieval_methods: List[str]
    # Score breakdown — not interchangeable; document their semantics clearly
    rrf_score: float
    """RRF ranking score. Max ≈ 0.0328 when chunk ranks #1 in both retrievers.
    Lower than cosine similarity in magnitude; only meaningful for relative ordering."""
    lexical_rank: Optional[int] = None
    lexical_score: Optional[float] = None
    """ts_rank_cd score: PostgreSQL cover-density FTS rank. Higher = more relevant.
    Not comparable to vector_similarity."""
    vector_rank: Optional[int] = None
    vector_distance: Optional[float] = None
    """pgvector cosine distance. Range [0, 2]; lower = more similar."""
    vector_similarity: Optional[float] = None
    """1.0 - vector_distance. Range [0, 1] for normalized embeddings; higher = more similar."""
    reranker_score: Optional[float] = None
    """FlashRank cross-encoder score. Higher = more relevant. None if reranker was unavailable."""


class RetrievalDiagnosticsResponse(BaseModel):
    lexical_candidates: int
    vector_candidates: int
    overlapping_candidates: int
    rrf_candidates: int
    reranked: bool
    total_latency_ms: float
    embed_latency_ms: float
    lexical_latency_ms: float
    vector_latency_ms: float
    rrf_latency_ms: float
    reranker_latency_ms: float


class RetrievalResponse(BaseModel):
    results: List[RetrievalResultItem]
    total_results: int
    diagnostics: Optional[RetrievalDiagnosticsResponse] = None
