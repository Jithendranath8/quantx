import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react';

import api from '../lib/api';
import { formatPercent, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { RiskConfig, RiskState } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  PageHeader,
  StatTile,
  TableWrap,
  Td,
  Th,
} from '../components/ui';

const LABELS: Record<keyof RiskConfig, string> = {
  max_risk_per_trade_pct: 'Max risk per trade',
  max_daily_loss_pct: 'Max daily loss',
  max_leverage: 'Max leverage',
  max_portfolio_exposure_pct: 'Max portfolio exposure',
  max_concurrent_trades: 'Max concurrent trades',
  cooldown_period_minutes: 'Cooldown period',
  circuit_breaker_active: 'Circuit breaker',
};

function renderValue(key: keyof RiskConfig, value: number | boolean): string {
  if (typeof value === 'boolean') return value ? 'ACTIVE' : 'inactive';
  if (key.endsWith('_pct')) return formatPercent(value * 100);
  if (key === 'max_leverage') return `${value}x`;
  if (key === 'cooldown_period_minutes') return `${value} min`;
  return String(value);
}

export default function RiskPage() {
  const config = useApi<RiskConfig>(() => api.get<RiskConfig>('/risk/config').then((r) => r.data));
  const state = useApi<RiskState>(() => api.get<RiskState>('/risk/state').then((r) => r.data));

  const toggle = useAction(async (active: boolean) => {
    await api.post('/risk/circuit-breaker/toggle', null, {
      params: { active, reason: active ? 'MANUAL_UI_HALT' : undefined },
    });
    config.reload();
    state.reload();
  });

  const halted = state.data?.circuit_breaker_active ?? false;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Risk Engine"
        description="Hard limits that AI signals cannot override"
        actions={
          <Button
            variant={halted ? 'primary' : 'danger'}
            onClick={() => void toggle.run(!halted)}
            disabled={toggle.pending || state.loading}
          >
            {halted ? 'Resume trading' : 'Halt trading'}
          </Button>
        }
      />

      {toggle.error && <div className="text-xs text-red-400">{toggle.error}</div>}

      <AsyncSection state={state}>
        {(data) => (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile
              label="Circuit Breaker"
              value={data.circuit_breaker_active ? 'HALTED' : 'ACTIVE'}
              sub={data.circuit_breaker_reason ?? 'Trading permitted'}
              tone={data.circuit_breaker_active ? 'negative' : 'positive'}
              icon={data.circuit_breaker_active ? <ShieldAlert className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
            />
            <StatTile label="Daily Loss" value={formatUsd(data.daily_loss_usd)} />
            <StatTile label="Peak Portfolio" value={formatUsd(data.peak_portfolio_value)} />
            <StatTile
              label="Current Drawdown"
              value={formatPercent(data.current_drawdown_pct)}
              tone={data.current_drawdown_pct > 10 ? 'warning' : 'neutral'}
            />
          </div>
        )}
      </AsyncSection>

      <Card title="Active Limits" icon={<Shield className="w-4 h-4 text-cyan-400" />}>
        <AsyncSection state={config}>
          {(data) => (
            <TableWrap>
              <table className="w-full">
                <thead className="bg-slate-900/60">
                  <tr>
                    <Th>Rule</Th>
                    <Th align="right">Value</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {(Object.keys(LABELS) as (keyof RiskConfig)[]).map((key) => (
                    <tr key={key} className="hover:bg-slate-800/30 transition-colors">
                      <Td className="text-slate-300">{LABELS[key]}</Td>
                      <Td align="right" mono className="text-white">
                        {key === 'circuit_breaker_active' ? (
                          <Badge tone={data[key] ? 'negative' : 'positive'}>
                            {renderValue(key, data[key])}
                          </Badge>
                        ) : (
                          renderValue(key, data[key])
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </AsyncSection>
      </Card>

      <p className="text-xs text-slate-600">
        The circuit breaker is stored per user in the database, so a halt applies to every worker
        process and survives a restart.
      </p>
    </div>
  );
}
