export interface CitationItem {
  citation_id: string;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  snippet: string;
}

export type GroundingStatus =
  | 'PROVENANCE_VERIFIED'
  | 'PARTIALLY_GROUNDED'
  | 'REFUSAL'
  | 'UNSUPPORTED_OR_FABRICATED';

export interface RAGDiagnosticsResponse {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
  total_latency_ms: number;
  context_chunks_count: number;
  valid_citations_count: number;
  fabricated_citations_count: number;
}

export interface RAGQueryResponse {
  answer: string;
  citations: CitationItem[];
  grounding_status: GroundingStatus;
  is_refusal: boolean;
  diagnostics?: RAGDiagnosticsResponse | null;
}
