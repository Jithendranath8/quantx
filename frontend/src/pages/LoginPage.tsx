import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Bot, LineChart, ShieldCheck, Sparkles } from 'lucide-react';

import { errorMessage } from '../lib/api';
import { useAuth } from '../contexts/useAuth';

const inputClass =
  'w-full bg-slate-950/60 text-white text-sm rounded-lg ring-1 ring-inset ring-white/10 px-3 py-2.5 ' +
  'placeholder:text-slate-600 focus:ring-2 focus:ring-cyan-500/60 focus:outline-none transition-shadow disabled:opacity-50';

const features = [
  { icon: Bot, title: 'Multi-agent AI', body: 'Specialist agents reason over your data under a LangGraph supervisor.' },
  { icon: ShieldCheck, title: 'Deterministic risk', body: 'Every decision is re-checked by a non-overridable risk engine.' },
  { icon: LineChart, title: 'Research suite', body: 'Backtesting, walk-forward, Monte Carlo and parameter search.' },
];

export default function LoginPage() {
  const { login, register, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400 font-mono text-sm">
        Loading QuantX Engine…
      </div>
    );
  }
  // An already-signed-in user landing here goes straight to the dashboard.
  if (isAuthenticated) return <Navigate to="/" replace />;

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
      navigate('/', { replace: true });
    } catch (err) {
      // The API returns {error, message, details}; reading `detail` (the
      // FastAPI default shape) always produced the generic fallback instead of
      // the real reason, such as which password rule failed.
      setError(errorMessage(err, 'Authentication failed'));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Brand / feature showcase */}
      <div className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r hairline p-12">
        <div className="pointer-events-none absolute -top-24 -left-24 w-96 h-96 rounded-full bg-cyan-500/20 blur-3xl animate-float" />
        <div className="pointer-events-none absolute bottom-0 right-0 w-96 h-96 rounded-full bg-blue-600/20 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-brand-gradient grid place-items-center font-bold text-white text-xl shadow-glow-sm">
            QX
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none text-white">QuantX</h1>
            <p className="text-[10px] text-slate-500 font-mono mt-1 tracking-wider">TRADING PLATFORM</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <div className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 mb-5 text-xs font-medium text-cyan-300 ring-1 ring-inset ring-cyan-400/20 bg-cyan-500/10">
            <Sparkles className="w-3.5 h-3.5" /> Agentic AI quant platform
          </div>
          <h2 className="text-3xl font-bold leading-tight gradient-text">
            Research, backtest and trade — with AI you can actually trust.
          </h2>
          <p className="mt-4 text-sm text-slate-400 leading-relaxed">
            The model proposes; deterministic math and explicit risk limits decide. Paper and
            Binance SPOT execution behind a persisted risk engine.
          </p>

          <div className="mt-8 space-y-4">
            {features.map(({ icon: Icon, title, body }) => (
              <div key={title} className="flex items-start gap-3">
                <span className="grid place-items-center w-9 h-9 rounded-lg bg-cyan-500/10 text-cyan-400 ring-1 ring-inset ring-cyan-500/20 shrink-0">
                  <Icon className="w-4 h-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-white">{title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-xs text-slate-600">Testnet by default — a two-flag interlock guards real orders.</p>
      </div>

      {/* Auth form */}
      <div className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md animate-fade-in-up">
          <div className="text-center mb-8 lg:hidden">
            <div className="w-14 h-14 rounded-2xl bg-brand-gradient grid place-items-center font-bold text-white text-2xl shadow-glow-sm mx-auto mb-4">
              QX
            </div>
            <h1 className="text-2xl font-bold text-white">QuantX</h1>
          </div>

          <div className="mb-6">
            <h2 className="text-xl font-bold text-white">{isRegister ? 'Create your account' : 'Welcome back'}</h2>
            <p className="text-sm text-slate-400 mt-1">
              {isRegister ? 'Start researching in minutes.' : 'Sign in to your trading workspace.'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="glass rounded-2xl p-6 space-y-4">
            {error && (
              <div className="px-4 py-2.5 rounded-lg bg-red-500/10 ring-1 ring-inset ring-red-500/20 text-red-300 text-sm">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="text-xs font-medium text-slate-400 block mb-1.5">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={pending}
                className={inputClass}
              />
            </div>

            {isRegister && (
              <>
                <div>
                  <label htmlFor="username" className="text-xs font-medium text-slate-400 block mb-1.5">Username</label>
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
                  <label htmlFor="fullName" className="text-xs font-medium text-slate-400 block mb-1.5">
                    Full name <span className="text-slate-600">(optional)</span>
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
              </>
            )}

            <div>
              <label htmlFor="password" className="text-xs font-medium text-slate-400 block mb-1.5">Password</label>
              <input
                id="password"
                type="password"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                maxLength={72}
                disabled={pending}
                className={inputClass}
              />
              {isRegister && (
                <p className="text-xs text-slate-600 mt-1.5">
                  8–72 characters, with an uppercase letter, a lowercase letter, and a digit.
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={pending}
              className="w-full py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-sm font-semibold rounded-lg transition-all shadow-lg shadow-cyan-600/20 hover:shadow-glow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {pending ? 'Please wait…' : isRegister ? 'Create Account' : 'Sign In'}
            </button>

            <p className="text-center text-xs text-slate-500">
              {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
              <button
                type="button"
                onClick={() => { setIsRegister(!isRegister); setError(''); }}
                className="text-cyan-400 hover:text-cyan-300 font-medium"
              >
                {isRegister ? 'Sign In' : 'Register'}
              </button>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
