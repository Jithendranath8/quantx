import React, { useState } from 'react';
import { BookOpen, Plus } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime, formatNumber, formatUsd } from '../lib/format';
import { useAction, useApi } from '../lib/useApi';
import type { JournalEntry } from '../lib/types';
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
  TextArea,
  TextInput,
  Th,
} from '../components/ui';

export default function TradeJournalPage() {
  const entries = useApi<JournalEntry[]>(
    () => api.get<JournalEntry[]>('/journal', { params: { limit: 100 } }).then((r) => r.data),
  );

  const [form, setForm] = useState({
    symbol: 'BTCUSDT',
    timeframe: '1h',
    direction: 'LONG',
    entry_price: '',
    stop_loss: '',
    take_profit: '',
    user_notes: '',
    lessons: '',
  });

  const create = useAction(async () => {
    await api.post('/journal', {
      symbol: form.symbol,
      timeframe: form.timeframe,
      direction: form.direction,
      entry_price: Number(form.entry_price),
      stop_loss: form.stop_loss ? Number(form.stop_loss) : null,
      take_profit: form.take_profit ? Number(form.take_profit) : null,
      user_notes: form.user_notes || null,
      lessons: form.lessons || null,
    });
    setForm((f) => ({ ...f, entry_price: '', stop_loss: '', take_profit: '', user_notes: '', lessons: '' }));
    entries.reload();
  });

  const set = (key: keyof typeof form) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="space-y-6">
      <PageHeader title="Trade Journal" description="Record setups, outcomes, and what you learned" />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card title="New Entry" icon={<Plus className="w-4 h-4 text-brand-400" />}>
          <div className="p-5 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Symbol">
                <TextInput value={form.symbol} onChange={set('symbol')} />
              </Field>
              <Field label="Timeframe">
                <Select value={form.timeframe} onChange={set('timeframe')}>
                  {['5m', '15m', '1h', '4h', '1d'].map((tf) => <option key={tf} value={tf}>{tf}</option>)}
                </Select>
              </Field>
              <Field label="Direction">
                <Select value={form.direction} onChange={set('direction')}>
                  <option value="LONG">LONG</option>
                  <option value="SHORT">SHORT</option>
                </Select>
              </Field>
              <Field label="Entry price">
                <TextInput type="number" step="any" value={form.entry_price} onChange={set('entry_price')} />
              </Field>
              <Field label="Stop loss">
                <TextInput type="number" step="any" value={form.stop_loss} onChange={set('stop_loss')} />
              </Field>
              <Field label="Take profit">
                <TextInput type="number" step="any" value={form.take_profit} onChange={set('take_profit')} />
              </Field>
            </div>
            <Field label="Notes">
              <TextArea rows={3} value={form.user_notes} onChange={set('user_notes')} />
            </Field>
            <Field label="Lessons">
              <TextArea rows={2} value={form.lessons} onChange={set('lessons')} />
            </Field>
            <Button onClick={() => void create.run()} disabled={create.pending || !form.entry_price}>
              {create.pending ? 'Saving…' : 'Save entry'}
            </Button>
            {create.error && <div className="text-xs text-red-400">{create.error}</div>}
          </div>
        </Card>

        <Card title="Entries" icon={<BookOpen className="w-4 h-4 text-brand-400" />} className="xl:col-span-2">
          <AsyncSection
            state={entries}
            emptyWhen={(d) => d.length === 0}
            emptyMessage="No journal entries yet"
            emptyHint="Record your first trade using the form."
          >
            {(data) => (
              <TableWrap>
                <table className="w-full">
                  <thead className="bg-zinc-900/60">
                    <tr>
                      <Th>Trade</Th>
                      <Th>Symbol</Th>
                      <Th>Direction</Th>
                      <Th align="right">Entry</Th>
                      <Th align="right">R:R</Th>
                      <Th align="right">Realized PnL</Th>
                      <Th>Created</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50">
                    {data.map((e) => (
                      <tr key={e.id} className="hover:bg-zinc-800/30 transition-colors align-top">
                        <Td mono className="text-brand-400 text-xs">{e.trade_id}</Td>
                        <Td mono className="text-white">{e.symbol}</Td>
                        <Td><Badge tone={e.direction === 'LONG' ? 'positive' : 'negative'}>{e.direction}</Badge></Td>
                        <Td align="right" mono className="text-zinc-300">{formatNumber(e.entry_price)}</Td>
                        <Td align="right" mono className="text-zinc-400">{e.risk_reward ? formatNumber(e.risk_reward) : '—'}</Td>
                        <Td
                          align="right"
                          mono
                          className={
                            e.realized_pnl === null
                              ? 'text-zinc-500'
                              : e.realized_pnl >= 0
                                ? 'text-emerald-400'
                                : 'text-red-400'
                          }
                        >
                          {formatUsd(e.realized_pnl)}
                        </Td>
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
    </div>
  );
}
