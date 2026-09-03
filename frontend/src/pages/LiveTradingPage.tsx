import { useState } from 'react';
import { AlertTriangle, Power, Zap } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime, formatNumber, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { KillSwitchStatus, LiveOrder } from '../lib/types';
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

  const submit = useAction(async () => {
    await api.post('/live/orders', {
      symbol,
      side,
      order_type: price ? 'LIMIT' : 'MARKET',
      quantity: Number(quantity),
      price: price ? Number(price) : null,
    });
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
        description="Real exchange execution behind mandatory risk checks"
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
              : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
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
        <Card title="Submit Live Order" icon={<Zap className="w-4 h-4 text-cyan-400" />}>
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
            <Button
              variant={side === 'BUY' ? 'primary' : 'danger'}
              onClick={() => void submit.run()}
              disabled={submit.pending || halted}
            >
              {submit.pending ? 'Submitting…' : `Submit ${side}`}
            </Button>
            {submit.error && <div className="text-xs text-red-400">{submit.error}</div>}
            <p className="text-xs text-slate-600 leading-relaxed">
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
                  <thead className="bg-slate-900/60">
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
                  <tbody className="divide-y divide-slate-800/50">
                    {data.map((o) => (
                      <tr key={o.id} className="hover:bg-slate-800/30 transition-colors">
                        <Td mono className="text-white font-semibold">{o.symbol}</Td>
                        <Td><Badge tone={o.side === 'BUY' ? 'positive' : 'negative'}>{o.side}</Badge></Td>
                        <Td align="right" mono className="text-slate-300">{formatNumber(o.quantity, 6)}</Td>
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
                        <Td className="text-slate-500 text-xs">{formatDateTime(o.created_at)}</Td>
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
