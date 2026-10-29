import { useState } from 'react';
import type { FormEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Bot, Calculator, Clock, Coins, Loader2, ShieldAlert, ShieldCheck, Sparkles, Target } from 'lucide-react';

import api from '../lib/api';
import { formatNumber } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { AgentDecision, AIObservability } from '../lib/types';
import { AsyncSection, Card, PageHeader, StatTile } from '../components/ui';
import { SpotlightCard } from '../components/fx/effects';

const QUICK_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];
// Prefixes the backend uses for its two non-model outcomes: the validator
// overruling the model, and the safe fallback when the provider call failed.
const VALIDATOR_REJECTION = 'Decision rejected by deterministic validator';
const PROVIDER_FALLBACK = 'Default to WAIT. Reason:';

const ACTION_STYLE = {
  BUY: { text: 'text-emerald-400', bar: 'bg-emerald-400', ring: 'ring-emerald-500/25', glow: 'rgba(16,185,129,0.14)', verb: 'Go long' },
  SELL: { text: 'text-red-400', bar: 'bg-red-400', ring: 'ring-red-500/25', glow: 'rgba(239,68,68,0.14)', verb: 'Go short' },
  WAIT: { text: 'text-yellow-300', bar: 'bg-yellow-300', ring: 'ring-yellow-400/25', glow: 'rgba(250,204,21,0.10)', verb: 'Stand aside' },
} as const;

/** Stop, entry and target drawn to scale, so the trade's shape is visible at a glance. */
function PriceLadder({ decision }: { decision: AgentDecision }) {
  const levels = [
    { key: 'Target', value: decision.take_profit, color: 'bg-emerald-400', text: 'text-emerald-400' },
    { key: 'Entry', value: decision.entry_price, color: 'bg-white', text: 'text-white' },
    { key: 'Stop', value: decision.stop_loss, color: 'bg-red-400', text: 'text-red-400' },
  ].filter((l): l is { key: string; value: number; color: string; text: string } => l.value !== null && l.value > 0);

  if (levels.length < 2) {
    return <p className="text-sm text-zinc-500">No price levels — the agent did not propose a trade.</p>;
  }
  const values = levels.map((l) => l.value);
  const hi = Math.max(...values);
  const lo = Math.min(...values);
  const span = hi - lo || 1;

  return (
    <div className="relative h-44" role="img" aria-label="Price levels of the proposed trade">
      <span className="absolute left-[6rem] top-0 bottom-0 w-px bg-white/[0.08]" />
      {levels.map((l) => {
        const top = ((hi - l.value) / span) * 100;
        return (
          <div key={l.key} className="absolute inset-x-0 flex items-center gap-3 -translate-y-1/2" style={{ top: `${top}%` }}>
            <span className={`w-20 text-right font-mono text-[11px] uppercase tracking-wider ${l.text}`}>{l.key}</span>
            <span className={`h-2 w-2 shrink-0 rounded-full ${l.color} ring-4 ring-ink-900`} />
            <span className="h-px flex-1 border-t border-dashed border-white/10" />
            <span className="font-mono text-sm text-zinc-200">{formatNumber(l.value)}</span>
          </div>
        );
      })}
    </div>
  );
}

function DecisionView({ decision, symbol }: { decision: AgentDecision; symbol: string }) {
  const style = ACTION_STYLE[decision.action];
  const rejected = decision.reasoning.startsWith(VALIDATOR_REJECTION);
  const fallback = decision.reasoning.startsWith(PROVIDER_FALLBACK);
  const confidence = Math.round(decision.confidence * 100);

  return (
    <motion.div
      key={`${symbol}-${decision.reasoning}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="relative"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -inset-8 rounded-[2rem]"
        style={{ background: `radial-gradient(400px circle at 20% 0%, ${style.glow}, transparent 70%)` }}
      />
      <div className="relative">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-zinc-500">{symbol} · decision</p>
            <p className={`mt-1 font-display text-7xl leading-none ${style.text}`}>{decision.action}</p>
            <p className="mt-2 text-sm text-zinc-400">{fallback ? 'Safe fallback — not a market view' : style.verb}</p>
          </div>
          <div className="min-w-[10rem]">
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Confidence</span>
              <span className="font-mono text-lg text-white">{confidence}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div
                className={`h-full rounded-full ${style.bar}`}
                initial={{ width: 0 }}
                animate={{ width: `${confidence}%` }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
              />
            </div>
            {decision.risk_reward_ratio !== null && (
              <p className="mt-3 flex items-center justify-between text-xs text-zinc-500">
                Reward : risk <span className="font-mono text-sm text-white">{decision.risk_reward_ratio.toFixed(2)}</span>
              </p>
            )}
          </div>
        </div>

        <div
          className={`mt-6 flex items-start gap-3 rounded-xl px-4 py-3 ring-1 ring-inset ${
            fallback
              ? 'bg-red-500/[0.07] ring-red-500/25'
              : rejected
                ? 'bg-yellow-500/[0.06] ring-yellow-400/25'
                : 'bg-emerald-500/[0.05] ring-emerald-500/20'
          }`}
        >
          {fallback ? (
            <ShieldAlert className="mt-0.5 w-4 h-4 shrink-0 text-red-400" />
          ) : rejected ? (
            <ShieldAlert className="mt-0.5 w-4 h-4 shrink-0 text-yellow-300" />
          ) : (
            <ShieldCheck className="mt-0.5 w-4 h-4 shrink-0 text-emerald-400" />
          )}
          <p className="text-sm text-zinc-300">
            {fallback
              ? 'The AI provider could not be reached, so the agent returned its safe default. Check the AI Service status on the dashboard and the provider settings.'
              : rejected
                ? 'The validator overruled the model: its numbers did not add up, so the decision was downgraded to WAIT.'
                : 'Passed the deterministic validator. Any order from it would still have to pass the risk engine’s limits.'}
          </p>
        </div>

        <div className="mt-8 grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Reasoning</h3>
            <p className="text-sm leading-relaxed text-zinc-300 whitespace-pre-line">{decision.reasoning}</p>
          </div>
          <div>
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Trade levels</h3>
            <PriceLadder decision={decision} />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/** Shown while the request runs; names the steps without pretending to track them. */
function Working() {
  const steps = [
    { icon: Coins, label: 'Building market context' },
    { icon: Bot, label: 'Model reasoning' },
    { icon: Calculator, label: 'Validator re-check' },
  ];
  return (
    <div className="flex flex-col items-center justify-center gap-6 py-16" role="status">
      <Loader2 className="w-6 h-6 animate-spin text-brand-400" />
      <ul className="flex flex-wrap justify-center gap-2">
        {steps.map((s, i) => (
          <motion.li
            key={s.label}
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.07] px-3 py-1.5 text-xs text-zinc-400"
            animate={{ opacity: [0.35, 1, 0.35] }}
            transition={{ duration: 1.8, repeat: Infinity, delay: i * 0.4 }}
          >
            <s.icon className="w-3.5 h-3.5" /> {s.label}
          </motion.li>
        ))}
      </ul>
      <p className="text-xs text-zinc-600">Usually a few seconds; local models can take longer.</p>
    </div>
  );
}

export default function AgentPage() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [analysed, setAnalysed] = useState<{ symbol: string; decision: AgentDecision } | null>(null);

  const observability = useApi<AIObservability>(
    () => api.get<AIObservability>('/research/ai-observability').then((r) => r.data),
  );

  const analyze = useAction(async () => {
    const target = symbol.trim().toUpperCase();
    const res = await api.get<AgentDecision>('/agent/analyze', { params: { symbol: target } });
    setAnalysed({ symbol: target, decision: res.data });
    observability.reload();
    return res.data;
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (symbol.trim()) void analyze.run();
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="AI Trading Agent"
        description="Hand the agent a symbol. It reads candles, indicators, funding, open interest and your positions, proposes BUY, SELL or WAIT — and the validator checks its arithmetic before you see it."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Card title="Ask the agent" icon={<Sparkles className="w-4 h-4" />}>
          <form onSubmit={submit} className="space-y-5 p-5">
            <div>
              <label htmlFor="agent-symbol" className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                Symbol
              </label>
              <input
                id="agent-symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="mt-1.5 h-11 w-full rounded-xl bg-ink-950 px-3.5 font-mono text-sm text-white ring-1 ring-inset ring-white/10 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500/60"
                placeholder="BTCUSDT"
                autoComplete="off"
                spellCheck={false}
              />
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {QUICK_SYMBOLS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSymbol(s)}
                    className={`rounded-full px-2.5 py-1 font-mono text-[11px] ring-1 ring-inset transition cursor-pointer ${
                      symbol === s ? 'bg-brand-500/15 text-brand-300 ring-brand-500/35' : 'text-zinc-400 ring-white/10 hover:text-white'
                    }`}
                  >
                    {s.replace('USDT', '')}
                  </button>
                ))}
              </div>
            </div>
            <button
              type="submit"
              disabled={analyze.pending || !symbol.trim()}
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-brand-500 text-sm font-semibold text-ink-950 transition hover:bg-brand-400 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {analyze.pending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
              {analyze.pending ? 'Analysing…' : `Analyse ${symbol || 'symbol'}`}
            </button>
            {analyze.error && (
              <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2.5 text-xs text-red-300 ring-1 ring-inset ring-red-500/20">
                {analyze.error}
              </p>
            )}
            <ul className="space-y-2.5 border-t border-white/[0.06] pt-5 text-xs text-zinc-500">
              <li className="flex gap-2"><Target className="mt-0.5 w-3.5 h-3.5 shrink-0" /> Analysis only — this page never places an order.</li>
              <li className="flex gap-2"><ShieldCheck className="mt-0.5 w-3.5 h-3.5 shrink-0" /> A decision that fails validation comes back as WAIT.</li>
              <li className="flex gap-2"><Clock className="mt-0.5 w-3.5 h-3.5 shrink-0" /> Every call is logged with latency, tokens and cost.</li>
            </ul>
          </form>
        </Card>

        <SpotlightCard className="min-h-[26rem] overflow-hidden p-6 sm:p-8">
          <AnimatePresence mode="wait">
            {analyze.pending ? (
              <motion.div key="working" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <Working />
              </motion.div>
            ) : analysed ? (
              <DecisionView key="decision" decision={analysed.decision} symbol={analysed.symbol} />
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex h-full min-h-[22rem] flex-col items-center justify-center text-center"
              >
                <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.03] ring-1 ring-inset ring-white/[0.08]">
                  <Bot className="w-6 h-6 text-zinc-400" />
                </span>
                <p className="mt-5 font-display text-3xl text-white">No decision yet.</p>
                <p className="mt-2 max-w-sm text-sm text-zinc-500">
                  Pick a symbol and run an analysis. The verdict, the model’s reasoning and the trade’s price levels appear here.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </SpotlightCard>
      </div>

      <section aria-labelledby="track-record">
        <h2 id="track-record" className="mb-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
          Agent track record
        </h2>
        <AsyncSection state={observability}>
          {(data) => (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatTile
                label="Decisions"
                value={data.total_ai_decisions}
                sub={`Last ${data.window_days} days`}
                icon={<Bot className="w-4 h-4" />}
              />
              <StatTile
                label="Win Rate"
                value={data.ai_win_rate_pct === null ? '—' : `${data.ai_win_rate_pct}%`}
                // Null until decisions have settled PnL attached, rather than a
                // constant that looks like a measurement.
                sub={data.ai_win_rate_pct === null ? 'No settled decisions yet' : `${data.settled_decisions} settled`}
              />
              <StatTile
                label="Avg Latency"
                value={data.avg_latency_ms === null ? '—' : `${data.avg_latency_ms}ms`}
              />
              <StatTile
                label="Token Spend"
                value={`$${data.total_cost_usd.toFixed(4)}`}
                sub={`${data.total_tokens_used.toLocaleString()} tokens`}
              />
            </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}
