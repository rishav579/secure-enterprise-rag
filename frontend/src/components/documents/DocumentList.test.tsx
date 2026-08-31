import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DocumentList } from './DocumentList';
import { AuthProvider } from '../../context/AuthContext';
import type { DocumentResponse } from '../../types/document';
import * as authApiModule from '../../api/auth';

describe('DocumentList Component - Role-Aware UX & Zero-Trust Boundary', () => {
  const sampleDoc: DocumentResponse = {
    id: 'doc-1234',
    tenant_id: 'tenant-a',
    owner_id: 'admin-owner-id',
    filename: 'corporate_security_policy.pdf',
    file_hash: 'abcdef123456',
    file_size_bytes: 2048576, // ~2 MB
    mime_type: 'application/pdf',
    min_role: 'admin',
    status: 'completed',
    doc_metadata: {},
    created_at: '2026-08-30T10:00:00Z',
    updated_at: '2026-08-30T10:00:00Z',
  };

  it('hides permission management buttons from non-owner employee', () => {
    // Non-owner employee viewing the list
    vi.spyOn(authApiModule.authApi, 'getCurrentUser').mockResolvedValueOnce({
      id: 'employee-viewer-id',
      email: 'employee@enterprise.com',
      role: 'employee',
      tenant_id: 'tenant-a',
      is_active: true,
      created_at: '2026-08-30T10:00:00Z',
      updated_at: '2026-08-30T10:00:00Z',
    });

    render(
      <AuthProvider>
        <DocumentList
          documents={[sampleDoc]}
          onRefresh={vi.fn()}
          isLoading={false}
        />
      </AuthProvider>
    );

    // Document is visible
    expect(screen.getByText('corporate_security_policy.pdf')).toBeInTheDocument();
    expect(screen.getByText('Admin Only')).toBeInTheDocument();

    // Permission and delete action buttons are NOT rendered for non-owner employee
    expect(screen.queryByRole('button', { name: /permissions/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });
});
