"""POST /api/v1/retrieval/search

Authorization:
  - Requires authenticated user (get_current_user).
  - tenant_id and role come exclusively from the authenticated User loaded from PostgreSQL.
  - Client request bodies cannot supply or override tenant_id or role.
  - Both SQL queries (lexical + vector) enforce DocumentAccessPolicy at the WHERE clause.
  - The reranker only receives already-authorized candidates.

Observability:
  Safe telemetry is included: request_id, user_id (UUID), tenant_id, candidate counts,
  method contributions, latency breakdown.
  NEVER logged: query text, document content, embeddings, credentials.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db, get_embedding_service
from backend.app.config import get_settings
from backend.app.models.user import User
from backend.app.schemas.retrieval import (
    RetrievalDiagnosticsResponse,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResultItem,
)
from backend.app.services.embedding import EmbeddingService
from backend.app.services.retrieval.pipeline import RetrievalPipeline
from backend.app.services.retrieval.reranker import FlashRankReranker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_reranker():
    """Dependency: instantiate the FlashRank reranker (with NullReranker fallback)."""
    return FlashRankReranker()


def get_retrieval_pipeline(
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    reranker=Depends(get_reranker),
) -> RetrievalPipeline:
    settings = get_settings()
    return RetrievalPipeline(
        embedding_service=embedding_service,
        reranker=reranker,
        embedding_dim=settings.EMBEDDING_DIMENSIONS,
    )


@router.post(
    "/search",
    response_model=RetrievalResponse,
    summary="Hybrid retrieval search (lexical + vector + RRF + reranking)",
)
async def retrieval_search(
    body: RetrievalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pipeline: RetrievalPipeline = Depends(get_retrieval_pipeline),
):
    """Hybrid retrieval endpoint.

    Security model:
    - tenant_id and role are sourced exclusively from the authenticated User.
    - SQL authorization predicates are applied before any candidate enters memory.
    - The reranker only scores already-authorized candidates.
    - Response never exposes: filesystem paths, raw chunk embeddings, internal DB IDs
      for unauthorized resources, or PII-bearing debug payloads.
    """
    request_id = str(uuid.uuid4())

    # Safe telemetry: log request metadata but NOT the query text
    logger.info(
        "retrieval.search user_id=%s tenant_id=%s top_k=%d request_id=%s",
        current_user.id,
        current_user.tenant_id,
        body.top_k,
        request_id,
    )

    try:
        results, diag = await pipeline.search(
            query=body.query,
            user=current_user,
            db=db,
            top_k=body.top_k,
            include_diagnostics=body.include_diagnostics,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "retrieval.search failed request_id=%s error=%s",
            request_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Retrieval service encountered an upstream failure.",
        ) from exc

    # Safe telemetry: log candidate counts but NOT content or scores in plaintext
    logger.info(
        "retrieval.search done request_id=%s results=%d "
        "lex_k=%s vec_k=%s overlap=%s total_ms=%s",
        request_id,
        len(results),
        diag.lexical_candidates if diag else "n/a",
        diag.vector_candidates if diag else "n/a",
        diag.overlapping_candidates if diag else "n/a",
        diag.total_latency_ms if diag else "n/a",
    )

    items = [
        RetrievalResultItem(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            filename=r.filename,
            page_number=r.page_number,
            char_start=r.char_start,
            char_end=r.char_end,
            content=r.content,
            retrieval_methods=r.retrieval_methods,
            rrf_score=r.rrf_score,
            lexical_rank=r.lexical_rank,
            lexical_score=r.lexical_score,
            vector_rank=r.vector_rank,
            vector_distance=r.vector_distance,
            vector_similarity=r.vector_similarity,
            reranker_score=r.reranker_score,
        )
        for r in results
    ]

    diag_resp = None
    if diag:
        diag_resp = RetrievalDiagnosticsResponse(**diag.__dict__)

    return RetrievalResponse(
        results=items,
        total_results=len(items),
        diagnostics=diag_resp,
    )
