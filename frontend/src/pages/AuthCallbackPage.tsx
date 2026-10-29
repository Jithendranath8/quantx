import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import { LogoMark } from '../components/brand/Logo';
import { useAuth } from '../contexts/useAuth';
import api, { errorMessage } from '../lib/api';
import { LINK_MESSAGE_KEY, oauthErrorMessage, takeOAuthNonce } from '../lib/oauth';

/**
 * Landing point after an OAuth 2.0 provider sign-in or link.
 *
 * The API passes a one-time code (or an error code) in the URL fragment, which
 * never reaches any server log. The code is redeemed once, together with the
 * nonce this tab stored when it started the flow, and the fragment is wiped
 * from history straight away.
 */
export default function AuthCallbackPage() {
  const { completeOAuth } = useAuth();
  const navigate = useNavigate();
  const started = useRef(false);

  useEffect(() => {
    // StrictMode runs effects twice in development; a second redemption of a
    // single-use code would fail and bounce a successful sign-in to an error.
    if (started.current) return;
    started.current = true;

    const params = new URLSearchParams(window.location.hash.slice(1));
    window.history.replaceState(null, '', window.location.pathname);
    const nonce = takeOAuthNonce();
    const loginFailed = (message: string) => navigate('/login', { replace: true, state: { oauthError: message } });
    // A full reload of Settings re-reads the account, so a new link shows at once.
    const backToSettings = (query: string) => window.location.assign(`/app/settings?${query}`);

    const linkCode = params.get('link_code');
    const linkError = params.get('link_error');
    if (linkError) {
      backToSettings(`link_error=${encodeURIComponent(linkError)}`);
      return;
    }
    if (linkCode) {
      if (!nonce) {
        backToSettings('link_error=state_mismatch');
        return;
      }
      api
        .post('/auth/oauth/link/complete', { code: linkCode, client_nonce: nonce })
        .then(() => backToSettings('linked=1'))
        .catch((err) => {
          // The API's reason travels via sessionStorage, never the URL, so a
          // crafted link cannot put its own text on the Settings page.
          sessionStorage.setItem(LINK_MESSAGE_KEY, errorMessage(err, 'Linking failed'));
          backToSettings('link_error=failed');
        });
      return;
    }

    const code = params.get('code');
    if (!code) {
      loginFailed(oauthErrorMessage(params.get('error')));
      return;
    }
    // No nonce means this tab never started a sign-in: the link came from
    // somewhere else, and redeeming it could sign this browser in as someone else.
    if (!nonce) {
      loginFailed('This sign-in link was not started in this browser. Please sign in again.');
      return;
    }
    completeOAuth(code, nonce)
      .then(() => navigate('/app', { replace: true }))
      .catch((err) => loginFailed(errorMessage(err, 'Sign-in failed')));
  }, [completeOAuth, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 text-sm text-zinc-500">
      <LogoMark className="w-10 h-10 animate-pulse" />
      Completing sign-in…
    </div>
  );
}
