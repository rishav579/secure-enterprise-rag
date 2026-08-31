"""Hybrid retrieval pipeline orchestrator.

Stages (all authorized at the SQL boundary before any in-memory processing):
  1. Embed query      → 768-d vector (same model/dimension as stored chunks)
  2. Lexical search   → Top-k authorized chunks via ts_rank_cd
  3. Vector search    → Top-k authorized chunks via pgvector cosine distance
  4. RRF fusion       → Unified ranked list
  5. Reranking        → FlashRank cross-encoder (with NullReranker fallback)

Query normalization:
  NFKC Unicode normalization and strip of leading/trailing whitespace only.
  Punctuation is NOT aggressively removed so that PostgreSQL websearch_to_tsquery
  semantics (quoted phrases, -negation) are preserved.
"""

import time
import asyncio
import unicodedata
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.user import User
from backend.app.services.embedding.base import EmbeddingService
from backend.app.services.retrieval.fusion import FusedCandidate, fuse_rrf
from backend.app.services.retrieval.lexical import run_lexical_search
from backend.app.services.retrieval.reranker import RerankerService
from backend.app.services.retrieval.vector import run_vector_search


# Query constraints — these bound external API costs and SQL complexity
QUERY_MIN_LEN = 2
QUERY_MAX_LEN = 1000

# Candidate pool sizes fed into RRF
LEXICAL_K = 20
VECTOR_K = 20
# Maximum candidates entering the reranker
RERANKER_INPUT_CAP = 20


@dataclass
class RetrievalResult:
    """Citation-ready retrieval result with full score breakdown."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: Optional[int]
    char_start: Optional[int]
    char_end: Optional[int]
    content: str
    retrieval_methods: List[str]
    rrf_score: float
    lexical_rank: Optional[int]
    lexical_score: Optional[float]
    vector_rank: Optional[int]
    vector_distance: Optional[float]
    vector_similarity: Optional[float]
    reranker_score: Optional[float]


@dataclass
class RetrievalDiagnostics:
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


def _normalize_query(query: str) -> str:
    """NFKC Unicode normalization + strip.

    Punctuation and operators are preserved so websearch_to_tsquery semantics work.
    """
    return unicodedata.normalize("NFKC", query).strip()


def _validate_query(query: str) -> None:
    stripped = query.strip()
    if len(stripped) < QUERY_MIN_LEN:
        raise ValueError(
            f"Query must contain at least {QUERY_MIN_LEN} non-whitespace characters."
        )
    if len(query) > QUERY_MAX_LEN:
        raise ValueError(
            f"Query must not exceed {QUERY_MAX_LEN} characters."
        )


def _candidate_to_result(c: FusedCandidate) -> RetrievalResult:
    meta = c.chunk_metadata or {}
    return RetrievalResult(
        chunk_id=c.chunk_id,
        document_id=c.document_id,
        filename=c.filename,
        page_number=meta.get("page_number"),
        char_start=meta.get("char_start"),
        char_end=meta.get("char_end"),
        content=c.content,
        retrieval_methods=list(c.retrieval_methods),
        rrf_score=c.rrf_score,
        lexical_rank=c.lexical_rank,
        lexical_score=c.lexical_score,
        vector_rank=c.vector_rank,
        vector_distance=c.vector_distance,
        vector_similarity=c.vector_similarity,
        reranker_score=c.reranker_score,
    )


class RetrievalPipeline:
    """End-to-end retrieval pipeline: lexical + vector → RRF → rerank."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        reranker: RerankerService,
        embedding_dim: int = 768,
        lexical_k: int = LEXICAL_K,
        vector_k: int = VECTOR_K,
        reranker_input_cap: int = RERANKER_INPUT_CAP,
    ) -> None:
        self._embed = embedding_service
        self._reranker = reranker
        self._embedding_dim = embedding_dim
        self._lexical_k = lexical_k
        self._vector_k = vector_k
        self._reranker_cap = reranker_input_cap

    async def search(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        top_k: int = 5,
        include_diagnostics: bool = False,
    ) -> tuple[List[RetrievalResult], Optional[RetrievalDiagnostics]]:
        """Run the full retrieval pipeline.

        Security invariants:
          - user.tenant_id and user.role come from the authenticated User object only.
          - Both SQL queries enforce DocumentAccessPolicy at the WHERE clause.
          - Reranker receives only candidates that already cleared authorization.
        """
        t_total_start = time.perf_counter()

        # 1. Query validation and normalization
        _validate_query(query)
        normalized = _normalize_query(query)

        # 2. Embed query (external API call, no DB transaction held open)
        t_embed_start = time.perf_counter()
        query_vec = await self._embed.embed_query(normalized)
        embed_ms = (time.perf_counter() - t_embed_start) * 1000

        if len(query_vec) != self._embedding_dim:
            raise ValueError(
                f"Query embedding dimension {len(query_vec)} != expected {self._embedding_dim}"
            )

        # 3. Lexical search (SQL with auth filter)
        t_lex_start = time.perf_counter()
        lex_results = await run_lexical_search(normalized, user, db, k=self._lexical_k)
        lex_ms = (time.perf_counter() - t_lex_start) * 1000

        # 4. Vector search (SQL with auth filter)
        t_vec_start = time.perf_counter()
        vec_results = await run_vector_search(
            query_vec, user, db, k=self._vector_k, embedding_dim=self._embedding_dim
        )
        vec_ms = (time.perf_counter() - t_vec_start) * 1000

        # 5. RRF
        t_rrf_start = time.perf_counter()
        lex_ids = {r.chunk_id for r in lex_results}
        vec_ids = {r.chunk_id for r in vec_results}
        overlap_count = len(lex_ids & vec_ids)
        fused = fuse_rrf(lex_results, vec_results, k=self._reranker_cap)
        rrf_ms = (time.perf_counter() - t_rrf_start) * 1000

        # 6. Rerank (Offloaded to a thread to prevent event loop blocking)
        t_rr_start = time.perf_counter()
        if self._reranker:
            reranked = await asyncio.to_thread(self._reranker.rerank, normalized, fused, top_k)
        else:
            reranked = fused[:top_k]
        rr_ms = (time.perf_counter() - t_rr_start) * 1000
        was_reranked = any(c.reranker_score is not None for c in reranked)

        total_ms = (time.perf_counter() - t_total_start) * 1000

        results = [_candidate_to_result(c) for c in reranked]

        diag: Optional[RetrievalDiagnostics] = None
        if include_diagnostics:
            diag = RetrievalDiagnostics(
                lexical_candidates=len(lex_results),
                vector_candidates=len(vec_results),
                overlapping_candidates=overlap_count,
                rrf_candidates=len(fused),
                reranked=was_reranked,
                total_latency_ms=round(total_ms, 2),
                embed_latency_ms=round(embed_ms, 2),
                lexical_latency_ms=round(lex_ms, 2),
                vector_latency_ms=round(vec_ms, 2),
                rrf_latency_ms=round(rrf_ms, 2),
                reranker_latency_ms=round(rr_ms, 2),
            )

        return results, diag
