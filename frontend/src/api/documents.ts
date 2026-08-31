import { apiClient } from './client';
import type {
  DocumentListResponse,
  DocumentPermissionListResponse,
  DocumentPermissionResponse,
  DocumentResponse,
  DocumentUploadResponse,
} from '../types/document';
import type { UserRole } from '../types/auth';

export const documentsApi = {
  list: async (limit: number = 50, offset: number = 0): Promise<DocumentListResponse> => {
    return apiClient<DocumentListResponse>(`/documents?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    });
  },

  get: async (documentId: string): Promise<DocumentResponse> => {
    return apiClient<DocumentResponse>(`/documents/${documentId}`, {
      method: 'GET',
    });
  },

  upload: async (file: File, minRole: UserRole = 'employee'): Promise<DocumentUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('min_role', minRole);

    return apiClient<DocumentUploadResponse>('/documents/upload', {
      method: 'POST',
      body: formData,
    });
  },

  delete: async (documentId: string): Promise<void> => {
    return apiClient<void>(`/documents/${documentId}`, {
      method: 'DELETE',
    });
  },

  listPermissions: async (documentId: string): Promise<DocumentPermissionListResponse> => {
    return apiClient<DocumentPermissionListResponse>(`/documents/${documentId}/permissions`, {
      method: 'GET',
    });
  },

  grantPermission: async (
    documentId: string,
    userId: string,
    permission: string = 'read'
  ): Promise<DocumentPermissionResponse> => {
    return apiClient<DocumentPermissionResponse>(`/documents/${documentId}/permissions`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, permission }),
    });
  },

  revokePermission: async (documentId: string, userId: string): Promise<void> => {
    return apiClient<void>(`/documents/${documentId}/permissions/${userId}`, {
      method: 'DELETE',
    });
  },
};
