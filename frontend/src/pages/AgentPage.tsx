import { useState } from 'react';
import { Bot, Sparkles } from 'lucide-react';

import api from '../lib/api';
import { formatNumber } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { AgentDecision, AIObservability } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  Field,
  PageHeader,
  StatTile,
  TextInput,} from '../components/ui';
import { actionTone } from '../lib/tone';

export default function AgentPage() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [decision, setDecision] = useState<AgentDecision | null>(null);

  const observability = useApi<AIObservability>(
    () => api.get<AIObservability>('/research/ai-observability').then((r) => r.data),
  );

  const analyze = useAction(async () => {
    const res = await api.get<AgentDecision>('/agent/analyze', { params: { symbol } });
    setDecision(res.data);
    observability.reload();
    return res.data;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Trading Agent"
        description="Structured market context in, validated decision out"
      />

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
              sub={
                data.ai_win_rate_pct === null
                  ? 'No settled decisions yet'
                  : `${data.settled_decisions} settled`
              }
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Request Analysis" icon={<Sparkles className="w-4 h-4 text-cyan-400" />}>
          <div className="p-5 space-y-4">
            <Field label="Symbol">
              <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
            </Field>
            <Button onClick={() => void analyze.run()} disabled={analyze.pending}>
              {analyze.pending ? 'Analyzing…' : 'Analyze'}
            </Button>
            {analyze.error && <div className="text-xs text-red-400">{analyze.error}</div>}
            <p className="text-xs text-slate-600 leading-relaxed">
              Context is built from stored candles, indicators, funding, open interest and your open
              positions. Every decision is re-checked against backend arithmetic; one that fails
              validation comes back as WAIT.
            </p>
          </div>
        </Card>

        <Card title="Latest Decision">
          {decision ? (
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <Badge tone={actionTone(decision.action)}>{decision.action}</Badge>
                <span className="text-xs font-mono text-slate-400">
                  confidence {(decision.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-slate-300 leading-relaxed">{decision.reasoning}</p>
              <div className="grid grid-cols-2 gap-3 text-xs font-mono pt-3 border-t border-slate-800">
                <div>
                  <div className="text-slate-600">Entry</div>
                  <div className="text-white">{decision.entry_price ? formatNumber(decision.entry_price) : '—'}</div>
                </div>
                <div>
                  <div className="text-slate-600">Risk : Reward</div>
                  <div className="text-white">{decision.risk_reward_ratio ? decision.risk_reward_ratio.toFixed(2) : '—'}</div>
                </div>
                <div>
                  <div className="text-slate-600">Stop loss</div>
                  <div className="text-red-400">{decision.stop_loss ? formatNumber(decision.stop_loss) : '—'}</div>
                </div>
                <div>
                  <div className="text-slate-600">Take profit</div>
                  <div className="text-emerald-400">{decision.take_profit ? formatNumber(decision.take_profit) : '—'}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-5 text-sm text-slate-500">Run an analysis to see a decision.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
