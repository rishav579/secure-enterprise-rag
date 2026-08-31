import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatInterface } from './ChatInterface';
import * as ragApiModule from '../../api/rag';
import type { RAGQueryResponse } from '../../types/rag';

vi.mock('../../api/rag', () => ({
  ragApi: {
    query: vi.fn(),
  },
}));

describe('ChatInterface Component', () => {
  it('submits search query and displays refusal state gracefully', async () => {
    const refusalResponse: RAGQueryResponse = {
      answer: 'I do not have enough information in the provided documents to answer this question.',
      citations: [],
      grounding_status: 'REFUSAL',
      is_refusal: true,
      diagnostics: null,
    };

    (ragApiModule.ragApi.query as any).mockResolvedValueOnce(refusalResponse);

    render(<ChatInterface />);

    const input = screen.getByPlaceholderText(/ask a question/i);
    const submitBtn = screen.getByRole('button', { name: /ask/i });

    fireEvent.change(input, { target: { value: 'What is the secret acquisition plan?' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(ragApiModule.ragApi.query).toHaveBeenCalledWith(
        'What is the secret acquisition plan?',
        5,
        true
      );
      expect(screen.getByText(/i do not have enough information in the provided documents/i)).toBeInTheDocument();
    });
  });

  it('renders verified citations when returned by the backend', async () => {
    const groundedResponse: RAGQueryResponse = {
      answer: 'Enterprise MFA is strictly mandatory for all employees [DOC-1].',
      citations: [
        {
          citation_id: '[DOC-1]',
          chunk_id: 'c1',
          document_id: 'd1',
          filename: 'security_handbook.pdf',
          page_number: 2,
          snippet: 'Enterprise MFA is strictly mandatory.',
        },
      ],
      grounding_status: 'PROVENANCE_VERIFIED',
      is_refusal: false,
      diagnostics: null,
    };

    (ragApiModule.ragApi.query as any).mockResolvedValueOnce(groundedResponse);

    render(<ChatInterface />);

    const input = screen.getByPlaceholderText(/ask a question/i);
    const submitBtn = screen.getByRole('button', { name: /ask/i });

    fireEvent.change(input, { target: { value: 'Is MFA mandatory?' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Enterprise MFA is strictly mandatory/i)).toBeInTheDocument();
      // Verified citation badge rendered in text and cited sources footer
      const citationButtons = screen.getAllByRole('button', { name: /\[DOC-1\]/i });
      expect(citationButtons.length).toBeGreaterThan(0);
    });
  });
});
