import { useState } from 'react';
import { FlaskConical, Play } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime, formatNumber, formatPercent } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type {
  BiasCheckReport,
  ExperimentRecord,
  MonteCarloSummary,
  OptimizationResult,
  StrategyMeta,
  WalkForwardResult,
} from '../lib/types';
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

type Tool = 'walk-forward' | 'optimize' | 'monte-carlo' | 'bias-check';

export default function ExperimentsPage() {
  const strategies = useApi<StrategyMeta[]>(
    () => api.get<StrategyMeta[]>('/strategies').then((r) => r.data),
  );
  const experiments = useApi<ExperimentRecord[]>(
    () => api.get<ExperimentRecord[]>('/research/experiments').then((r) => r.data),
  );

  const [tool, setTool] = useState<Tool>('walk-forward');
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [strategyName, setStrategyName] = useState('ema_crossover');
  const [output, setOutput] = useState<unknown>(null);

  const run = useAction(async () => {
    const params = { strategy_name: strategyName, symbol, timeframe };
    const res = await api.post(`/research/${tool}`, null, { params });
    setOutput(res.data);
    return res.data;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Research Suite"
        description="Walk-forward, parameter search, Monte Carlo, and causality auditing"
      />

      <Card title="Run a Study" icon={<FlaskConical className="w-4 h-4 text-brand-400" />}>
        <div className="p-5 flex flex-wrap items-end gap-4">
          <Field label="Tool">
            <Select value={tool} onChange={(e) => { setTool(e.target.value as Tool); setOutput(null); }}>
              <option value="walk-forward">Walk-forward</option>
              <option value="optimize">Parameter optimization</option>
              <option value="monte-carlo">Monte Carlo</option>
              <option value="bias-check">Look-ahead bias audit</option>
            </Select>
          </Field>
          <Field label="Strategy">
            <Select value={strategyName} onChange={(e) => setStrategyName(e.target.value)}>
              {(strategies.data ?? []).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Symbol">
            <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          </Field>
          <Field label="Timeframe">
            <Select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {['15m', '1h', '4h', '1d'].map((tf) => <option key={tf} value={tf}>{tf}</option>)}
            </Select>
          </Field>
          <Button onClick={() => void run.run()} disabled={run.pending}>
            <span className="flex items-center gap-1.5">
              <Play className="w-3 h-3" /> {run.pending ? 'Running…' : 'Run'}
            </span>
          </Button>
        </div>
        {run.error && <div className="px-5 pb-5 text-xs text-red-400">{run.error}</div>}
        <p className="px-5 pb-5 text-xs text-zinc-600">
          Every study runs real backtests over your stored candles. Results depend on the data you
          have ingested for this symbol and timeframe.
        </p>
      </Card>

      {output !== null && tool === 'walk-forward' && <WalkForward result={output as WalkForwardResult} />}
      {output !== null && tool === 'optimize' && <Optimization result={output as OptimizationResult} />}
      {output !== null && tool === 'monte-carlo' && <MonteCarlo result={output as MonteCarloSummary} />}
      {output !== null && tool === 'bias-check' && <BiasCheck result={output as BiasCheckReport} />}

      <Card title="Experiment Registry">
        <AsyncSection
          state={experiments}
          emptyWhen={(d) => d.length === 0}
          emptyMessage="No experiments registered"
          emptyHint="Studies are recorded here once the registry is wired to your research runs."
        >
          {(data) => (
            <TableWrap>
              <table className="w-full">
                <thead className="bg-zinc-900/60">
                  <tr>
                    <Th>ID</Th>
                    <Th>Strategy</Th>
                    <Th>Symbol</Th>
                    <Th>Timeframe</Th>
                    <Th>Created</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {data.map((e) => (
                    <tr key={e.experiment_id} className="hover:bg-zinc-800/30 transition-colors">
                      <Td mono className="text-brand-400 text-xs">{e.experiment_id}</Td>
                      <Td className="text-white">{e.strategy_name}</Td>
                      <Td mono className="text-zinc-300">{e.symbol}</Td>
                      <Td mono className="text-zinc-400">{e.timeframe}</Td>
                      <Td className="text-zinc-500 text-xs">{formatDateTime(e.created_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </AsyncSection>
      </Card>
    </div>
  );
}

function WalkForward({ result }: { result: WalkForwardResult }) {
  return (
    <Card
      title="Walk-Forward Result"
      actions={
        result.overfitting_warning ? <Badge tone="negative">overfitting risk</Badge> : <Badge tone="positive">consistent</Badge>
      }
    >
      <div className="p-5 space-y-3">
        <p className="text-sm text-zinc-400">{result.message}</p>
        <div className="flex gap-6 text-xs font-mono">
          <span className="text-zinc-500">IS Sharpe <span className="text-white">{formatNumber(result.avg_in_sample_sharpe)}</span></span>
          <span className="text-zinc-500">OOS Sharpe <span className="text-white">{formatNumber(result.avg_out_of_sample_sharpe)}</span></span>
          <span className="text-zinc-500">Efficiency <span className="text-white">{formatNumber(result.efficiency_ratio)}</span></span>
        </div>
      </div>
      {result.windows.length > 0 && (
        <TableWrap>
          <table className="w-full">
            <thead className="bg-zinc-900/60">
              <tr>
                <Th>Window</Th>
                <Th align="right">Train bars</Th>
                <Th align="right">Test bars</Th>
                <Th align="right">IS Sharpe</Th>
                <Th align="right">OOS Sharpe</Th>
                <Th align="right">OOS return</Th>
                <Th align="right">OOS trades</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {result.windows.map((w) => (
                <tr key={w.window_id} className="hover:bg-zinc-800/30 transition-colors">
                  <Td mono className="text-white">#{w.window_id}</Td>
                  <Td align="right" mono className="text-zinc-400">{w.train_bars}</Td>
                  <Td align="right" mono className="text-zinc-400">{w.test_bars}</Td>
                  <Td align="right" mono className="text-zinc-300">{formatNumber(w.in_sample_sharpe)}</Td>
                  <Td align="right" mono className="text-white">{formatNumber(w.out_of_sample_sharpe)}</Td>
                  <Td align="right" mono className={w.out_of_sample_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {formatPercent(w.out_of_sample_return_pct)}
                  </Td>
                  <Td align="right" mono className="text-zinc-400">{w.out_of_sample_trades}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </Card>
  );
}

function Optimization({ result }: { result: OptimizationResult }) {
  return (
    <Card
      title="Optimization Result"
      actions={result.overfitting_warning ? <Badge tone="negative">overfitting risk</Badge> : null}
    >
      <div className="p-5 space-y-2">
        <p className="text-sm text-zinc-400">{result.recommendation}</p>
        <p className="text-xs font-mono text-zinc-600">{result.total_evaluations} parameter sets evaluated</p>
        {result.deflated_sharpe !== null && (
          <p className="text-xs font-mono text-zinc-500">
            PSR {formatNumber(result.probabilistic_sharpe ?? 0)} · DSR {formatNumber(result.deflated_sharpe)}
            {result.probability_of_backtest_overfitting !== null &&
              ` · PBO ${(result.probability_of_backtest_overfitting * 100).toFixed(0)}%`}
          </p>
        )}
      </div>
      {result.top_candidates.length > 0 && (
        <TableWrap>
          <table className="w-full">
            <thead className="bg-zinc-900/60">
              <tr>
                <Th>Parameters</Th>
                <Th align="right">Sharpe</Th>
                <Th align="right">Return</Th>
                <Th align="right">Max DD</Th>
                <Th align="right">Trades</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {result.top_candidates.map((c, i) => (
                <tr key={i} className="hover:bg-zinc-800/30 transition-colors">
                  <Td mono className="text-brand-400 text-xs">{JSON.stringify(c.params)}</Td>
                  <Td align="right" mono className="text-white">{formatNumber(c.sharpe_ratio)}</Td>
                  <Td align="right" mono className={c.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {formatPercent(c.total_return_pct)}
                  </Td>
                  <Td align="right" mono className="text-zinc-400">{formatPercent(c.max_drawdown_pct)}</Td>
                  <Td align="right" mono className="text-zinc-400">{c.total_trades}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </Card>
  );
}

function MonteCarlo({ result }: { result: MonteCarloSummary }) {
  return (
    <Card title="Monte Carlo Result">
      <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        {[
          ['Simulations', result.num_simulations.toLocaleString()],
          ['Trades per path', result.num_trades_per_path],
          ['Mean final equity', formatNumber(result.mean_final_equity)],
          ['Median final equity', formatNumber(result.median_final_equity)],
          ['Probability of ruin', formatPercent(result.probability_of_ruin_pct)],
          ['95% worst drawdown', formatPercent(result.worst_case_drawdown_95_pct)],
          ['Median max drawdown', formatPercent(result.median_max_drawdown_pct)],
          ['Expected losing streak', result.expected_longest_losing_streak],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <div className="text-xs text-zinc-500 uppercase tracking-wider">{label}</div>
            <div className="text-white font-mono mt-1">{value}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function BiasCheck({ result }: { result: BiasCheckReport }) {
  return (
    <Card
      title="Look-Ahead Bias Audit"
      actions={
        result.has_lookahead_bias ? <Badge tone="negative">bias detected</Badge> : <Badge tone="positive">clean</Badge>
      }
    >
      <div className="p-5 space-y-2">
        <p className="text-sm text-zinc-400">{result.message}</p>
        <p className="text-xs font-mono text-zinc-600">
          {result.bars_tested} bars tested · {result.violations_found} violations
        </p>
      </div>
    </Card>
  );
}
