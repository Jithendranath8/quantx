import { useMemo, useState } from 'react';
import { ArrowRight, FlaskConical, History, Play, TrendingDown, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';

import api from '../lib/api';
import { formatDateTime, formatNumber, formatPercent, formatUsd } from '../lib/format';
import { appPath } from '../lib/navigation';
import { useAction, useApi } from '../lib/useApi';
import type { BacktestResult, EquityPoint, StrategyMeta } from '../lib/types';
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

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];

const W = 1000;
const H = 220;

/** Equity over time with a starting-capital baseline; hover to read any point. */
function EquityCurve({ points, initial }: { points: EquityPoint[]; initial: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const geometry = useMemo(() => {
    const values = points.map((p) => p.equity);
    const min = Math.min(initial, ...values);
    const max = Math.max(initial, ...values);
    const range = max - min || 1;
    const x = (i: number) => (i / (points.length - 1)) * W;
    const y = (v: number) => H - ((v - min) / range) * (H - 16) - 8;
    const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
    return { line, area: `${line}L${W},${H}L0,${H}Z`, x, y, baseline: y(initial) };
  }, [points, initial]);

  if (points.length < 2) return null;
  const up = points[points.length - 1].equity >= initial;
  const stroke = up ? '#34d399' : '#f87171';
  const active = hover === null ? null : points[hover];

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-56 w-full cursor-crosshair"
        role="img"
        aria-label={`Equity curve from ${formatUsd(initial)} to ${formatUsd(points[points.length - 1].equity)}`}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left) / r.width) * (points.length - 1));
          setHover(Math.max(0, Math.min(points.length - 1, i)));
        }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="equity-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" x2={W} y1={geometry.baseline} y2={geometry.baseline} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 6" vectorEffect="non-scaling-stroke" />
        <path d={geometry.area} fill="url(#equity-fill)" />
        <path d={geometry.line} fill="none" stroke={stroke} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {hover !== null && (
          <line x1={geometry.x(hover)} x2={geometry.x(hover)} y1="0" y2={H} stroke="rgba(255,255,255,0.25)" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      {active && hover !== null && (
        <div
          className="pointer-events-none absolute top-2 -translate-x-1/2 rounded-lg border border-white/10 bg-ink-900/95 px-3 py-2 text-xs shadow-xl"
          style={{ left: `${Math.min(92, Math.max(8, (hover / (points.length - 1)) * 100))}%` }}
        >
          <p className="text-zinc-500">{formatDateTime(active.timestamp)}</p>
          <p className="font-mono text-sm text-white">{formatUsd(active.equity)}</p>
          <p className="font-mono text-zinc-500">drawdown {formatPercent(active.drawdown_pct)}</p>
        </div>
      )}
    </div>
  );
}

/** A plain-language read of the result, so the numbers have a conclusion. */
function Verdict({ result }: { result: BacktestResult }) {
  const m = result.metrics;
  const profitable = m.total_return_pct > 0;
  const Icon = profitable ? TrendingUp : TrendingDown;
  const headline = profitable
    ? m.sharpe_ratio >= 1
      ? 'Profitable, with returns large relative to their volatility.'
      : 'Profitable, but the returns were noisy for the risk taken.'
    : 'This strategy lost money over the tested period.';
  return (
    <div className={`flex flex-wrap items-center justify-between gap-4 rounded-2xl border px-5 py-4 ${profitable ? 'border-emerald-500/20 bg-emerald-500/[0.04]' : 'border-red-500/25 bg-red-500/[0.05]'}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 w-5 h-5 shrink-0 ${profitable ? 'text-emerald-400' : 'text-red-400'}`} />
        <div>
          <p className="text-sm font-medium text-white">{headline}</p>
          <p className="mt-1 text-xs text-zinc-400">
            {result.strategy_name} on {result.symbol} {result.timeframe}: {m.total_trades} trades, worst peak-to-trough fall{' '}
            {formatPercent(m.max_drawdown_pct)}. One backtest can be luck — a single good run is not evidence.
          </p>
        </div>
      </div>
      <Link
        to={appPath('experiments')}
        className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-zinc-300 ring-1 ring-inset ring-white/10 hover:text-white cursor-pointer"
      >
        <FlaskConical className="w-3.5 h-3.5" /> Stress-test it <ArrowRight className="w-3 h-3" />
      </Link>
    </div>
  );
}

export default function BacktestPage() {
  const strategies = useApi<StrategyMeta[]>(
    () => api.get<StrategyMeta[]>('/strategies').then((r) => r.data),
  );

  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [strategyName, setStrategyName] = useState('ema_crossover');
  const [capital, setCapital] = useState('10000');
  const [result, setResult] = useState<BacktestResult | null>(null);
  const selectedStrategy = strategies.data?.find((s) => s.name === strategyName);

  const run = useAction(async () => {
    const res = await api.post<BacktestResult>('/backtest/run', {
      symbol,
      timeframe,
      strategy_name: strategyName,
      initial_capital: Number(capital),
    });
    setResult(res.data);
    return res.data;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Backtesting"
        description="Replay a strategy bar by bar over stored candles, with fees and stops, to see what it would have done — before any money or paper account is involved."
      />

      <Card title="Configuration" icon={<History className="w-4 h-4 text-brand-400" />}>
        <div className="p-5 flex flex-wrap items-end gap-4">
          <Field label="Symbol">
            <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          </Field>
          <Field label="Timeframe">
            <Select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
            </Select>
          </Field>
          <Field label="Strategy">
            <Select value={strategyName} onChange={(e) => setStrategyName(e.target.value)}>
              {(strategies.data ?? []).map((s) => <option key={s.name} value={s.name}>{s.name.replace(/_/g, ' ')}</option>)}
            </Select>
          </Field>
          <Field label="Initial capital">
            <TextInput type="number" min="100" value={capital} onChange={(e) => setCapital(e.target.value)} />
          </Field>
          <Button onClick={() => void run.run()} disabled={run.pending}>
            <span className="flex items-center gap-1.5">
              <Play className="w-3 h-3" /> {run.pending ? 'Running…' : 'Run backtest'}
            </span>
          </Button>
        </div>
        {selectedStrategy?.description && (
          <p className="px-5 pb-5 -mt-1 text-xs text-zinc-500">{selectedStrategy.description}</p>
        )}
        {run.error && <div className="px-5 pb-5 text-xs text-red-400">{run.error}</div>}
      </Card>

      {!result && !run.pending && (
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            ['Total return & Sharpe', 'How much it made, and how much it made per unit of volatility. Sharpe above 1 is respectable.'],
            ['Max drawdown', 'The deepest fall from a high point. Ask yourself whether you would really have held through it.'],
            ['Every trade', 'Entry, exit, side and why it closed — take profit, stop loss or the strategy’s own signal.'],
          ].map(([title, body]) => (
            <div key={title} className="rounded-2xl border border-dashed border-white/10 p-5">
              <p className="text-sm text-white">{title}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">{body}</p>
            </div>
          ))}
        </div>
      )}

      {result && (
        <>
          <Verdict result={result} />
          {result.equity_curve.length === 0 && (
            <div className="text-xs text-yellow-400">
              <Badge tone="warning">No data</Badge> No candles are stored for {result.symbol} {result.timeframe}.
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile
              label="Total Return"
              value={formatPercent(result.metrics.total_return_pct)}
              sub={formatUsd(result.metrics.net_profit_usd)}
              tone={result.metrics.total_return_pct >= 0 ? 'positive' : 'negative'}
            />
            <StatTile label="Sharpe" value={formatNumber(result.metrics.sharpe_ratio)} sub={`Sortino ${formatNumber(result.metrics.sortino_ratio)}`} />
            <StatTile
              label="Max Drawdown"
              value={formatPercent(result.metrics.max_drawdown_pct)}
              tone={result.metrics.max_drawdown_pct > 20 ? 'negative' : 'neutral'}
            />
            <StatTile
              label="Win Rate"
              value={formatPercent(result.metrics.win_rate_pct)}
              sub={`${result.metrics.total_trades} trades`}
            />
          </div>

          <Card title="Equity Curve">
            <div className="p-5">
              <EquityCurve points={result.equity_curve} initial={result.initial_capital} />
              <div className="flex justify-between text-xs font-mono text-zinc-500 mt-2">
                <span>{formatUsd(result.initial_capital)}</span>
                <span className={result.final_equity >= result.initial_capital ? 'text-emerald-400' : 'text-red-400'}>
                  {formatUsd(result.final_equity)}
                </span>
              </div>
            </div>
          </Card>

          <Card title={`Trades (${result.trades.length}${result.trades.length > 50 ? ', first 50 shown' : ''})`}>
            {result.trades.length === 0 ? (
              <div className="p-5 text-sm text-zinc-500">The strategy produced no trades on this data.</div>
            ) : (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-zinc-900/60">
                    <tr>
                      <Th>Entry</Th>
                      <Th>Exit</Th>
                      <Th>Side</Th>
                      <Th align="right">Entry price</Th>
                      <Th align="right">Exit price</Th>
                      <Th align="right">PnL</Th>
                      <Th>Reason</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50">
                    {result.trades.slice(0, 50).map((t, i) => (
                      <tr key={i} className="hover:bg-zinc-800/30 transition-colors">
                        <Td className="text-zinc-400 text-xs">{formatDateTime(String(t.entry_time))}</Td>
                        <Td className="text-zinc-400 text-xs">{formatDateTime(String(t.exit_time))}</Td>
                        <Td><Badge tone={t.side === 'LONG' ? 'positive' : 'negative'}>{String(t.side)}</Badge></Td>
                        <Td align="right" mono className="text-zinc-300">{formatNumber(Number(t.entry_price))}</Td>
                        <Td align="right" mono className="text-zinc-300">{formatNumber(Number(t.exit_price))}</Td>
                        <Td align="right" mono className={Number(t.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {formatUsd(Number(t.pnl))}
                        </Td>
                        <Td className="text-zinc-500 text-xs">{String(t.reason)}</Td>
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
