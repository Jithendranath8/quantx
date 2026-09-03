import { useState } from 'react';
import { Cpu, Play } from 'lucide-react';

import api from '../lib/api';
import { formatNumber } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { Signal, StrategyMeta } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  TextInput,} from '../components/ui';
import { actionTone } from '../lib/tone';

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];

export default function StrategiesPage() {
  const strategies = useApi<StrategyMeta[]>(
    () => api.get<StrategyMeta[]>('/strategies').then((r) => r.data),
  );

  const [strategyName, setStrategyName] = useState('ema_crossover');
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [signal, setSignal] = useState<Signal | null>(null);

  const evaluate = useAction(async () => {
    const res = await api.get<Signal>('/strategies/evaluate', {
      params: { strategy_name: strategyName, symbol, timeframe, limit: 200 },
    });
    setSignal(res.data);
    return res.data;
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Strategy Engine" description="Registered strategies and live evaluation" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Registered Strategies" icon={<Cpu className="w-4 h-4 text-cyan-400" />}>
          <AsyncSection state={strategies} emptyWhen={(d) => d.length === 0} emptyMessage="No strategies registered">
            {(data) => (
              <div className="divide-y divide-slate-800/50">
                {data.map((s) => (
                  <button
                    key={s.name}
                    type="button"
                    onClick={() => setStrategyName(s.name)}
                    className={`w-full px-5 py-3.5 text-left transition-colors ${
                      s.name === strategyName ? 'bg-slate-800/50' : 'hover:bg-slate-800/30'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-mono font-semibold text-white">{s.name}</span>
                      {s.name === strategyName && <Badge tone="info">selected</Badge>}
                    </div>
                    <p className="text-xs text-slate-500">{s.description}</p>
                  </button>
                ))}
              </div>
            )}
          </AsyncSection>
        </Card>

        <Card title="Evaluate">
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Symbol">
                <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
              </Field>
              <Field label="Timeframe">
                <Select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                  {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
                </Select>
              </Field>
            </div>

            <Button onClick={() => void evaluate.run()} disabled={evaluate.pending}>
              <span className="flex items-center gap-1.5">
                <Play className="w-3 h-3" /> {evaluate.pending ? 'Evaluating…' : 'Run evaluation'}
              </span>
            </Button>

            {evaluate.error && <div className="text-xs text-red-400">{evaluate.error}</div>}

            {signal && (
              <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500 uppercase tracking-wider">Signal</span>
                  <Badge tone={actionTone(signal.action)}>{signal.action}</Badge>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-slate-800 rounded-full h-1.5">
                    <div
                      className="h-1.5 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500"
                      style={{ width: `${signal.confidence * 100}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    {(signal.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">{signal.reasoning}</p>
                {signal.entry_price !== null && (
                  <div className="grid grid-cols-3 gap-2 text-xs font-mono pt-2 border-t border-slate-800">
                    <div>
                      <div className="text-slate-600">Entry</div>
                      <div className="text-white">{formatNumber(signal.entry_price)}</div>
                    </div>
                    <div>
                      <div className="text-slate-600">Stop</div>
                      <div className="text-red-400">{signal.stop_loss ? formatNumber(signal.stop_loss) : '—'}</div>
                    </div>
                    <div>
                      <div className="text-slate-600">Target</div>
                      <div className="text-emerald-400">{signal.take_profit ? formatNumber(signal.take_profit) : '—'}</div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
