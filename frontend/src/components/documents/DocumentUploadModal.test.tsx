import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DocumentUploadModal } from './DocumentUploadModal';

describe('DocumentUploadModal Component', () => {
  it('validates PDF extension on client side', async () => {
    const onClose = vi.fn();
    const onUploadSuccess = vi.fn();

    render(
      <DocumentUploadModal
        isOpen={true}
        onClose={onClose}
        onUploadSuccess={onUploadSuccess}
      />
    );

    const input = screen.getByLabelText(/upload a file/i) as HTMLInputElement;
    const invalidFile = new File(['hello'], 'document.txt', { type: 'text/plain' });

    fireEvent.change(input, { target: { files: [invalidFile] } });

    expect(screen.getByText(/only pdf documents \(\.pdf\) are accepted/i)).toBeInTheDocument();
  });

  it('rejects files larger than 10 MB on client side', async () => {
    const onClose = vi.fn();
    const onUploadSuccess = vi.fn();

    render(
      <DocumentUploadModal
        isOpen={true}
        onClose={onClose}
        onUploadSuccess={onUploadSuccess}
      />
    );

    const input = screen.getByLabelText(/upload a file/i) as HTMLInputElement;
    // 11 MB dummy file
    const largeFile = new File(['x'.repeat(11 * 1024 * 1024)], 'large.pdf', {
      type: 'application/pdf',
    });

    fireEvent.change(input, { target: { files: [largeFile] } });

    expect(screen.getByText(/file size exceeds the 10 mb limit/i)).toBeInTheDocument();
  });
});
