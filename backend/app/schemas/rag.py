from typing import List, Optional
from pydantic import BaseModel, Field

from backend.app.services.rag.citations import CitationItem
from backend.app.services.rag.grounding import GroundingStatus


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="User search query")
    top_k: int = Field(default=5, ge=1, le=10, description="Max context chunks to retrieve and consider")
    include_diagnostics: bool = Field(default=False, description="Whether to include cost and latency breakdown")


class RAGDiagnosticsResponse(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    retrieval_latency_ms: float
    generation_latency_ms: float
    total_latency_ms: float
    context_chunks_count: int
    valid_citations_count: int
    fabricated_citations_count: int


class RAGQueryResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
    grounding_status: GroundingStatus
    is_refusal: bool
    diagnostics: Optional[RAGDiagnosticsResponse] = None
