import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LoginForm } from './LoginForm';
import { AuthProvider } from '../../context/AuthContext';
import * as authApiModule from '../../api/auth';

// Mock authApi
vi.mock('../../api/auth', () => ({
  authApi: {
    login: vi.fn(),
    getCurrentUser: vi.fn(),
    logout: vi.fn(),
  },
}));

describe('LoginForm Component', () => {
  it('renders email and password inputs', () => {
    render(
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    );

    expect(screen.getByLabelText(/work email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('submits credentials and calls onSuccess on success', async () => {
    const onSuccess = vi.fn();
    (authApiModule.authApi.login as any).mockResolvedValueOnce({
      access_token: 'mock-jwt-token',
      token_type: 'bearer',
    });
    (authApiModule.authApi.getCurrentUser as any).mockResolvedValueOnce({
      id: 'mock-user-id',
      email: 'test@example.com',
      role: 'employee',
      tenant_id: 'default',
    });

    render(
      <AuthProvider>
        <LoginForm onSuccess={onSuccess} />
      </AuthProvider>
    );

    fireEvent.change(screen.getByLabelText(/work email/i), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'Password123!' },
    });

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(authApiModule.authApi.login).toHaveBeenCalledWith('test@example.com', 'Password123!');
      expect(onSuccess).toHaveBeenCalled();
    });
  });
});
