import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CitationDrawer } from './CitationDrawer';
import type { CitationItem } from '../../types/rag';

describe('CitationDrawer Component', () => {
  const sampleCitation: CitationItem = {
    citation_id: '[DOC-1]',
    chunk_id: '11111111-2222-3333-4444-555555555555',
    document_id: '99999999-8888-7777-6666-555555555555',
    filename: 'employee_handbook.pdf',
    page_number: 4,
    char_start: 120,
    char_end: 250,
    snippet: 'Employees are entitled to 20 days of paid vacation annually.',
  };

  it('renders verified citation details and snippet', () => {
    const onClose = vi.fn();

    render(
      <CitationDrawer
        isOpen={true}
        onClose={onClose}
        citation={sampleCitation}
      />
    );

    expect(screen.getByText('[DOC-1]')).toBeInTheDocument();
    expect(screen.getByText('employee_handbook.pdf')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText(/employees are entitled to 20 days/i)).toBeInTheDocument();
    expect(screen.getByText(/char span: 120–250/i)).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();

    render(
      <CitationDrawer
        isOpen={true}
        onClose={onClose}
        citation={sampleCitation}
      />
    );

    const closeBtn = screen.getByRole('button');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });
});
