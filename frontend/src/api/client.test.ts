import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from './client';

describe('apiClient structured error extraction', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('extracts nested message from structured detail object (e.g. 409 Conflict)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: {
          message: 'A document with identical content already exists in this tenant.',
          existing_document_id: 'doc-1234',
        },
      }),
    } as any);

    await expect(apiClient('/test')).rejects.toThrow(
      'A document with identical content already exists in this tenant.'
    );
  });

  it('extracts string detail message (e.g. 400 Bad Request)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: 'PDF contains no extractable text.',
      }),
    } as any);

    await expect(apiClient('/test')).rejects.toThrow(
      'PDF contains no extractable text.'
    );
  });

  it('extracts validation error messages from array detail (e.g. 422 Unprocessable Entity)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: [{ msg: 'Value is not a valid email' }],
      }),
    } as any);

    await expect(apiClient('/test')).rejects.toThrow(
      'Value is not a valid email'
    );
  });

  it('falls back to normalized status message if no specific detail is provided', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({}),
    } as any);

    await expect(apiClient('/test')).rejects.toThrow(
      'A conflict occurred with an existing resource.'
    );
  });
});
