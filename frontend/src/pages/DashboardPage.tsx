import { useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { motion } from 'motion/react';
import {
  Activity, ArrowRight, BarChart3, Check, ChevronDown, Layers, PieChart, Sparkles, TrendingUp, Wallet, X,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { useAuth } from '../contexts/useAuth';
import api from '../lib/api';
import { formatPercent, formatUsd } from '../lib/format';
import { WORKSPACES, appPath } from '../lib/navigation';
import { isOnboardingDismissed, setOnboardingDismissed, visitedPages } from '../lib/onboarding';
import { useApi } from '../lib/useApi';
import type { PaperAccount, PortfolioSummary, SystemHealth } from '../lib/types';
import { AsyncSection, Card, LoadingState, StatTile, Td, TableWrap, Th } from '../components/ui';

// Acronyms keep their casing; CSS `capitalize` would render "ai_service" as "Ai Service".
const ACRONYMS = new Set(['ai', 'api']);

function subsystemLabel(name: string): string {
  return name
    .split('_')
    .map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ');
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

interface Step {
  title: string;
  body: string;
  path: string;
  done: boolean;
}

/** The four-step first session, ticked from real state where it exists. */
function GettingStarted({ hasAccount, onDismiss }: { hasAccount: boolean; onDismiss: () => void }) {
  const visited = useMemo(visitedPages, []);
  const steps: Step[] = [
    { title: 'Look at a market', body: 'Live chart, depth and microstructure for BTCUSDT.', path: 'market', done: visited.has('market') },
    { title: 'Fund a paper account', body: 'Play money against real prices — nothing real is at risk.', path: 'paper-trading', done: hasAccount },
    { title: 'Ask the AI agent', body: 'Read its reasoning and what the validator said about it.', path: 'agent', done: visited.has('agent') },
    { title: 'Backtest before you trust', body: 'Replay a strategy over stored candles.', path: 'backtest', done: visited.has('backtest') },
  ];
  const completed = steps.filter((s) => s.done).length;
  const next = steps.find((s) => !s.done);

  return (
    <section aria-label="Getting started" className="relative overflow-hidden rounded-3xl border border-white/[0.07] bg-ink-900/70 p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-500/10 blur-3xl" />
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-brand-400">Your first session</p>
          <h2 className="mt-2 font-display text-3xl text-white">
            {completed === steps.length ? <>All set. <em className="text-zinc-400">You know your way around.</em></> : <>Four steps to <em className="text-zinc-400">your first decision.</em></>}
          </h2>
        </div>
        <div className="flex items-center gap-4">
          <div
            className="d-radial-progress text-brand-400 bg-white/[0.04] ring-1 ring-inset ring-white/[0.08]"
            style={{ '--value': (completed / steps.length) * 100, '--size': '3.25rem', '--thickness': '3px' } as CSSProperties}
            role="progressbar"
            aria-valuenow={completed}
            aria-valuemin={0}
            aria-valuemax={steps.length}
          >
            <span className="font-mono text-xs text-white">{completed}/{steps.length}</span>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            className="p-2 text-zinc-500 hover:text-white cursor-pointer"
            aria-label="Hide the getting-started checklist"
            title="Hide (you can bring it back from the dashboard)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <ol className="relative mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {steps.map((s, i) => {
          const isNext = s === next;
          return (
            <li key={s.path}>
              <Link
                to={appPath(s.path)}
                className={`group flex h-full flex-col rounded-2xl border p-5 transition cursor-pointer ${
                  isNext
                    ? 'border-brand-500/35 bg-brand-500/[0.06] hover:bg-brand-500/[0.1]'
                    : 'border-white/[0.06] bg-ink-950/40 hover:border-white/15'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`grid h-7 w-7 place-items-center rounded-full text-xs font-mono ring-1 ring-inset ${
                      s.done ? 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30' : isNext ? 'bg-brand-500/15 text-brand-300 ring-brand-500/40' : 'text-zinc-500 ring-white/10'
                    }`}
                  >
                    {s.done ? <Check className="w-3.5 h-3.5" /> : i + 1}
                  </span>
                  {isNext && <span className="text-[10px] font-mono uppercase tracking-wider text-brand-300">Up next</span>}
                </div>
                <h3 className={`mt-4 text-sm font-medium ${s.done ? 'text-zinc-400 line-through decoration-zinc-600' : 'text-white'}`}>{s.title}</h3>
                <p className="mt-1 flex-1 text-xs leading-relaxed text-zinc-500">{s.body}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-xs text-zinc-500 group-hover:text-white">
                  {s.done ? 'Revisit' : 'Start'} <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** One line per subsystem in a compact grid; details are a click away. */
function HealthGrid({ health }: { health: SystemHealth }) {
  const entries = Object.entries(health.subsystems);
  const failing = entries.filter(([, e]) => !e.healthy);
  const [open, setOpen] = useState(failing.length > 0);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left cursor-pointer"
      >
        <span className="text-sm text-zinc-300">
          {failing.length === 0 ? (
            <>All {entries.length} subsystems healthy.</>
          ) : (
            <>
              <span className="text-yellow-300">{failing.length} need attention:</span>{' '}
              {failing.map(([n]) => subsystemLabel(n)).join(', ')}
            </>
          )}
        </span>
        <span className="inline-flex items-center gap-1 text-xs text-zinc-500">
          {open ? 'Hide' : 'Details'}
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {open && (
        <motion.ul
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-1 sm:grid-cols-2 gap-px border-t border-white/[0.05] bg-white/[0.04]"
        >
          {entries.map(([name, entry]) => (
            <li key={name} className="flex items-center justify-between gap-3 bg-ink-900 px-5 py-3" title={typeof entry.detail === 'string' ? entry.detail : undefined}>
              <span className="flex items-center gap-2.5 text-sm text-zinc-300">
                <span className={`h-1.5 w-1.5 rounded-full ${entry.healthy ? 'bg-emerald-400' : 'bg-yellow-400'}`} />
                {subsystemLabel(name)}
              </span>
              <span className={`font-mono text-[11px] ${entry.healthy ? 'text-zinc-500' : 'text-yellow-300'}`}>
                {entry.status.replace(/_/g, ' ')}
              </span>
            </li>
          ))}
        </motion.ul>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const portfolio = useApi<PortfolioSummary>(() => api.get<PortfolioSummary>('/analytics/portfolio').then((r) => r.data));
  const health = useApi<SystemHealth>(() => api.get<SystemHealth>('/health/system').then((r) => r.data));
  const accounts = useApi<PaperAccount[]>(() => api.get<PaperAccount[]>('/paper/accounts').then((r) => r.data));
  const [dismissed, setDismissed] = useState(isOnboardingDismissed);

  const name = user?.full_name?.split(' ')[0] ?? user?.username ?? 'trader';
  const dismiss = (value: boolean) => {
    setOnboardingDismissed(value);
    setDismissed(value);
  };

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-zinc-500">
            {new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
          </p>
          <h1 className="mt-1 font-display text-4xl sm:text-5xl text-white">
            {greeting()}, <em className="text-brand-400">{name}.</em>
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-400">
            Your paper portfolio and the health of the platform. Everything here is simulated unless live trading is
            explicitly enabled on the server.
          </p>
        </div>
        {dismissed && (
          <button
            type="button"
            onClick={() => dismiss(false)}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-zinc-400 ring-1 ring-inset ring-white/10 hover:text-white cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5" /> Show getting started
          </button>
        )}
      </header>

      {!dismissed && <GettingStarted hasAccount={(accounts.data?.length ?? 0) > 0} onDismiss={() => dismiss(true)} />}

      {portfolio.loading && portfolio.data === null ? (
        <LoadingState label="Loading portfolio…" />
      ) : portfolio.error ? (
        <Card>
          <AsyncSection state={portfolio}>{() => null}</AsyncSection>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatTile
            label="Total Equity"
            value={formatUsd(portfolio.data?.total_equity_usd)}
            sub={`Cash ${formatUsd(portfolio.data?.cash_balance_usd)}`}
            icon={<Wallet className="w-4 h-4" />}
          />
          <StatTile
            label="Unrealized PnL"
            value={formatUsd(portfolio.data?.unrealized_pnl_usd)}
            sub={`Realized ${formatUsd(portfolio.data?.realized_pnl_usd)}`}
            tone={(portfolio.data?.unrealized_pnl_usd ?? 0) >= 0 ? 'positive' : 'negative'}
            icon={<TrendingUp className="w-4 h-4" />}
          />
          <StatTile
            label="Win Rate"
            value={formatPercent(portfolio.data?.win_rate_pct)}
            // Null until a position has actually closed, rather than a
            // plausible-looking constant.
            sub={
              portfolio.data?.win_rate_pct === null
                ? 'No closed trades yet'
                : `${portfolio.data?.closed_trades_count ?? 0} closed trades`
            }
            icon={<BarChart3 className="w-4 h-4" />}
          />
          <StatTile
            label="Open Positions"
            value={portfolio.data?.open_positions_count ?? 0}
            sub={`${portfolio.data?.total_trades_count ?? 0} orders total`}
            icon={<Layers className="w-4 h-4" />}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-6">
        <Card title="Asset Allocation" icon={<PieChart className="w-4 h-4" />}>
          <AsyncSection
            state={portfolio}
            emptyWhen={(d) => d.allocations.length === 0}
            emptyMessage="No allocations yet"
            emptyHint="Fund a paper account and place an order — your holdings appear here."
          >
            {(data) => (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-zinc-900/60">
                    <tr>
                      <Th>Asset</Th>
                      <Th align="right">Value</Th>
                      <Th align="right">Weight</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50">
                    {data.allocations.map((a) => (
                      <tr key={a.symbol} className="hover:bg-zinc-800/30 transition-colors">
                        <Td mono className="text-white">{a.symbol}</Td>
                        <Td align="right" mono className="text-zinc-300">{formatUsd(a.value_usd)}</Td>
                        <Td align="right" mono className="text-zinc-400">{formatPercent(a.allocation_pct)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </AsyncSection>
        </Card>

        <div className="space-y-6">
          <Card title="System Health" icon={<Activity className="w-4 h-4" />}>
            <AsyncSection state={health}>{(data) => <HealthGrid health={data} />}</AsyncSection>
          </Card>

          <Card title="Jump into a workspace">
            <ul className="grid grid-cols-2 gap-px bg-white/[0.04]">
              {WORKSPACES.slice(1).map((w) => (
                <li key={w.id}>
                  <Link
                    to={appPath(w.pages[0].path)}
                    className="group flex h-full flex-col gap-1 bg-ink-900 px-5 py-4 hover:bg-ink-850 transition cursor-pointer"
                  >
                    <span className="flex items-center justify-between text-sm text-white">
                      {w.label}
                      <ArrowRight className="w-3.5 h-3.5 text-zinc-600 transition group-hover:translate-x-0.5 group-hover:text-brand-400" />
                    </span>
                    <span className="font-display text-[15px] italic text-zinc-500">{w.question}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
