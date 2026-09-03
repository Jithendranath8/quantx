import React from 'react';
import { KeyRound, LogOut, Settings, ShieldCheck } from 'lucide-react';

import api from '../lib/api';
import { useAction } from '../lib/useApi';
import { useAuth } from '../contexts/useAuth';
import { Badge, Button, Card, PageHeader } from '../components/ui';

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-800/50 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-sm text-white font-mono">{value}</span>
    </div>
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
        <Card title="Account" icon={<Settings className="w-4 h-4 text-cyan-400" />}>
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

        <Card title="Sessions" icon={<LogOut className="w-4 h-4 text-cyan-400" />}>
          <div className="p-5 space-y-3">
            <p className="text-sm text-slate-400">
              Signing out everywhere revokes every refresh token issued to your account, ending all
              active sessions on all devices.
            </p>
            <Button variant="danger" onClick={() => void logoutAll.run()} disabled={logoutAll.pending}>
              {logoutAll.pending ? 'Revoking…' : 'Sign out of all devices'}
            </Button>
            {logoutAll.error && <div className="text-xs text-red-400">{logoutAll.error}</div>}
          </div>
        </Card>

        <Card title="Exchange & Model Credentials" icon={<KeyRound className="w-4 h-4 text-cyan-400" />}>
          <div className="p-5 space-y-3 text-sm text-slate-400 leading-relaxed">
            {/* This page used to show password inputs for the Binance and
                OpenAI keys with a Save button that did nothing. Credentials are
                server-side configuration, not per-user settings, so the form is
                replaced with an accurate description of where they live. */}
            <p>
              Exchange and model credentials are server-side configuration, not per-user settings.
              Set them in the deployment environment:
            </p>
            <ul className="space-y-1 font-mono text-xs text-slate-300">
              <li>· BINANCE_API_KEY / BINANCE_SECRET</li>
              <li>· BINANCE_TESTNET</li>
              <li>· ALLOW_MAINNET_TRADING</li>
              <li>· OPENAI_API_KEY / OPENAI_MODEL</li>
            </ul>
            <div className="flex items-start gap-2 mt-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <ShieldCheck className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-200">
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
