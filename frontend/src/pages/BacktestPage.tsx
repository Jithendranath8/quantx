import { useState } from 'react';
import { History, Play } from 'lucide-react';

import api from '../lib/api';
import { formatNumber, formatPercent, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { BacktestResult, StrategyMeta } from '../lib/types';
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

/** Minimal inline equity sparkline; no charting dependency needed. */
function EquityCurve({ points }: { points: { equity: number }[] }) {
  if (points.length < 2) return null;
  const values = points.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = 100 / (values.length - 1);
  const path = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(3)} ${(40 - ((v - min) / range) * 40).toFixed(3)}`)
    .join(' ');

  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-32" role="img" aria-label="Equity curve">
      <path d={path} fill="none" stroke="#06b6d4" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
    </svg>
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
      <PageHeader title="Backtesting" description="Event-driven simulation over stored candles" />

      <Card title="Configuration" icon={<History className="w-4 h-4 text-cyan-400" />}>
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
              {(strategies.data ?? []).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
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
        {run.error && <div className="px-5 pb-5 text-xs text-red-400">{run.error}</div>}
      </Card>

      {result && (
        <>
          {result.equity_curve.length === 0 && (
            <div className="text-xs text-amber-400">
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
              <EquityCurve points={result.equity_curve} />
              <div className="flex justify-between text-xs font-mono text-slate-500 mt-2">
                <span>{formatUsd(result.initial_capital)}</span>
                <span className={result.final_equity >= result.initial_capital ? 'text-emerald-400' : 'text-red-400'}>
                  {formatUsd(result.final_equity)}
                </span>
              </div>
            </div>
          </Card>

          <Card title={`Trades (${result.trades.length})`}>
            {result.trades.length === 0 ? (
              <div className="p-5 text-sm text-slate-500">The strategy produced no trades on this data.</div>
            ) : (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-slate-900/60">
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
                  <tbody className="divide-y divide-slate-800/50">
                    {result.trades.slice(0, 50).map((t, i) => (
                      <tr key={i} className="hover:bg-slate-800/30 transition-colors">
                        <Td className="text-slate-400 text-xs">{String(t.entry_time)}</Td>
                        <Td className="text-slate-400 text-xs">{String(t.exit_time)}</Td>
                        <Td><Badge tone={t.side === 'LONG' ? 'positive' : 'negative'}>{String(t.side)}</Badge></Td>
                        <Td align="right" mono className="text-slate-300">{formatNumber(Number(t.entry_price))}</Td>
                        <Td align="right" mono className="text-slate-300">{formatNumber(Number(t.exit_price))}</Td>
                        <Td align="right" mono className={Number(t.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {formatUsd(Number(t.pnl))}
                        </Td>
                        <Td className="text-slate-500 text-xs">{String(t.reason)}</Td>
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
