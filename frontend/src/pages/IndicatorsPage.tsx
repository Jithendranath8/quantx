import { useState } from 'react';
import { LineChart } from 'lucide-react';

import api from '../lib/api';
import { formatNumber } from '../lib/format';
import { useApi } from '../lib/useApi';
import { AsyncSection, Card, Field, PageHeader, TextInput } from '../components/ui';

interface IndicatorResponse {
  symbol: string;
  indicators: Record<string, Record<string, number | string | null>>;
}

const AVAILABLE = ['1m', '5m', '15m', '1h', '4h', '1d'];
// The backend caps the number of timeframes per request, so the UI cannot
// build a request it will reject.
const MAX_TIMEFRAMES = 8;

const HIGHLIGHT = ['close', 'rsi_14', 'ema_9', 'ema_21', 'ema_50', 'ema_200', 'macd_histogram', 'atr_14', 'adx_14'];

export default function IndicatorsPage() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [selected, setSelected] = useState<string[]>(['15m', '1h', '4h']);

  const indicators = useApi<IndicatorResponse>(
    () =>
      api
        .get<IndicatorResponse>(`/indicators/${symbol}`, {
          params: { timeframes: selected.join(','), limit: 200 },
        })
        .then((r) => r.data),
    [symbol, selected.join(',')],
    { enabled: selected.length > 0 },
  );

  const toggle = (tf: string) => {
    setSelected((current) =>
      current.includes(tf)
        ? current.filter((t) => t !== tf)
        : current.length >= MAX_TIMEFRAMES
          ? current
          : [...current, tf],
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Indicator Engine" description="Multi-timeframe technical analysis" />

      <div className="flex flex-wrap items-end gap-4">
        <Field label="Symbol">
          <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </Field>
        <Field label={`Timeframes (max ${MAX_TIMEFRAMES})`}>
          <div className="flex flex-wrap gap-1.5">
            {AVAILABLE.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => toggle(tf)}
                className={`px-2.5 py-1 rounded-lg border text-xs font-mono transition-colors ${
                  selected.includes(tf)
                    ? 'bg-cyan-600/20 border-cyan-500/40 text-cyan-300'
                    : 'bg-slate-900 border-slate-800 text-slate-500 hover:border-slate-700'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </Field>
      </div>

      <Card title={`Indicators · ${symbol}`} icon={<LineChart className="w-4 h-4 text-cyan-400" />}>
        <AsyncSection
          state={indicators}
          emptyWhen={(d) => Object.values(d.indicators).every((v) => Object.keys(v).length === 0)}
          emptyMessage="No indicator data"
          emptyHint="No candles are stored for this symbol and timeframe yet."
        >
          {(data) => (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-px bg-slate-800">
              {Object.entries(data.indicators).map(([tf, values]) => (
                <div key={tf} className="bg-slate-900/50 p-5">
                  <div className="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-3">{tf}</div>
                  {Object.keys(values).length === 0 ? (
                    <p className="text-xs text-slate-600">No candles stored</p>
                  ) : (
                    <div className="space-y-1.5">
                      {HIGHLIGHT.filter((k) => k in values).map((key) => (
                        <div key={key} className="flex justify-between text-xs">
                          <span className="text-slate-500 font-mono">{key}</span>
                          <span className="text-white font-mono">
                            {typeof values[key] === 'number'
                              ? formatNumber(values[key] as number, 4)
                              : String(values[key] ?? '—')}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </AsyncSection>
      </Card>

      {selected.length === 0 && (
        <p className="text-xs text-amber-400">Select at least one timeframe.</p>
      )}
    </div>
  );
}
