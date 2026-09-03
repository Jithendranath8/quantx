import { Layers, RefreshCw } from 'lucide-react';

import api from '../lib/api';
import { formatNumber, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import { usePaperAccounts } from '../lib/usePaperAccount';
import type { PaperPosition } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Select,
  TableWrap,
  Td,
  Th,
} from '../components/ui';

export default function PositionsPage() {
  const { accounts, selectedId, setSelectedId } = usePaperAccounts();

  const positions = useApi<PaperPosition[]>(
    () =>
      api.get<PaperPosition[]>(`/paper/accounts/${selectedId}/positions`).then((r) => r.data),
    [selectedId],
    { enabled: selectedId !== null },
  );

  const mark = useAction(async () => {
    await api.post(`/paper/accounts/${selectedId}/mark-to-market`);
    positions.reload();
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Positions"
        description="Open positions across your paper trading accounts"
        actions={
          <Button variant="secondary" onClick={() => void mark.run()} disabled={!selectedId || mark.pending}>
            <span className="flex items-center gap-1.5">
              <RefreshCw className={`w-3 h-3 ${mark.pending ? 'animate-spin' : ''}`} /> Mark to market
            </span>
          </Button>
        }
      />

      {accounts.data && accounts.data.length > 0 && (
        <Field label="Account">
          <Select value={selectedId ?? ''} onChange={(e) => setSelectedId(e.target.value)}>
            {accounts.data.map((a) => (
              <option key={a.id} value={a.id}>{a.name} · {formatUsd(a.current_balance)}</option>
            ))}
          </Select>
        </Field>
      )}

      {mark.error && <div className="text-xs text-red-400">{mark.error}</div>}

      <Card title="Open Positions" icon={<Layers className="w-4 h-4 text-cyan-400" />}>
        {accounts.data && accounts.data.length === 0 ? (
          <EmptyState
            message="No paper trading accounts"
            hint="Create one on the Paper Trading page to start tracking positions."
          />
        ) : (
          <AsyncSection
            state={positions}
            emptyWhen={(d) => d.length === 0}
            emptyMessage="No open positions"
            emptyHint="Submit a paper order to open a position."
          >
            {(data) => (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-slate-900/60">
                    <tr>
                      <Th>Symbol</Th>
                      <Th>Side</Th>
                      <Th align="right">Quantity</Th>
                      <Th align="right">Entry</Th>
                      <Th align="right">Current</Th>
                      <Th align="right">Unrealized PnL</Th>
                      <Th align="right">Stop / Target</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {data.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-800/30 transition-colors">
                        <Td mono className="text-white font-semibold">{p.symbol}</Td>
                        <Td><Badge tone={p.side === 'LONG' ? 'positive' : 'negative'}>{p.side}</Badge></Td>
                        <Td align="right" mono className="text-slate-300">{formatNumber(p.quantity, 6)}</Td>
                        <Td align="right" mono className="text-slate-300">{formatUsd(p.entry_price)}</Td>
                        <Td align="right" mono className="text-white">{formatUsd(p.current_price)}</Td>
                        <Td
                          align="right"
                          mono
                          className={p.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}
                        >
                          {formatUsd(p.unrealized_pnl)}
                        </Td>
                        <Td align="right" mono className="text-slate-500 text-xs">
                          {p.stop_loss ? formatNumber(p.stop_loss) : '—'} / {p.take_profit ? formatNumber(p.take_profit) : '—'}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </AsyncSection>
        )}
      </Card>
    </div>
  );
}
