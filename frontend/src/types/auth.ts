export type UserRole = 'employee' | 'admin';

export interface UserResponse {
  id: string;
  email: string;
  role: UserRole;
  tenant_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
