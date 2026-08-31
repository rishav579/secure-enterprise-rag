import { apiClient } from './client';
import type { RAGQueryResponse } from '../types/rag';

export const ragApi = {
  query: async (
    query: string,
    topK: number = 5,
    includeDiagnostics: boolean = false
  ): Promise<RAGQueryResponse> => {
    return apiClient<RAGQueryResponse>('/rag/query', {
      method: 'POST',
      body: JSON.stringify({
        query,
        top_k: topK,
        include_diagnostics: includeDiagnostics,
      }),
    });
  },
};
