import axios, { AxiosError, AxiosRequestConfig } from 'axios';

import type { ApiError, Tokens } from './types';

export const ACCESS_TOKEN_KEY = 'quantx_token';
export const REFRESH_TOKEN_KEY = 'quantx_refresh_token';

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeTokens(tokens: Tokens): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Access tokens expire after 30 minutes. Without this the app simply bounced
// the user to /login every half hour, and the whole refresh-rotation flow on
// the backend was unreachable because the refresh token was never even stored.
//
// A single in-flight refresh is shared by every request that hits a 401 at the
// same time, so a burst of parallel calls performs one rotation rather than N
// competing ones (which would invalidate each other, since the backend rotates
// and revokes on every use).
let refreshInFlight: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error('No refresh token available');

  // Bare axios, not `api`: this request must not run the interceptors below.
  const response = await axios.post<Tokens>('/api/v1/auth/refresh', {
    refresh_token: refreshToken,
  });
  storeTokens(response.data);
  return response.data.access_token;
}

interface RetriableConfig extends AxiosRequestConfig {
  _retried?: boolean;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as RetriableConfig | undefined;
    const isAuthCall = original?.url?.includes('/auth/');

    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      try {
        refreshInFlight = refreshInFlight ?? refreshAccessToken();
        const token = await refreshInFlight;
        refreshInFlight = null;
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` };
        return api.request(original);
      } catch {
        refreshInFlight = null;
        clearTokens();
        if (window.location.pathname !== '/login') {
          window.location.assign('/login');
        }
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  },
);

/** Extract a human-readable message from an API failure. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError<ApiError>(error)) {
    if (error.response?.data?.message) return error.response.data.message;
    if (error.response?.status === 403) return 'You do not have access to this resource.';
    if (error.response?.status === 429) return 'Rate limit reached. Please wait and try again.';
    if (error.response?.status === 501) return 'This capability is not implemented.';
    if (error.code === 'ERR_NETWORK') return 'Cannot reach the API. Is the backend running?';
    return error.message || fallback;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

export default api;
