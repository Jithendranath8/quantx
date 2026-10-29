import { useEffect, useState } from 'react';
import { Gauge, Layers, Octagon, Percent, Scale, ShieldAlert, ShieldCheck, Timer } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import api from '../lib/api';
import { formatPercent } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { RiskConfig, RiskState } from '../lib/types';
import { AsyncSection, PageHeader } from '../components/ui';

type NumericRule = Exclude<keyof RiskConfig, 'circuit_breaker_active'>;

// What each limit means in practice, checked against RiskManager.validate_trade
// and the two services that call it. Every rule applies to paper and live buys;
// live limits measure the book rebuilt from orders QuantX itself placed.
const RULES: { key: NumericRule; label: string; icon: LucideIcon; explain: string }[] = [
  { key: 'max_risk_per_trade_pct', label: 'Risk per trade', icon: Percent, explain: 'A buy larger than the engine’s size for its stop distance is refused, so a stopped-out trade loses at most this share of equity.' },
  { key: 'max_daily_loss_pct', label: 'Daily loss cap', icon: Octagon, explain: 'Once today’s realised losses (UTC) reach this share of equity, buys are refused. On live this also trips the circuit breaker; a paper account is blocked until midnight UTC.' },
  { key: 'max_portfolio_exposure_pct', label: 'Portfolio exposure', icon: Layers, explain: 'A buy is refused if it would push open positions, valued at current prices, above this share of equity.' },
  { key: 'max_leverage', label: 'Leverage', icon: Scale, explain: 'Any order asking for more leverage than this is refused.' },
  { key: 'max_concurrent_trades', label: 'Concurrent trades', icon: Gauge, explain: 'Once this many positions are open, a buy in a new symbol is refused. Adding to an open position is allowed.' },
  { key: 'cooldown_period_minutes', label: 'Cooldown', icon: Timer, explain: 'After a position is closed at a loss, buying that symbol again is blocked for this long.' },
];

function renderValue(key: NumericRule, value: number): string {
  if (key.endsWith('_pct')) return formatPercent(value * 100);
  if (key === 'max_leverage') return `${value}×`;
  if (key === 'cooldown_period_minutes') return `${value} min`;
  return String(value);
}

/** Big, unambiguous trading status with a two-step halt/resume control. */
function StatusBanner({
  state,
  onToggle,
  pending,
}: {
  state: RiskState;
  onToggle: (halt: boolean) => void;
  pending: boolean;
}) {
  const halted = state.circuit_breaker_active;
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!confirming) return;
    // Disarm the confirmation if it is not used, so a stray click later can't halt trading.
    const id = window.setTimeout(() => setConfirming(false), 4000);
    return () => window.clearTimeout(id);
  }, [confirming]);

  const act = () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setConfirming(false);
    onToggle(!halted);
  };

  return (
    <section
      aria-live="polite"
      className={`relative overflow-hidden rounded-3xl border p-6 sm:p-8 ${
        halted ? 'border-red-500/30 bg-red-500/[0.06]' : 'border-emerald-500/20 bg-emerald-500/[0.04]'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-6">
        <div className="flex items-start gap-4">
          <span
            className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl ring-1 ring-inset ${
              halted ? 'bg-red-500/15 text-red-300 ring-red-500/30' : 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25'
            }`}
          >
            {halted ? <ShieldAlert className="w-6 h-6" /> : <ShieldCheck className="w-6 h-6" />}
          </span>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-zinc-500">Circuit breaker</p>
            <h2 className="mt-1 font-display text-4xl text-white">
              {halted ? <>Trading is <em className="text-red-300">halted.</em></> : <>Trading is <em className="text-emerald-300">permitted.</em></>}
            </h2>
            <p className="mt-2 max-w-xl text-sm text-zinc-400">
              {halted
                ? `New buys are refused until trading is resumed — on paper you can still sell to exit a position.${state.circuit_breaker_reason ? ` Reason: ${state.circuit_breaker_reason}.` : ''}`
                : 'New orders are allowed, but each buy is still checked against the rules below.'}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={act}
          disabled={pending}
          className={`h-11 rounded-xl px-5 text-sm font-semibold transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
            halted
              ? 'bg-white text-ink-950 hover:bg-zinc-200'
              : confirming
                ? 'bg-red-500 text-white hover:bg-red-400'
                : 'bg-red-500/10 text-red-300 ring-1 ring-inset ring-red-500/30 hover:bg-red-500/20'
          }`}
        >
          {pending ? 'Saving…' : confirming ? (halted ? 'Confirm resume' : 'Confirm halt') : halted ? 'Resume trading' : 'Halt all trading'}
        </button>
      </div>
    </section>
  );
}

export default function RiskPage() {
  const config = useApi<RiskConfig>(() => api.get<RiskConfig>('/risk/config').then((r) => r.data));
  const state = useApi<RiskState>(() => api.get<RiskState>('/risk/state').then((r) => r.data));

  const toggle = useAction(async (active: boolean) => {
    await api.post('/risk/circuit-breaker/toggle', null, {
      params: { active, reason: active ? 'MANUAL_UI_HALT' : undefined },
    });
    config.reload();
    state.reload();
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title="Risk Engine"
        description="Hard limits checked on every buy, paper or live, whoever — or whatever — placed it. AI signals cannot override them, and the breaker below halts new trading at once."
      />

      {toggle.error && <div role="alert" className="text-sm text-red-400">{toggle.error}</div>}

      <AsyncSection state={state}>
        {(data) => <StatusBanner state={data} onToggle={(halt) => void toggle.run(halt)} pending={toggle.pending} />}
      </AsyncSection>

      <section aria-labelledby="rules-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <h2 id="rules-heading" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
            The rules each buy is checked against
          </h2>
          <p className="text-xs text-zinc-600">Set on the server; changes need a deploy, not a click.</p>
        </div>
        <AsyncSection state={config}>
          {(data) => (
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {RULES.map(({ key, label, icon: Icon, explain }) => (
                <li key={key} className="surface rounded-2xl p-5">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-sm text-zinc-300">
                      <Icon className="w-4 h-4 text-zinc-500" /> {label}
                    </span>
                    <span className="font-mono text-2xl text-white">{renderValue(key, data[key])}</span>
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-zinc-500">{explain}</p>
                </li>
              ))}
            </ul>
          )}
        </AsyncSection>
      </section>

      <p className="text-xs text-zinc-600">
        The circuit breaker is stored per user in the database, so a halt applies to every worker process and survives
        a restart. Live limits see only orders placed through QuantX: assets bought elsewhere are not part of the book.
        Sells are never sized or blocked by these rules, so you can always exit; a halt still stops live sells.
      </p>
    </div>
  );
}
