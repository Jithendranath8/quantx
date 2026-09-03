import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import api, { clearTokens, errorMessage, getAccessToken, getRefreshToken, storeTokens } from '../lib/api';
import type { AuthResponse, User } from '../lib/types';
import { AuthContext } from './auth-context';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore the session on mount. The access token may already have expired,
  // in which case the api client's interceptor rotates it using the stored
  // refresh token rather than dumping the user back at the login screen.
  useEffect(() => {
    if (!getAccessToken()) {
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    api
      .get<User>('/auth/me')
      .then((res) => {
        if (!cancelled) setUser(res.data);
      })
      .catch(() => {
        if (!cancelled) {
          clearTokens();
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<AuthResponse>('/auth/login', { email, password });
    storeTokens(res.data.tokens);
    setUser(res.data.user);
  }, []);

  const register = useCallback(
    async (email: string, username: string, password: string, fullName?: string) => {
      const res = await api.post<AuthResponse>('/auth/register', {
        email,
        username,
        password,
        full_name: fullName || null,
      });
      storeTokens(res.data.tokens);
      setUser(res.data.user);
    },
    [],
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    // Revoke server-side so the refresh token cannot be replayed. A failure
    // here must still clear local state, or the user appears stuck logged in.
    if (refreshToken) {
      try {
        await api.post('/auth/logout', { refresh_token: refreshToken });
      } catch (error) {
        console.warn('Logout revocation failed:', errorMessage(error));
      }
    }
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, login, register, logout, isAuthenticated: user !== null, isLoading }),
    [user, login, register, logout, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
