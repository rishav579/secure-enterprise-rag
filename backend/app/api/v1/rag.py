import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import (
    get_current_user,
    get_db,
    get_embedding_service,
    get_llm_service,
)
from backend.app.api.v1.retrieval import get_reranker
from backend.app.core.rate_limit import limiter
from backend.app.config import get_settings
from backend.app.models.user import User
from backend.app.schemas.rag import (
    RAGDiagnosticsResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from backend.app.services.embedding import EmbeddingService
from backend.app.services.llm import LLMError, LLMRateLimitError, LLMService, LLMTimeoutError
from backend.app.services.rag.pipeline import RAGPipeline
from backend.app.services.retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["rag"])


def get_rag_pipeline(
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    reranker=Depends(get_reranker),
    llm_service: LLMService = Depends(get_llm_service),
) -> RAGPipeline:
    settings = get_settings()
    retrieval_pipeline = RetrievalPipeline(
        embedding_service=embedding_service,
        reranker=reranker,
        embedding_dim=settings.EMBEDDING_DIMENSIONS,
    )
    return RAGPipeline(
        retrieval_pipeline=retrieval_pipeline,
        llm_service=llm_service,
        settings=settings,
    )


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="Execute grounded retrieval-augmented generation with verified citations",
)
@limiter.limit("20/minute")
async def rag_query(
    request: Request,
    body: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
):
    """Execute authenticated RAG query.

    Security & Observability Rules:
    - Authoritative tenant_id and role come exclusively from the authenticated User.
    - SQL authorization boundary from Phase 3 ensures no unauthorized document content is accessed.
    - Grounding validator ensures only supplied context chunks are cited.
    - Telemetry logs only request IDs, user IDs, token counts, and component latencies.
    - Raw user queries, raw document text, PII, and API keys are NEVER logged.
    """
    request_id = str(uuid.uuid4())

    # Safe telemetry: request metadata without query text
    logger.info(
        "rag.query.start request_id=%s user_id=%s tenant_id=%s top_k=%d",
        request_id,
        current_user.id,
        current_user.tenant_id,
        body.top_k,
    )

    try:
        res = await pipeline.execute_query(
            query=body.query,
            user=current_user,
            db=db,
            top_k=body.top_k,
        )
    except LLMTimeoutError as exc:
        logger.error("rag.query timeout request_id=%s", request_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The language model generation service timed out.",
        ) from exc
    except LLMRateLimitError as exc:
        logger.error("rag.query rate_limit request_id=%s", request_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for generation service. Please try again later.",
        ) from exc
    except (LLMError, Exception) as exc:
        logger.error("rag.query failed request_id=%s error=%s", request_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Generation service encountered an upstream failure.",
        ) from exc

    # Safe completion telemetry: token usage and latencies only
    logger.info(
        "rag.query.done request_id=%s status=%s is_refusal=%s prompt_tokens=%d "
        "completion_tokens=%d cost_usd=%.6f total_ms=%.1f",
        request_id,
        res.grounding_status.value,
        res.is_refusal,
        res.prompt_tokens,
        res.completion_tokens,
        res.estimated_cost_usd,
        res.total_latency_ms,
    )

    diag_resp = None
    if body.include_diagnostics:
        settings = get_settings()
        diag_resp = RAGDiagnosticsResponse(
            model=settings.LLM_MODEL,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            total_tokens=res.total_tokens,
            estimated_cost_usd=res.estimated_cost_usd,
            retrieval_latency_ms=res.retrieval_latency_ms,
            generation_latency_ms=res.generation_latency_ms,
            total_latency_ms=res.total_latency_ms,
            context_chunks_count=res.context_chunks_count,
            valid_citations_count=res.valid_citations_count,
            fabricated_citations_count=res.fabricated_citations_count,
        )

    return RAGQueryResponse(
        answer=res.answer,
        citations=res.citations,
        grounding_status=res.grounding_status,
        is_refusal=res.is_refusal,
        diagnostics=diag_resp,
    )
