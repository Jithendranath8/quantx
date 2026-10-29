import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, Eye, EyeOff, Loader2 } from 'lucide-react';

import DecisionFlow from '../components/brand/DecisionFlow';
import { Logo, LogoMark } from '../components/brand/Logo';
import { GitHubIcon, GoogleIcon } from '../components/brand/ProviderIcons';
import { GridBackdrop, Spotlight } from '../components/fx/effects';
import api, { errorMessage } from '../lib/api';
import { startOAuth } from '../lib/oauth';
import { useAuth } from '../contexts/useAuth';

const inputClass =
  'w-full h-11 bg-ink-900 text-white text-sm rounded-xl ring-1 ring-inset ring-white/10 px-3.5 ' +
  'placeholder:text-zinc-600 hover:ring-white/20 focus:ring-2 focus:ring-brand-500/70 focus:outline-none transition disabled:opacity-50';

interface Provider {
  name: string;
  label: string;
}

// Shown even when a provider is not configured, so the option is discoverable
// and the reason it is unavailable is stated rather than hidden.
const KNOWN_PROVIDERS: { name: string; label: string; icon: typeof GoogleIcon }[] = [
  { name: 'google', label: 'Google', icon: GoogleIcon },
  { name: 'github', label: 'GitHub', icon: GitHubIcon },
];

function OAuthButtons({ disabled }: { disabled: boolean }) {
  const [enabled, setEnabled] = useState<Set<string> | null>(null);

  useEffect(() => {
    api
      .get<Provider[]>('/auth/oauth/providers')
      .then((r) => setEnabled(new Set(r.data.map((p) => p.name))))
      .catch(() => setEnabled(new Set()));
  }, []);

  return (
    <div>
      <div className="grid grid-cols-2 gap-3">
        {KNOWN_PROVIDERS.map(({ name, label, icon: Icon }) => {
          const available = enabled?.has(name) ?? false;
          const className =
            'flex h-11 items-center justify-center gap-2.5 rounded-xl text-sm font-medium ring-1 ring-inset transition ' +
            (available && !disabled
              ? 'bg-white text-zinc-900 ring-white hover:bg-zinc-200 cursor-pointer'
              : 'bg-white/[0.03] text-zinc-500 ring-white/[0.08] cursor-not-allowed');
          return available && !disabled ? (
            // A full-page navigation, not XHR: the provider's consent screen must
            // own the window for the OAuth 2.0 redirect flow.
            <button key={name} type="button" onClick={() => startOAuth(name)} className={className}>
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ) : (
            <span
              key={name}
              className={className}
              title={enabled === null ? 'Checking…' : `${label} sign-in is not configured on this server`}
              aria-disabled="true"
            >
              <Icon className="w-4 h-4 opacity-60" />
              {label}
            </span>
          );
        })}
      </div>
      {enabled?.size === 0 && (
        <p className="mt-2.5 text-xs text-zinc-600">
          Google and GitHub sign-in turn on once the server sets its OAUTH_* client credentials.
        </p>
      )}
    </div>
  );
}

/** Where to go after sign-in: the page that sent us here, but only ever inside the app. */
function returnPath(search: string): string {
  const next = new URLSearchParams(search).get('next');
  return next && next.startsWith('/app') && !next.startsWith('//') ? next : '/app';
}

export default function LoginPage() {
  const { login, register, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const oauthError = (location.state as { oauthError?: string } | null)?.oauthError;

  const [isRegister, setIsRegister] = useState(new URLSearchParams(location.search).get('mode') === 'register');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(oauthError ?? '');
  const [pending, setPending] = useState(false);

  if (isLoading) {
    return (
      <div className="min-h-screen grid place-items-center">
        <LogoMark className="w-10 h-10 animate-pulse" />
      </div>
    );
  }
  // An already-signed-in user landing here goes straight to the app.
  if (isAuthenticated) return <Navigate to={returnPath(location.search)} replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setPending(true);
    try {
      if (isRegister) {
        await register(email, username, password, fullName || undefined);
      } else {
        await login(email, password);
      }
      navigate(returnPath(location.search), { replace: true });
    } catch (err) {
      // The API returns {error, message, details}; reading `detail` (the
      // FastAPI default shape) always produced the generic fallback instead of
      // the real reason, such as which password rule failed.
      setError(errorMessage(err, 'Authentication failed'));
    } finally {
      setPending(false);
    }
  };

  const switchMode = (register: boolean) => {
    setIsRegister(register);
    setError('');
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] bg-ink-950">
      {/* Form column */}
      <div className="relative flex flex-col px-6 sm:px-12 py-8">
        <div className="flex items-center justify-between">
          <Logo />
          <Link to="/" className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-white transition cursor-pointer">
            <ArrowLeft className="w-3.5 h-3.5" /> Back to home
          </Link>
        </div>

        <div className="flex-1 flex items-center justify-center py-12">
          <div className="w-full max-w-sm animate-fade-in-up">
            <h1 className="font-display text-[2.6rem] leading-[1.05] text-white">
              {isRegister ? (
                <>Open your <em className="text-brand-400">research desk.</em></>
              ) : (
                <>Welcome <em className="text-brand-400">back.</em></>
              )}
            </h1>
            <p className="mt-3 text-sm text-zinc-400">
              {isRegister
                ? 'Free, paper-only by default. Nothing trades for real unless you explicitly turn it on.'
                : 'Sign in to pick up where your agents left off.'}
            </p>

            {/* Mode switch (DaisyUI tabs) */}
            <div role="tablist" className="d-tabs d-tabs-boxed mt-8 bg-ink-900 ring-1 ring-inset ring-white/[0.06] p-1 rounded-xl">
              <button
                type="button"
                role="tab"
                aria-selected={!isRegister}
                onClick={() => switchMode(false)}
                className={`d-tab h-9 rounded-lg text-sm cursor-pointer ${!isRegister ? 'd-tab-active !bg-white/[0.08] !text-white' : 'text-zinc-400'}`}
              >
                Sign in
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={isRegister}
                onClick={() => switchMode(true)}
                className={`d-tab h-9 rounded-lg text-sm cursor-pointer ${isRegister ? 'd-tab-active !bg-white/[0.08] !text-white' : 'text-zinc-400'}`}
              >
                Create account
              </button>
            </div>

            <div className="mt-6">
              <OAuthButtons disabled={pending} />
            </div>

            <div className="d-divider my-6 text-[11px] uppercase tracking-[0.16em] text-zinc-600 before:bg-white/[0.07] after:bg-white/[0.07]">
              or with email
            </div>

            <form onSubmit={handleSubmit} className="space-y-4" noValidate={false}>
              {error && (
                <div role="alert" className="px-4 py-3 rounded-xl bg-red-500/10 ring-1 ring-inset ring-red-500/20 text-red-300 text-sm">
                  {error}
                </div>
              )}

              <div>
                <label htmlFor="email" className="text-xs font-medium text-zinc-400 block mb-1.5">Email</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@desk.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={pending}
                  className={inputClass}
                />
              </div>

              {isRegister && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="username" className="text-xs font-medium text-zinc-400 block mb-1.5">Username</label>
                    <input
                      id="username"
                      type="text"
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      required
                      minLength={3}
                      disabled={pending}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor="fullName" className="text-xs font-medium text-zinc-400 block mb-1.5">
                      Full name <span className="text-zinc-600">(optional)</span>
                    </label>
                    <input
                      id="fullName"
                      type="text"
                      autoComplete="name"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      disabled={pending}
                      className={inputClass}
                    />
                  </div>
                </div>
              )}

              <div>
                <label htmlFor="password" className="text-xs font-medium text-zinc-400 block mb-1.5">Password</label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete={isRegister ? 'new-password' : 'current-password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    maxLength={72}
                    disabled={pending}
                    className={`${inputClass} pr-11`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 p-2 text-zinc-500 hover:text-white cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {isRegister && (
                  <p className="text-xs text-zinc-600 mt-1.5">
                    8–72 characters, with an uppercase letter, a lowercase letter, and a digit.
                  </p>
                )}
              </div>

              <button
                type="submit"
                disabled={pending}
                className="w-full h-11 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-400 text-ink-950 text-sm font-semibold transition shadow-[0_8px_30px_-10px_rgba(255,122,26,0.7)] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {pending && <Loader2 className="w-4 h-4 animate-spin" />}
                {pending ? 'Please wait…' : isRegister ? 'Create account' : 'Sign in'}
              </button>
            </form>

            <p className="mt-6 text-xs text-zinc-600 leading-relaxed">
              Sign-in with Google or GitHub uses OAuth 2.0 with PKCE. QuantX only receives your verified email and
              name — never your provider password.
            </p>
          </div>
        </div>
      </div>

      {/* Showcase column: what happens after you sign in. */}
      <div className="relative hidden lg:flex flex-col justify-center overflow-hidden border-l border-white/[0.06] bg-ink-900/40 px-16">
        <Spotlight className="-top-40 left-0" />
        <GridBackdrop />
        <div className="relative max-w-md">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-brand-400 mb-4">What you are signing in to</p>
          <h2 className="font-display text-4xl leading-tight text-white">
            The model proposes.
            <br />
            <em className="text-zinc-400">Math and explicit limits decide.</em>
          </h2>
          <div className="mt-10">
            <DecisionFlow />
          </div>
        </div>
      </div>
    </div>
  );
}
