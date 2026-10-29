import axios, { AxiosError, AxiosRequestConfig } from 'axios';

import type { ApiError, Tokens } from './types';

export const ACCESS_TOKEN_KEY = 'quantx_token';
export const REFRESH_TOKEN_KEY = 'quantx_refresh_token';

// Default to the same-origin nginx proxy path. For a split deploy (static
// frontend + separate API host), set VITE_API_BASE_URL at build time to the
// API's absolute base, e.g. https://quantx-api.onrender.com/api/v1.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
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
  const response = await axios.post<Tokens>(`${API_BASE_URL}/auth/refresh`, {
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
    // Only the credential endpoints are exempt. /auth/me must refresh like any
    // other call: it restores the session on load, and skipping it logged
    // everyone out on the first reload after the access token expired.
    const isAuthCall = /\/auth\/(login|register|refresh|logout|oauth)/.test(original?.url ?? '');

    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      try {
        refreshInFlight = refreshInFlight ?? refreshAccessToken();
        const token = await refreshInFlight;
        refreshInFlight = null;
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` };
        return api.request(original);
      } catch (refreshError) {
        refreshInFlight = null;
        // Only a refresh the server actually refused ends the session. A
        // network error or 5xx (say, the API restarting) keeps the tokens, so
        // the next request can refresh normally instead of forcing a sign-in.
        // Reject with the refresh failure itself: passing on the original 401
        // made callers (session restore) read a transient outage as sign-out.
        if (!isAuthRejection(refreshError)) return Promise.reject(refreshError);
        clearTokens();
        if (window.location.pathname !== '/login') {
          const next = encodeURIComponent(window.location.pathname + window.location.search);
          window.location.assign(`/login?next=${next}`);
        }
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  },
);

/** True when the server definitively refused the credentials, as opposed to being unreachable. */
export function isAuthRejection(error: unknown): boolean {
  const status = axios.isAxiosError(error) ? error.response?.status : undefined;
  return status === 400 || status === 401 || status === 403;
}

/** Extract a human-readable message from an API failure. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError<ApiError>(error)) {
    if (error.response?.data?.message) return error.response.data.message;
    if (error.response?.status === 403) return 'You do not have access to this resource.';
    if (error.response?.status === 429) return 'Rate limit reached. Please wait and try again.';
    if (error.response?.status === 501) return 'This capability is not implemented.';
    if (error.code === 'ERR_NETWORK') return 'Unable to reach the server. Please check your connection and try again.';
    return error.message || fallback;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

export default api;
