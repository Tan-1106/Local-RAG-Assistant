import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { API_BASE_URL } from '../config';
import { fetchWithTimeout, type ApiRequestInit } from '../utils/api';
import { parseUser } from '../utils/validation';
import { AuthContext, type User } from './auth';

const SAFE_RETRY_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const csrfTokenRef = useRef<string | null>(null);
  const refreshPromiseRef = useRef<Promise<User | null> | null>(null);

  const clearSession = useCallback(() => {
    csrfTokenRef.current = null;
    setUser(null);
  }, []);

  const acceptSessionResponse = useCallback(async (response: Response): Promise<User | null> => {
    if (!response.ok) return null;
    const csrfToken = response.headers.get('X-CSRF-Token');
    if (!csrfToken) return null;
    const currentUser = parseUser(await response.json());
    csrfTokenRef.current = csrfToken;
    setUser(currentUser);
    return currentUser;
  }, []);

  const refreshSession = useCallback(async (): Promise<User | null> => {
    if (!refreshPromiseRef.current) {
      const refreshInsideLock = async () => {
        const currentSession = await fetchWithTimeout(`${API_BASE_URL}/auth/me`, {
          credentials: 'include',
        });
        const currentUser = await acceptSessionResponse(currentSession);
        if (currentUser) return currentUser;

        const response = await fetchWithTimeout(`${API_BASE_URL}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
        });
        const refreshedUser = await acceptSessionResponse(response);
        if (!refreshedUser) clearSession();
        return refreshedUser;
      };

      refreshPromiseRef.current = (
        navigator.locks
          ? navigator.locks.request('local-rag-assistant-auth-refresh', refreshInsideLock)
          : refreshInsideLock()
      ).catch(error => {
        console.error('Session refresh failed', error);
        clearSession();
        return null;
      }).finally(() => {
        refreshPromiseRef.current = null;
      });
    }
    return refreshPromiseRef.current;
  }, [acceptSessionResponse, clearSession]);

  const logout = useCallback(async () => {
    const response = await fetchWithTimeout(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: csrfTokenRef.current
        ? { 'X-CSRF-Token': csrfTokenRef.current }
        : undefined,
    });
    if (!response.ok) {
      throw new Error(`Logout failed with status ${response.status}`);
    }
    clearSession();
  }, [clearSession]);

  const logoutAll = useCallback(async () => {
    const response = await fetchWithTimeout(`${API_BASE_URL}/auth/logout-all`, {
      method: 'POST',
      credentials: 'include',
      headers: csrfTokenRef.current
        ? { 'X-CSRF-Token': csrfTokenRef.current }
        : undefined,
    });
    if (!response.ok) {
      throw new Error(`Logout all failed with status ${response.status}`);
    }
    clearSession();
  }, [clearSession]);

  useEffect(() => {
    const controller = new AbortController();

    const fetchMe = async () => {
      setIsLoading(true);
      try {
        const response = await fetchWithTimeout(`${API_BASE_URL}/auth/me`, {
          credentials: 'include',
          signal: controller.signal,
        });
        if (!await acceptSessionResponse(response)) {
          await refreshSession();
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error('Failed to fetch user', error);
          clearSession();
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    };

    void fetchMe();
    return () => controller.abort();
  }, [acceptSessionResponse, clearSession, refreshSession]);

  const login = useCallback((newUser: User, csrfToken: string) => {
    csrfTokenRef.current = csrfToken;
    setUser(newUser);
    setIsLoading(false);
  }, []);

  const apiFetch = useCallback(async (
    input: RequestInfo | URL,
    init: ApiRequestInit = {},
  ) => {
    const {
      retryOnAuth,
      timeoutMs,
      ...requestInit
    } = init;
    const headers = new Headers(requestInit.headers);
    const method = (requestInit.method ?? 'GET').toUpperCase();
    if (!SAFE_RETRY_METHODS.has(method) && csrfTokenRef.current) {
      headers.set('X-CSRF-Token', csrfTokenRef.current);
    }

    let response = await fetchWithTimeout(input, {
      ...requestInit,
      headers,
      credentials: 'include',
    }, timeoutMs);

    if (response.status !== 401) return response;

    const refreshedUser = await refreshSession();
    // Default to true to auto-retry all requests (including POST/PUT/DELETE) upon successful token refresh
    const mayRetry = retryOnAuth ?? true;
    if (!refreshedUser || !mayRetry) return response;

    const retryHeaders = new Headers(requestInit.headers);
    if (!SAFE_RETRY_METHODS.has(method) && csrfTokenRef.current) {
      retryHeaders.set('X-CSRF-Token', csrfTokenRef.current);
    }
    response = await fetchWithTimeout(input, {
      ...requestInit,
      headers: retryHeaders,
      credentials: 'include',
    }, timeoutMs);
    if (response.status === 401) clearSession();
    return response;
  }, [clearSession, refreshSession]);

  const contextValue = useMemo(
    () => ({ user, login, logout, logoutAll, apiFetch, isLoading }),
    [apiFetch, isLoading, login, logout, logoutAll, user],
  );

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}
