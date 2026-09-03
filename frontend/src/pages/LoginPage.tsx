import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { errorMessage } from '../lib/api';
import { useAuth } from '../contexts/useAuth';

const inputClass =
  'w-full bg-slate-800 text-white text-sm rounded-lg border border-slate-700 px-3 py-2.5 ' +
  'focus:border-cyan-500 focus:outline-none transition-colors disabled:opacity-50';

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
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 font-mono text-sm">
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
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-2xl shadow-2xl shadow-cyan-500/30 mx-auto mb-4">
            QX
          </div>
          <h1 className="text-2xl font-bold text-white">QuantX</h1>
          <p className="text-sm text-slate-400 mt-1">AI-Powered Trading Research Platform</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="p-6 rounded-2xl bg-slate-900/70 backdrop-blur-xl border border-slate-800 space-y-4"
        >
          {error && (
            <div className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="email" className="text-xs text-slate-400 block mb-1">Email</label>
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
                <label htmlFor="username" className="text-xs text-slate-400 block mb-1">Username</label>
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
                <label htmlFor="fullName" className="text-xs text-slate-400 block mb-1">
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
            <label htmlFor="password" className="text-xs text-slate-400 block mb-1">Password</label>
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
            className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-sm font-semibold rounded-lg transition-all shadow-lg shadow-cyan-600/20 disabled:opacity-50 disabled:cursor-not-allowed"
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
  );
}
