import { Download, PieChart } from 'lucide-react';

import api from '../lib/api';
import { formatPercent, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { PortfolioSummary } from '../lib/types';
import {
  AsyncSection,
  Button,
  Card,
  PageHeader,
  StatTile,
  TableWrap,
  Td,
  Th,
} from '../components/ui';

export default function AnalyticsPage() {
  const portfolio = useApi<PortfolioSummary>(
    () => api.get<PortfolioSummary>('/analytics/portfolio').then((r) => r.data),
  );

  const exportCsv = useAction(async () => {
    // Fetched through the api client so the Authorization header is attached;
    // a plain link would hit the endpoint unauthenticated.
    const res = await api.get('/analytics/export/csv', { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'quantx_trade_history.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Portfolio performance and trade history export"
        actions={
          <Button variant="secondary" onClick={() => void exportCsv.run()} disabled={exportCsv.pending}>
            <span className="flex items-center gap-1.5">
              <Download className="w-3 h-3" /> {exportCsv.pending ? 'Exporting…' : 'Export CSV'}
            </span>
          </Button>
        }
      />

      {exportCsv.error && <div className="text-xs text-red-400">{exportCsv.error}</div>}

      <AsyncSection state={portfolio}>
        {(data) => (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatTile label="Total Equity" value={formatUsd(data.total_equity_usd)} icon={<PieChart className="w-4 h-4" />} />
              <StatTile
                label="Realized PnL"
                value={formatUsd(data.realized_pnl_usd)}
                tone={data.realized_pnl_usd >= 0 ? 'positive' : 'negative'}
              />
              <StatTile
                label="Unrealized PnL"
                value={formatUsd(data.unrealized_pnl_usd)}
                tone={data.unrealized_pnl_usd >= 0 ? 'positive' : 'negative'}
              />
              <StatTile
                label="Win Rate"
                value={data.win_rate_pct === null ? '—' : formatPercent(data.win_rate_pct)}
                sub={
                  data.win_rate_pct === null
                    ? 'No closed trades yet'
                    : `${data.closed_trades_count} of ${data.total_trades_count}`
                }
              />
            </div>

            <Card title="Allocation Breakdown">
              {data.allocations.length === 0 ? (
                <div className="p-5 text-sm text-slate-500">No allocations to show.</div>
              ) : (
                <TableWrap>
                  <table className="w-full">
                    <thead className="bg-slate-900/60">
                      <tr>
                        <Th>Asset</Th>
                        <Th align="right">Value</Th>
                        <Th align="right">Weight</Th>
                        <Th>Distribution</Th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                      {data.allocations.map((a) => (
                        <tr key={a.symbol} className="hover:bg-slate-800/30 transition-colors">
                          <Td mono className="text-white">{a.symbol}</Td>
                          <Td align="right" mono className="text-slate-300">{formatUsd(a.value_usd)}</Td>
                          <Td align="right" mono className="text-slate-400">{formatPercent(a.allocation_pct)}</Td>
                          <Td className="w-1/3">
                            <div className="w-full bg-slate-800 rounded-full h-1.5">
                              <div
                                className="h-1.5 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500"
                                style={{ width: `${Math.min(100, Math.max(0, a.allocation_pct))}%` }}
                              />
                            </div>
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
              )}
            </Card>
          </>
        )}
      </AsyncSection>
    </div>
  );
}
