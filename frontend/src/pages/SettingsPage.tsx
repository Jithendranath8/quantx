import React, { useEffect, useState } from 'react';
import { CheckCircle2, KeyRound, Link2, LogOut, Settings, ShieldCheck } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import api, { errorMessage } from '../lib/api';
import { LINK_MESSAGE_KEY, oauthErrorMessage, startLink } from '../lib/oauth';
import { useAction, useApi } from '../lib/useApi';
import { useAuth } from '../contexts/useAuth';
import { Badge, Button, Card, PageHeader } from '../components/ui';

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
      <span className="text-sm text-zinc-400">{label}</span>
      <span className="text-sm text-white font-mono">{value}</span>
    </div>
  );
}

const PROVIDER_LABEL: Record<string, string> = { google: 'Google', github: 'GitHub' };

/** Password users can add provider sign-in; the provider must verify this account's email. */
function SignInMethods({ oauthProvider }: { oauthProvider: string | null | undefined }) {
  const providers = useApi<{ name: string; label: string }[]>(() =>
    api.get<{ name: string; label: string }[]>('/auth/oauth/providers').then((r) => r.data),
  );
  const [params, setParams] = useSearchParams();
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (params.get('linked')) {
      setNotice({ ok: true, text: 'Provider linked. You can now sign in with it.' });
    } else if (params.get('link_error')) {
      const stored = sessionStorage.getItem(LINK_MESSAGE_KEY);
      sessionStorage.removeItem(LINK_MESSAGE_KEY);
      setNotice({ ok: false, text: stored ?? oauthErrorMessage(params.get('link_error')) });
    } else {
      return;
    }
    setParams({}, { replace: true });
  }, [params, setParams]);

  const link = async (name: string) => {
    setBusy(name);
    try {
      await startLink(name);
    } catch (err) {
      setNotice({ ok: false, text: errorMessage(err, 'Could not start linking') });
      setBusy(null);
    }
  };

  return (
    <Card title="Sign-in methods" icon={<Link2 className="w-4 h-4 text-brand-400" />}>
      <div className="p-5 space-y-4">
        {notice && (
          <div
            role="status"
            className={`rounded-lg px-3 py-2 text-sm ring-1 ring-inset ${
              notice.ok ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/20' : 'bg-red-500/10 text-red-300 ring-red-500/20'
            }`}
          >
            {notice.text}
          </div>
        )}
        <Row label="Email & password" value={<Badge tone="neutral">available</Badge>} />
        {oauthProvider ? (
          <Row
            label={PROVIDER_LABEL[oauthProvider] ?? oauthProvider}
            value={
              <span className="inline-flex items-center gap-1.5 text-emerald-300">
                <CheckCircle2 className="w-3.5 h-3.5" /> linked
              </span>
            }
          />
        ) : providers.data && providers.data.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs text-zinc-500">
              Link a provider to sign in with it. It must verify the same email as this account.
            </p>
            <div className="flex flex-wrap gap-2">
              {providers.data.map((p) => (
                <Button key={p.name} variant="secondary" onClick={() => void link(p.name)} disabled={busy !== null}>
                  {busy === p.name ? 'Redirecting…' : `Link ${p.label}`}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-500">No sign-in providers are configured on this server.</p>
        )}
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();

  const logoutAll = useAction(async () => {
    await api.post('/auth/logout-all');
    await logout();
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Your account and platform configuration" />

      <div className="max-w-3xl space-y-6">
        <Card title="Account" icon={<Settings className="w-4 h-4 text-brand-400" />}>
          <div className="p-5">
            <Row label="Email" value={user?.email ?? '—'} />
            <Row label="Username" value={user?.username ?? '—'} />
            <Row label="Full name" value={user?.full_name || '—'} />
            <Row
              label="Status"
              value={<Badge tone={user?.is_active ? 'positive' : 'negative'}>{user?.is_active ? 'Active' : 'Inactive'}</Badge>}
            />
            <Row label="User ID" value={<span className="text-xs">{user?.id ?? '—'}</span>} />
          </div>
        </Card>

        <SignInMethods oauthProvider={user?.oauth_provider} />

        <Card title="Sessions" icon={<LogOut className="w-4 h-4 text-brand-400" />}>
          <div className="p-5 space-y-3">
            <p className="text-sm text-zinc-400">
              Signing out everywhere revokes every refresh token issued to your account, ending all
              active sessions on all devices.
            </p>
            <Button variant="danger" onClick={() => void logoutAll.run()} disabled={logoutAll.pending}>
              {logoutAll.pending ? 'Revoking…' : 'Sign out of all devices'}
            </Button>
            {logoutAll.error && <div className="text-xs text-red-400">{logoutAll.error}</div>}
          </div>
        </Card>

        <Card title="Exchange & Model Credentials" icon={<KeyRound className="w-4 h-4 text-brand-400" />}>
          <div className="p-5 space-y-3 text-sm text-zinc-400 leading-relaxed">
            {/* This page used to show password inputs for the Binance and
                OpenAI keys with a Save button that did nothing. Credentials are
                server-side configuration, not per-user settings, so the form is
                replaced with an accurate description of where they live. */}
            <p>
              Exchange and model credentials are server-side configuration, not per-user settings.
              Set them in the deployment environment:
            </p>
            <ul className="space-y-1 font-mono text-xs text-zinc-300">
              <li>· BINANCE_API_KEY / BINANCE_SECRET</li>
              <li>· BINANCE_TESTNET</li>
              <li>· ALLOW_MAINNET_TRADING</li>
              <li>· OPENAI_API_KEY / OPENAI_MODEL</li>
            </ul>
            <div className="flex items-start gap-2 mt-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
              <ShieldCheck className="w-4 h-4 text-yellow-400 shrink-0 mt-0.5" />
              <p className="text-xs text-yellow-200">
                Placing real orders requires <span className="font-mono">BINANCE_TESTNET=false</span> and{' '}
                <span className="font-mono">ALLOW_MAINNET_TRADING=true</span> together. Either one alone
                keeps the platform on testnet.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
