import { useState } from 'react';
import { AlertTriangle, FlaskConical, PlugZap, Power, Siren, Zap } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime, formatNumber, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { KillSwitchStatus, LiveOrder, SystemHealth } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  TableWrap,
  Td,
  TextInput,
  Th,
} from '../components/ui';

interface KillSwitchResult {
  status: string;
  fully_successful: boolean;
  total_orders_cancelled: number;
  binance_cancellations_failed: number;
  errors: string[];
  message: string;
}

function statusTone(status: string): 'positive' | 'negative' | 'warning' | 'neutral' {
  if (status === 'FILLED') return 'positive';
  if (status === 'REJECTED' || status === 'CANCELED') return 'negative';
  if (status.startsWith('UNKNOWN') || status === 'PENDING_SUBMIT') return 'warning';
  return 'neutral';
}

/**
 * Where an order would actually go, read from the execution engine's health
 * entry. Ambiguity here is how people trade real money by accident.
 */
function VenueBanner() {
  const health = useApi<SystemHealth>(() => api.get<SystemHealth>('/health/system').then((r) => r.data));
  const engine = health.data?.subsystems.execution_engine;
  if (!engine) {
    return (
      <div role="status" className="rounded-2xl border border-white/[0.07] px-5 py-4 text-sm text-zinc-500">
        {health.error ? 'Could not determine the execution venue — treat orders as real.' : 'Checking where orders go…'}
      </div>
    );
  }

  const mainnet = engine.mainnet_trading_enabled === true;
  const connected = engine.status === 'READY';
  const view = mainnet
    ? {
        icon: Siren,
        tone: 'border-red-500/40 bg-red-500/[0.08] text-red-200',
        title: 'MAINNET — orders here use real money.',
        body: 'BINANCE_TESTNET=false and ALLOW_MAINNET_TRADING=true are both set on the server. Every order below is real.',
      }
    : connected
      ? {
          icon: FlaskConical,
          tone: 'border-sky-400/25 bg-sky-400/[0.05] text-sky-100',
          title: 'Binance testnet — real API calls, test funds.',
          body: 'Orders reach the exchange’s test environment. Mainnet stays locked until two separate server flags are set.',
        }
      : {
          icon: PlugZap,
          tone: 'border-white/10 bg-white/[0.02] text-zinc-200',
          title: 'Not connected to an exchange.',
          body: 'No exchange credentials are configured, so live orders are refused. Use Paper Trading to practise against live prices.',
        };
  const Icon = view.icon;

  return (
    <div role="status" className={`flex items-start gap-4 rounded-2xl border px-5 py-4 ${view.tone}`}>
      <Icon className="mt-0.5 w-5 h-5 shrink-0" />
      <div>
        <p className="text-sm font-semibold">{view.title}</p>
        <p className="mt-1 text-xs opacity-80">{view.body}</p>
      </div>
    </div>
  );
}

export default function LiveTradingPage() {
  const status = useApi<KillSwitchStatus>(
    () => api.get<KillSwitchStatus>('/live/kill-switch/status').then((r) => r.data),
  );
  const orders = useApi<LiveOrder[]>(
    () => api.get<LiveOrder[]>('/live/orders', { params: { limit: 100 } }).then((r) => r.data),
  );

  const [symbol, setSymbol] = useState('BTCUSDT');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('0.001');
  const [price, setPrice] = useState('');
  const [killResult, setKillResult] = useState<KillSwitchResult | null>(null);
  // Live orders take two deliberate clicks: review, then confirm.
  const [reviewing, setReviewing] = useState(false);

  const submit = useAction(async () => {
    await api.post('/live/orders', {
      symbol,
      side,
      order_type: price ? 'LIMIT' : 'MARKET',
      quantity: Number(quantity),
      price: price ? Number(price) : null,
    });
    setReviewing(false);
    orders.reload();
  });

  const killSwitch = useAction(async () => {
    const res = await api.post<KillSwitchResult>('/live/kill-switch');
    setKillResult(res.data);
    status.reload();
    orders.reload();
    return res.data;
  });

  const resume = useAction(async () => {
    await api.post('/live/kill-switch/deactivate');
    setKillResult(null);
    status.reload();
  });

  const halted = status.data?.circuit_breaker_active ?? false;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Live Trading"
        description="Orders sent to the exchange, each one checked by the risk engine first. The kill switch cancels everything and halts trading."
        actions={
          halted ? (
            <Button variant="primary" onClick={() => void resume.run()} disabled={resume.pending}>
              <span className="flex items-center gap-1.5"><Power className="w-3 h-3" /> Resume trading</span>
            </Button>
          ) : (
            <Button variant="danger" onClick={() => void killSwitch.run()} disabled={killSwitch.pending}>
              <span className="flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3" /> {killSwitch.pending ? 'Halting…' : 'Kill switch'}
              </span>
            </Button>
          )
        }
      />

      <VenueBanner />

      {halted && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          Trading is halted. {status.data?.reason && <span className="font-mono text-xs">({status.data.reason})</span>}
        </div>
      )}

      {killResult && (
        <div
          className={`px-4 py-3 rounded-lg border text-sm ${
            killResult.fully_successful
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300'
          }`}
        >
          <p>{killResult.message}</p>
          {/* A partially successful halt is surfaced, not hidden behind a
              generic success message. */}
          {killResult.errors.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs font-mono">
              {killResult.errors.map((e, i) => <li key={i}>· {e}</li>)}
            </ul>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Submit Live Order" icon={<Zap className="w-4 h-4 text-brand-400" />}>
          <div className="p-5 space-y-3">
            <Field label="Symbol">
              <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
            </Field>
            <Field label="Side">
              <Select value={side} onChange={(e) => setSide(e.target.value as 'BUY' | 'SELL')}>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </Select>
            </Field>
            <Field label="Quantity">
              <TextInput type="number" step="any" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </Field>
            <Field label="Limit price (blank for market)">
              <TextInput type="number" step="any" value={price} onChange={(e) => setPrice(e.target.value)} />
            </Field>
            {reviewing ? (
              <div className="space-y-3 rounded-xl border border-white/10 bg-ink-950/60 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Review order</p>
                <p className="font-mono text-sm text-white">
                  <span className={side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>{side}</span> {quantity} {symbol}{' '}
                  {price ? `@ ${price} (limit)` : 'at market'}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant={side === 'BUY' ? 'primary' : 'danger'}
                    onClick={() => void submit.run()}
                    disabled={submit.pending || halted}
                  >
                    {submit.pending ? 'Submitting…' : 'Confirm & send'}
                  </Button>
                  <Button variant="secondary" onClick={() => setReviewing(false)} disabled={submit.pending}>
                    Edit
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant={side === 'BUY' ? 'primary' : 'danger'}
                onClick={() => setReviewing(true)}
                disabled={halted || !symbol || !(Number(quantity) > 0)}
              >
                Review {side}
              </Button>
            )}
            {submit.error && <div className="text-xs text-red-400">{submit.error}</div>}
            <p className="text-xs text-zinc-600 leading-relaxed">
              Mainnet execution requires both BINANCE_TESTNET=false and ALLOW_MAINNET_TRADING=true on
              the server. Otherwise the order is refused rather than simulated.
            </p>
          </div>
        </Card>

        <Card title="Live Orders" className="lg:col-span-2">
          <AsyncSection
            state={orders}
            emptyWhen={(d) => d.length === 0}
            emptyMessage="No live orders"
            emptyHint="Orders submitted to the exchange appear here with their real exchange ids."
          >
            {(data) => (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-zinc-900/60">
                    <tr>
                      <Th>Symbol</Th>
                      <Th>Side</Th>
                      <Th align="right">Quantity</Th>
                      <Th align="right">Filled</Th>
                      <Th>Status</Th>
                      <Th>Env</Th>
                      <Th>Created</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50">
                    {data.map((o) => (
                      <tr key={o.id} className="hover:bg-zinc-800/30 transition-colors">
                        <Td mono className="text-white font-semibold">{o.symbol}</Td>
                        <Td><Badge tone={o.side === 'BUY' ? 'positive' : 'negative'}>{o.side}</Badge></Td>
                        <Td align="right" mono className="text-zinc-300">{formatNumber(o.quantity, 6)}</Td>
                        <Td align="right" mono className="text-white">{formatUsd(o.filled_price)}</Td>
                        <Td>
                          <Badge tone={statusTone(o.status)}>{o.status}</Badge>
                          {o.rejection_reason && (
                            <div className="text-xs text-red-400 mt-1 max-w-xs truncate" title={o.rejection_reason}>
                              {o.rejection_reason}
                            </div>
                          )}
                        </Td>
                        <Td><Badge tone={o.is_testnet ? 'info' : 'warning'}>{o.is_testnet ? 'testnet' : 'MAINNET'}</Badge></Td>
                        <Td className="text-zinc-500 text-xs">{formatDateTime(o.created_at)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </AsyncSection>
        </Card>
      </div>
    </div>
  );
}
