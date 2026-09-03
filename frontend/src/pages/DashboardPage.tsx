import { Activity, BarChart3, Bot, Layers, TrendingUp, Wallet } from 'lucide-react';

import api from '../lib/api';
import { formatPercent, formatUsd } from '../lib/format';
import { useApi } from '../lib/useApi';
import type { PortfolioSummary, SystemHealth } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Card,
  LoadingState,
  PageHeader,
  StatTile,
  Td,
  TableWrap,
  Th,
} from '../components/ui';

export default function DashboardPage() {
  const portfolio = useApi<PortfolioSummary>(
    () => api.get<PortfolioSummary>('/analytics/portfolio').then((r) => r.data),
  );
  const health = useApi<SystemHealth>(
    () => api.get<SystemHealth>('/health/system').then((r) => r.data),
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" description="Overview of your portfolio and platform health" />

      {portfolio.loading && portfolio.data === null ? (
        <LoadingState label="Loading portfolio…" />
      ) : portfolio.error ? (
        <Card>
          <AsyncSection state={portfolio}>{() => null}</AsyncSection>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatTile
            label="Total Equity"
            value={formatUsd(portfolio.data?.total_equity_usd)}
            sub={`Cash ${formatUsd(portfolio.data?.cash_balance_usd)}`}
            icon={<Wallet className="w-4 h-4" />}
          />
          <StatTile
            label="Unrealized PnL"
            value={formatUsd(portfolio.data?.unrealized_pnl_usd)}
            sub={`Realized ${formatUsd(portfolio.data?.realized_pnl_usd)}`}
            tone={(portfolio.data?.unrealized_pnl_usd ?? 0) >= 0 ? 'positive' : 'negative'}
            icon={<TrendingUp className="w-4 h-4" />}
          />
          <StatTile
            label="Win Rate"
            value={formatPercent(portfolio.data?.win_rate_pct)}
            // Null until a position has actually closed, rather than a
            // plausible-looking constant.
            sub={
              portfolio.data?.win_rate_pct === null
                ? 'No closed trades yet'
                : `${portfolio.data?.closed_trades_count ?? 0} closed trades`
            }
            icon={<BarChart3 className="w-4 h-4" />}
          />
          <StatTile
            label="Open Positions"
            value={portfolio.data?.open_positions_count ?? 0}
            sub={`${portfolio.data?.total_trades_count ?? 0} orders total`}
            icon={<Layers className="w-4 h-4" />}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Asset Allocation" icon={<Bot className="w-4 h-4 text-cyan-400" />}>
          <AsyncSection
            state={portfolio}
            emptyWhen={(d) => d.allocations.length === 0}
            emptyMessage="No allocations yet"
            emptyHint="Create a paper trading account and place an order to see your allocation."
          >
            {(data) => (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-slate-900/60">
                    <tr>
                      <Th>Asset</Th>
                      <Th align="right">Value</Th>
                      <Th align="right">Weight</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {data.allocations.map((a) => (
                      <tr key={a.symbol} className="hover:bg-slate-800/30 transition-colors">
                        <Td mono className="text-white">{a.symbol}</Td>
                        <Td align="right" mono className="text-slate-300">{formatUsd(a.value_usd)}</Td>
                        <Td align="right" mono className="text-slate-400">{formatPercent(a.allocation_pct)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </AsyncSection>
        </Card>

        <Card title="System Health" icon={<Activity className="w-4 h-4 text-cyan-400" />}>
          <AsyncSection state={health}>
            {(data) => (
              <div className="divide-y divide-slate-800/50">
                {Object.entries(data.subsystems).map(([name, entry]) => (
                  <div key={name} className="px-5 py-3 flex items-center justify-between">
                    <span className="text-sm text-slate-300 capitalize">{name.replace(/_/g, ' ')}</span>
                    <Badge tone={entry.healthy ? 'positive' : 'negative'}>{entry.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </AsyncSection>
        </Card>
      </div>
    </div>
  );
}
