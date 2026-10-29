import { useState } from 'react';
import { Layers, Play } from 'lucide-react';

import api from '../lib/api';
import { formatNumber, formatUsd } from '../lib/format';
import { useAction } from '../lib/useApi';
import type { MarketMakingResult, QuotePoint } from '../lib/types';
import {
  Badge,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  StatTile,
  TableWrap,
  Td,
  TextInput,
  Th,
} from '../components/ui';

const TIMEFRAMES = ['1m', '5m', '15m', '1h'];

/** Map a numeric series to an SVG polyline path in a 100x40 viewBox. */
function linePath(values: number[], min: number, max: number): string {
  const range = max - min || 1;
  const step = 100 / (values.length - 1 || 1);
  return values
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(3)} ${(40 - ((v - min) / range) * 40).toFixed(3)}`)
    .join(' ');
}

/** Single-series line chart (PnL, etc.). */
function Sparkline({ values, color, label }: { values: number[]; color: string; label: string }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-32" role="img" aria-label={label}>
      <path d={linePath(values, min, max)} fill="none" stroke={color} strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Inventory path with a zero baseline so long/short is read at a glance. */
function InventoryChart({ series }: { series: QuotePoint[] }) {
  if (series.length < 2) return null;
  const values = series.map((p) => p.inventory);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const range = max - min || 1;
  const zeroY = (40 - ((0 - min) / range) * 40).toFixed(3);
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-32" role="img" aria-label="Inventory over time">
      <line x1="0" y1={zeroY} x2="100" y2={zeroY} stroke="#475569" strokeWidth="0.3" strokeDasharray="1 1" vectorEffect="non-scaling-stroke" />
      <path d={linePath(values, min, max)} fill="none" stroke="#a78bfa" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Mid price with the bid/ask band drawn around it — shows quotes tracking price. */
function QuoteBand({ series }: { series: QuotePoint[] }) {
  if (series.length < 2) return null;
  const all = series.flatMap((p) => [p.bid, p.ask, p.mid]);
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const step = 100 / (series.length - 1);
  const y = (v: number) => (40 - ((v - min) / range) * 40).toFixed(3);
  const asks = series.map((p, i) => `${(i * step).toFixed(3)},${y(p.ask)}`);
  const bidsRev = series.map((p, i) => `${(i * step).toFixed(3)},${y(p.bid)}`).reverse();
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-40" role="img" aria-label="Quotes around mid price">
      <polygon points={[...asks, ...bidsRev].join(' ')} fill="#ff7a1a" opacity="0.12" />
      <path d={linePath(series.map((p) => p.mid), min, max)} fill="none" stroke="#e2e8f0" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function MarketMakingPage() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1m');
  const [gamma, setGamma] = useState('0.3');
  const [k, setK] = useState('1.5');
  const [orderSize, setOrderSize] = useState('0.01');
  const [maxInventory, setMaxInventory] = useState('1.0');
  const [result, setResult] = useState<MarketMakingResult | null>(null);

  const run = useAction(async () => {
    const res = await api.post<MarketMakingResult>('/market-making/simulate', {
      symbol,
      timeframe,
      gamma: Number(gamma),
      k: Number(k),
      order_size: Number(orderSize),
      max_inventory: Number(maxInventory),
    });
    setResult(res.data);
    return res.data;
  });

  const m = result?.metrics;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Market Making"
        description="Avellaneda–Stoikov inventory-aware quoting, simulated over stored candles"
      />

      <Card title="Configuration" icon={<Layers className="w-4 h-4 text-brand-400" />}>
        <div className="p-5 flex flex-wrap items-end gap-4">
          <Field label="Symbol">
            <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          </Field>
          <Field label="Timeframe">
            <Select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
            </Select>
          </Field>
          <Field label="γ (risk aversion)">
            <TextInput type="number" step="0.1" min="0.01" value={gamma} onChange={(e) => setGamma(e.target.value)} />
          </Field>
          <Field label="k (liquidity)">
            <TextInput type="number" step="0.1" min="0.1" value={k} onChange={(e) => setK(e.target.value)} />
          </Field>
          <Field label="Order size">
            <TextInput type="number" step="0.01" min="0.001" value={orderSize} onChange={(e) => setOrderSize(e.target.value)} />
          </Field>
          <Field label="Max inventory">
            <TextInput type="number" step="0.1" min="0.1" value={maxInventory} onChange={(e) => setMaxInventory(e.target.value)} />
          </Field>
          <Button onClick={() => void run.run()} disabled={run.pending}>
            <span className="flex items-center gap-1.5">
              <Play className="w-3 h-3" /> {run.pending ? 'Simulating…' : 'Run simulation'}
            </span>
          </Button>
        </div>
        {run.error && <div className="px-5 pb-5 text-xs text-red-400">{run.error}</div>}
      </Card>

      {result && m && (
        <>
          {result.series.length === 0 && (
            <div className="text-xs text-yellow-400">
              <Badge tone="warning">No data</Badge> No candles are stored for {result.symbol} {result.timeframe}.
            </div>
          )}

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile
              label="Total P&L"
              value={formatUsd(m.total_pnl)}
              sub={`${m.num_fills} fills`}
              tone={m.total_pnl >= 0 ? 'positive' : 'negative'}
            />
            <StatTile label="Spread Capture" value={formatUsd(m.spread_pnl)} sub={`${m.avg_spread_bps} bps avg`} tone="positive" />
            <StatTile
              label="Inventory P&L"
              value={formatUsd(m.inventory_pnl)}
              sub="holding risk"
              tone={m.inventory_pnl >= 0 ? 'positive' : 'negative'}
            />
            <StatTile label="Sharpe" value={formatNumber(m.sharpe_ratio)} sub={`fill ratio ${(m.fill_ratio * 100).toFixed(0)}%`} />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile label="Buys / Sells" value={`${m.num_buys} / ${m.num_sells}`} />
            <StatTile label="Max Inventory" value={formatNumber(m.max_inventory)} sub="base units" />
            <StatTile label="Final Inventory" value={formatNumber(m.final_inventory)} sub="base units" />
            <StatTile label="Fees Paid" value={formatUsd(m.fees_paid)} />
          </div>

          <Card title="Quotes vs Mid Price">
            <div className="p-5">
              <QuoteBand series={result.series} />
              <p className="text-xs text-zinc-500 mt-2">
                The shaded band is the maker's live bid/ask; it skews away from the mid as inventory builds.
              </p>
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Cumulative P&L">
              <div className="p-5">
                <Sparkline values={result.series.map((p) => p.pnl)} color="#ff7a1a" label="Cumulative PnL" />
                <div className="flex justify-between text-xs font-mono text-zinc-500 mt-2">
                  <span>$0</span>
                  <span className={m.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{formatUsd(m.total_pnl)}</span>
                </div>
              </div>
            </Card>
            <Card title="Inventory">
              <div className="p-5">
                <InventoryChart series={result.series} />
                <div className="flex justify-between text-xs font-mono text-zinc-500 mt-2">
                  <span>cap ±{result.params.max_inventory}</span>
                  <span>final {formatNumber(m.final_inventory)}</span>
                </div>
              </div>
            </Card>
          </div>

          <Card title={`Recent Fills (${result.fills.length})`}>
            {result.fills.length === 0 ? (
              <div className="p-5 text-sm text-zinc-500">No quotes were filled on this data.</div>
            ) : (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-zinc-900/60">
                    <tr>
                      <Th>Time</Th>
                      <Th>Side</Th>
                      <Th align="right">Price</Th>
                      <Th align="right">Size</Th>
                      <Th align="right">Edge vs mid</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50">
                    {result.fills.slice(-50).reverse().map((f, i) => (
                      <tr key={i} className="hover:bg-zinc-800/30 transition-colors">
                        <Td className="text-zinc-400 text-xs">{f.timestamp}</Td>
                        <Td><Badge tone={f.side === 'BUY' ? 'positive' : 'negative'}>{f.side}</Badge></Td>
                        <Td align="right" mono className="text-zinc-300">{formatNumber(f.price)}</Td>
                        <Td align="right" mono className="text-zinc-400">{formatNumber(f.size)}</Td>
                        <Td align="right" mono className="text-emerald-400">{formatUsd(f.edge)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
