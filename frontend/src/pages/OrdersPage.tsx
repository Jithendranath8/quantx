import { ListOrdered } from 'lucide-react';

import api from '../lib/api';
import { formatNumber, formatUsd } from '../lib/format';
import { useApi } from '../lib/useApi';
import { usePaperAccounts } from '../lib/usePaperAccount';
import type { PaperOrder } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Select,
  TableWrap,
  Td,
  Th,
} from '../components/ui';

function statusTone(status: string): 'positive' | 'negative' | 'warning' | 'neutral' {
  if (status === 'FILLED') return 'positive';
  if (status.startsWith('CANCELLED') || status === 'REJECTED') return 'negative';
  if (status === 'PENDING') return 'warning';
  return 'neutral';
}

export default function OrdersPage() {
  const { accounts, selectedId, setSelectedId } = usePaperAccounts();

  const orders = useApi<PaperOrder[]>(
    () =>
      api
        .get<PaperOrder[]>(`/paper/accounts/${selectedId}/orders`, { params: { limit: 200 } })
        .then((r) => r.data),
    [selectedId],
    { enabled: selectedId !== null },
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Orders" description="Paper order history for the selected account" />

      {accounts.data && accounts.data.length > 0 && (
        <Field label="Account">
          <Select value={selectedId ?? ''} onChange={(e) => setSelectedId(e.target.value)}>
            {accounts.data.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        </Field>
      )}

      <Card title="Order History" icon={<ListOrdered className="w-4 h-4 text-cyan-400" />}>
        {accounts.data && accounts.data.length === 0 ? (
          <EmptyState
            message="No paper trading accounts"
            hint="Create one on the Paper Trading page first."
          />
        ) : (
          <AsyncSection
            state={orders}
            emptyWhen={(d) => d.length === 0}
            emptyMessage="No orders yet"
          >
            {(data) => (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-slate-900/60">
                    <tr>
                      <Th>Symbol</Th>
                      <Th>Side</Th>
                      <Th>Type</Th>
                      <Th align="right">Quantity</Th>
                      <Th align="right">Price</Th>
                      <Th align="right">Filled</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {data.map((o) => (
                      <tr key={o.id} className="hover:bg-slate-800/30 transition-colors">
                        <Td mono className="text-white font-semibold">{o.symbol}</Td>
                        <Td><Badge tone={o.side === 'BUY' ? 'positive' : 'negative'}>{o.side}</Badge></Td>
                        <Td className="text-slate-400">{o.order_type}</Td>
                        <Td align="right" mono className="text-slate-300">{formatNumber(o.quantity, 6)}</Td>
                        <Td align="right" mono className="text-slate-300">{formatUsd(o.price)}</Td>
                        <Td align="right" mono className="text-white">{formatUsd(o.filled_price)}</Td>
                        <Td><Badge tone={statusTone(o.status)}>{o.status}</Badge></Td>
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
