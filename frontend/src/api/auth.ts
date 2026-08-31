import { apiClient, setAuthToken } from './client';
import type { TokenResponse, UserResponse } from '../types/auth';

export const authApi = {
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const data = await apiClient<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(data.access_token);
    return data;
  },

  register: async (email: string, password: string): Promise<UserResponse> => {
    return apiClient<UserResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  getCurrentUser: async (): Promise<UserResponse> => {
    return apiClient<UserResponse>('/auth/me', {
      method: 'GET',
    });
  },

  logout: () => {
    setAuthToken(null);
  },
};
