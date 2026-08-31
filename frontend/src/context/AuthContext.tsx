import React, { createContext, useContext, useEffect, useState } from 'react';
import type { UserResponse } from '../types/auth';
import { authApi } from '../api/auth';
import { getAuthToken } from '../api/client';

interface AuthContextType {
  user: UserResponse | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(getAuthToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Load user identity on startup if token is present
  useEffect(() => {
    const initAuth = async () => {
      const existingToken = getAuthToken();
      if (existingToken) {
        try {
          const profile = await authApi.getCurrentUser();
          setUser(profile);
          setToken(existingToken);
        } catch {
          // Token expired or invalid
          authApi.logout();
          setUser(null);
          setToken(null);
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = async (email: string, password: string) => {
    const tokenRes = await authApi.login(email, password);
    setToken(tokenRes.access_token);
    const profile = await authApi.getCurrentUser();
    setUser(profile);
  };

  const register = async (email: string, password: string) => {
    await authApi.register(email, password);
    // Automatically log in after registration
    await login(email, password);
  };

  const logout = () => {
    authApi.logout();
    setUser(null);
    setToken(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
