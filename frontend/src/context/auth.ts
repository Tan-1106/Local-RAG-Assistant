import { createContext, useContext } from 'react';
import type { ApiRequestInit } from '../utils/api';

export interface User {
  id: number;
  username: string;
  role: string;
}

export interface AuthContextType {
  user: User | null;
  login: (user: User, csrfToken: string) => void;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  apiFetch: (input: RequestInfo | URL, init?: ApiRequestInit) => Promise<Response>;
  isLoading: boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
