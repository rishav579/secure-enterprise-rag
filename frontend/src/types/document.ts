import type { UserRole } from './auth';

export interface DocumentResponse {
  id: string;
  tenant_id: string;
  owner_id: string;
  filename: string;
  file_hash: string;
  file_size_bytes: number;
  mime_type: string;
  min_role: UserRole;
  status: string;
  error_message?: string | null;
  doc_metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse extends DocumentResponse {
  total_pages: number;
  total_chunks: number;
}

export interface DocumentListResponse {
  items: DocumentResponse[];
  total: number;
}

export interface DocumentPermissionResponse {
  id: string;
  document_id: string;
  user_id: string;
  tenant_id: string;
  permission: string;
  created_at: string;
}

export interface DocumentPermissionListResponse {
  items: DocumentPermissionResponse[];
  total: number;
}
