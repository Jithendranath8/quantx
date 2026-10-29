import api, { API_BASE_URL } from './api';

// Binds an OAuth sign-in to the browser tab that started it. The API ties the
// sign-in state and the one-time login code to this value, so a callback link
// someone else produced cannot sign this browser into their account.
const NONCE_KEY = 'quantx_oauth_nonce';
/** Where a failed link's server-side reason waits for the Settings page. */
export const LINK_MESSAGE_KEY = 'quantx_oauth_link_message';

function randomNonce(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Start a provider sign-in: remember a fresh nonce, then hand the window to the API. */
export function startOAuth(provider: string): void {
  const nonce = randomNonce();
  sessionStorage.setItem(NONCE_KEY, nonce);
  window.location.assign(`${API_BASE_URL}/auth/oauth/${provider}/authorize?client_nonce=${nonce}`);
}

/** Start linking a provider to the signed-in account (needs the bearer token, so XHR first). */
export async function startLink(provider: string): Promise<void> {
  const nonce = randomNonce();
  sessionStorage.setItem(NONCE_KEY, nonce);
  const res = await api.post<{ authorize_url: string }>(`/auth/oauth/${provider}/link`, { client_nonce: nonce });
  window.location.assign(res.data.authorize_url);
}

// The API redirects with a code, never free text, so a crafted callback link
// can only ever produce one of these messages.
const ERROR_MESSAGES: Record<string, string> = {
  cancelled: 'Sign-in was cancelled.',
  incomplete: 'The provider did not complete sign-in. Please try again.',
  state_expired: 'That sign-in link expired or was already used. Please try again.',
  state_mismatch: 'That sign-in link does not match the provider. Please try again.',
  provider_rejected: 'The provider rejected the sign-in. Please try again.',
  no_verified_email: 'Your provider account has no verified email address.',
  profile_unreadable: 'Your provider profile could not be read. Please try again.',
  password_account_exists:
    'An account with this email already uses a password. Sign in with it, then link the provider in Settings.',
  account_disabled: 'This account is deactivated.',
  email_mismatch: 'That provider account’s email is not this account’s email.',
  provider_unavailable: 'That sign-in provider is not available.',
};

export function oauthErrorMessage(code: string | null): string {
  return (code && ERROR_MESSAGES[code]) || 'Sign-in did not complete. Please try again.';
}

/** The nonce for the sign-in this tab started, removed so it is used once. */
export function takeOAuthNonce(): string | null {
  const nonce = sessionStorage.getItem(NONCE_KEY);
  sessionStorage.removeItem(NONCE_KEY);
  return nonce;
}
