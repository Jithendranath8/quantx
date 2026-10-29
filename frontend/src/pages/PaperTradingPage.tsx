import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { motion } from 'motion/react';
import { CheckCircle2, Loader2, Plus, Wallet, X } from 'lucide-react';

import api from '../lib/api';
import { formatNumber, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import { usePaperAccounts } from '../lib/usePaperAccount';
import type { PaperAccount, PaperOrder, Ticker } from '../lib/types';
import { AsyncSection, Card, PageHeader, StatTile } from '../components/ui';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'];
const BALANCE_PRESETS = [10_000, 100_000, 1_000_000];

const fieldClass =
  'h-11 w-full rounded-xl bg-ink-950 px-3.5 font-mono text-sm text-white ring-1 ring-inset ring-white/10 ' +
  'placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500/60';

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 font-mono text-xs ring-1 ring-inset transition cursor-pointer ${
        active ? 'bg-brand-500/15 text-brand-300 ring-brand-500/35' : 'text-zinc-400 ring-white/10 hover:text-white'
      }`}
    >
      {children}
    </button>
  );
}

/** Create-account form; shown as the page's centrepiece when there are no accounts yet. */
function NewAccountForm({ onCreated, onCancel, first }: { onCreated: () => void; onCancel?: () => void; first: boolean }) {
  const [name, setName] = useState(first ? 'My first paper account' : 'Paper account');
  const [balance, setBalance] = useState(100_000);

  const create = useAction(async () => {
    await api.post<PaperAccount>('/paper/accounts', { name, initial_balance: balance });
    onCreated();
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void create.run();
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Account name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} className={`${fieldClass} mt-1.5 font-sans`} required />
        </label>
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Starting balance (USD)</span>
          <input
            type="number"
            min={100}
            value={balance}
            onChange={(e) => setBalance(Number(e.target.value))}
            className={`${fieldClass} mt-1.5`}
            required
          />
          <div className="mt-2 flex gap-1.5">
            {BALANCE_PRESETS.map((b) => (
              <Chip key={b} active={balance === b} onClick={() => setBalance(b)}>
                ${b >= 1_000_000 ? `${b / 1_000_000}M` : `${b / 1000}k`}
              </Chip>
            ))}
          </div>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={create.pending || !name.trim() || balance < 100}
          className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand-500 px-5 text-sm font-semibold text-ink-950 transition hover:bg-brand-400 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {create.pending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          {first ? 'Fund paper account' : 'Create account'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-sm text-zinc-400 hover:text-white cursor-pointer">
            Cancel
          </button>
        )}
        {create.error && <p role="alert" className="text-xs text-red-400">{create.error}</p>}
      </div>
    </form>
  );
}

/** Market order ticket with an estimate from the latest ticker price. */
function OrderTicket({ account, onFilled }: { account: PaperAccount; onFilled: () => void }) {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('0.01');
  const [lastOrder, setLastOrder] = useState<PaperOrder | null>(null);

  const ticker = useApi<Ticker>(() => api.get<Ticker>('/market/ticker', { params: { symbol } }).then((r) => r.data), [symbol]);
  const price = Number(ticker.data?.lastPrice);
  const qty = Number(quantity);
  const estimate = Number.isFinite(price) && price > 0 && qty > 0 ? price * qty : null;

  const submit = useAction(async () => {
    const res = await api.post<PaperOrder>('/paper/orders', {
      account_id: account.id,
      symbol,
      side,
      order_type: 'MARKET',
      quantity: qty,
    });
    setLastOrder(res.data);
    onFilled();
    return res.data;
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit.run();
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5 p-5">
      <div>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Market</span>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SYMBOLS.map((s) => (
            <Chip key={s} active={symbol === s} onClick={() => setSymbol(s)}>{s.replace('USDT', '')}</Chip>
          ))}
        </div>
      </div>

      {/* BUY / SELL segmented control */}
      <div role="radiogroup" aria-label="Side" className="grid grid-cols-2 gap-1 rounded-xl bg-ink-950 p-1 ring-1 ring-inset ring-white/[0.07]">
        {(['BUY', 'SELL'] as const).map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={side === s}
            onClick={() => setSide(s)}
            className={`relative h-10 rounded-lg text-sm font-semibold transition cursor-pointer ${
              side === s ? (s === 'BUY' ? 'text-emerald-950' : 'text-red-950') : 'text-zinc-400 hover:text-white'
            }`}
          >
            {side === s && (
              <motion.span
                layoutId="side-pill"
                className={`absolute inset-0 rounded-lg ${s === 'BUY' ? 'bg-emerald-400' : 'bg-red-400'}`}
                transition={{ type: 'spring', stiffness: 500, damping: 38 }}
              />
            )}
            <span className="relative">{s === 'BUY' ? 'Buy' : 'Sell'}</span>
          </button>
        ))}
      </div>

      <label className="block">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Quantity ({symbol.replace('USDT', '')})</span>
        <input type="number" step="any" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} className={`${fieldClass} mt-1.5`} />
      </label>

      <dl className="space-y-2 rounded-xl border border-white/[0.06] bg-ink-950/50 px-4 py-3 text-xs">
        <div className="flex justify-between">
          <dt className="text-zinc-500">Last price</dt>
          <dd className="font-mono text-zinc-200">{Number.isFinite(price) && price > 0 ? formatNumber(price) : '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500">Estimated {side === 'BUY' ? 'cost' : 'proceeds'}</dt>
          <dd className="font-mono text-white">{estimate === null ? '—' : `≈ ${formatUsd(estimate)}`}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500">Available balance</dt>
          <dd className="font-mono text-zinc-200">{formatUsd(account.current_balance)}</dd>
        </div>
        <p className="pt-1 text-[11px] text-zinc-600">Filled against the live price with simulated slippage and fees, so the fill differs slightly from the estimate.</p>
      </dl>

      <button
        type="submit"
        disabled={submit.pending || !(qty > 0)}
        className={`inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
          side === 'BUY' ? 'bg-emerald-400 text-emerald-950 hover:bg-emerald-300' : 'bg-red-400 text-red-950 hover:bg-red-300'
        }`}
      >
        {submit.pending && <Loader2 className="w-4 h-4 animate-spin" />}
        {submit.pending ? 'Placing order…' : `${side === 'BUY' ? 'Buy' : 'Sell'} ${quantity || 0} ${symbol.replace('USDT', '')}`}
      </button>
      {submit.error && <p role="alert" className="text-xs text-red-400">{submit.error}</p>}

      {lastOrder && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 rounded-xl bg-emerald-500/[0.06] px-4 py-3 ring-1 ring-inset ring-emerald-500/20"
        >
          <CheckCircle2 className="mt-0.5 w-4 h-4 shrink-0 text-emerald-400" />
          <div className="text-xs">
            <p className="text-white">
              {lastOrder.status}: {lastOrder.side} {lastOrder.filled_quantity} {lastOrder.symbol} at {formatUsd(lastOrder.filled_price)}
            </p>
            <p className="mt-0.5 text-zinc-500">See it under Positions and Orders.</p>
          </div>
          <button type="button" onClick={() => setLastOrder(null)} aria-label="Dismiss" className="ml-auto text-zinc-500 hover:text-white cursor-pointer">
            <X className="w-3.5 h-3.5" />
          </button>
        </motion.div>
      )}
    </form>
  );
}

export default function PaperTradingPage() {
  const { accounts, selectedId, setSelectedId, selected } = usePaperAccounts();
  const [creating, setCreating] = useState(false);
  const hasAccounts = (accounts.data?.length ?? 0) > 0;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Paper Trading"
        description="Trade play money against live Binance prices. Fills include simulated slippage and fees. Every buy passes the risk engine — sizing, exposure, open-position and circuit-breaker limits; selling to exit always goes through."
      />

      <AsyncSection state={accounts}>
        {() =>
          !hasAccounts ? (
            <section className="relative overflow-hidden rounded-3xl border border-white/[0.07] bg-ink-900/70 p-6 sm:p-10">
              <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-brand-500/10 blur-3xl" />
              <div className="relative max-w-2xl">
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-brand-400">Step 2 of your first session</p>
                <h2 className="mt-2 font-display text-4xl text-white">
                  Fund a paper account. <em className="text-zinc-400">Nothing real is at risk.</em>
                </h2>
                <p className="mt-3 text-sm text-zinc-400">
                  Pick a starting balance. You can open as many accounts as you like — one per strategy keeps results clean.
                </p>
                <div className="mt-8">
                  <NewAccountForm first onCreated={() => accounts.reload()} />
                </div>
              </div>
            </section>
          ) : (
            <div className="space-y-6">
              <div className="flex gap-3 overflow-x-auto pb-1">
                {accounts.data!.map((a) => {
                  // Cash spent on an open position is not a loss, so P&L is realised + unrealised.
                  const pnl = a.realized_pnl + a.unrealized_pnl;
                  const active = a.id === selectedId;
                  return (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => setSelectedId(a.id)}
                      aria-pressed={active}
                      className={`min-w-[15rem] shrink-0 rounded-2xl border p-4 text-left transition cursor-pointer ${
                        active ? 'border-brand-500/40 bg-brand-500/[0.06]' : 'border-white/[0.07] bg-ink-900/60 hover:border-white/15'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="flex min-w-0 items-center gap-2 text-sm text-white">
                          <Wallet className={`w-4 h-4 shrink-0 ${active ? 'text-brand-400' : 'text-zinc-500'}`} />
                          <span className="truncate">{a.name}</span>
                        </span>
                        <span className="shrink-0 font-mono text-[10px] text-zinc-600">{a.id.slice(0, 6)}</span>
                      </div>
                      <p className="mt-3 font-mono text-xl text-white">{formatUsd(a.current_balance)}</p>
                      <p className="text-[11px] text-zinc-500">cash</p>
                      <p className={`mt-0.5 font-mono text-xs ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {pnl >= 0 ? '+' : ''}{formatUsd(pnl)} P&L
                      </p>
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="grid min-w-[10rem] shrink-0 place-items-center rounded-2xl border border-dashed border-white/15 p-4 text-sm text-zinc-400 hover:border-white/30 hover:text-white cursor-pointer"
                >
                  <span className="flex items-center gap-2"><Plus className="w-4 h-4" /> New account</span>
                </button>
              </div>

              {creating && (
                <Card title="New paper account" icon={<Plus className="w-4 h-4" />}>
                  <div className="p-5">
                    <NewAccountForm
                      first={false}
                      onCreated={() => {
                        setCreating(false);
                        accounts.reload();
                      }}
                      onCancel={() => setCreating(false)}
                    />
                  </div>
                </Card>
              )}

              {selected && (
                <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 content-start">
                    <StatTile label="Cash balance" value={formatUsd(selected.current_balance)} icon={<Wallet className="w-4 h-4" />} />
                    <StatTile label="Starting balance" value={formatUsd(selected.initial_balance)} />
                    <StatTile
                      label="Realized PnL"
                      value={formatUsd(selected.realized_pnl)}
                      sub="From closed trades"
                      tone={selected.realized_pnl >= 0 ? 'positive' : 'negative'}
                    />
                    <StatTile
                      label="Unrealized PnL"
                      value={formatUsd(selected.unrealized_pnl)}
                      sub="On open positions"
                      tone={selected.unrealized_pnl >= 0 ? 'positive' : 'negative'}
                    />
                  </div>
                  <Card title={`Order ticket · ${selected.name}`}>
                    <OrderTicket account={selected} onFilled={() => accounts.reload()} />
                  </Card>
                </div>
              )}
            </div>
          )
        }
      </AsyncSection>
    </div>
  );
}
