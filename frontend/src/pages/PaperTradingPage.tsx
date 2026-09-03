import { useState } from 'react';
import { Plus, Wallet } from 'lucide-react';

import api from '../lib/api';
import { formatUsd } from '../lib/format';
import { useAction } from '../lib/useApi';
import { usePaperAccounts } from '../lib/usePaperAccount';
import type { PaperAccount, PaperOrder } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  StatTile,
  TextInput,
} from '../components/ui';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'];

export default function PaperTradingPage() {
  const { accounts, selectedId, setSelectedId, selected } = usePaperAccounts();

  const [accountName, setAccountName] = useState('Demo Account');
  const [initialBalance, setInitialBalance] = useState('100000');
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('0.01');
  const [lastOrder, setLastOrder] = useState<PaperOrder | null>(null);

  const createAccount = useAction(async () => {
    const res = await api.post<PaperAccount>('/paper/accounts', {
      name: accountName,
      initial_balance: Number(initialBalance),
    });
    accounts.reload();
    return res.data;
  });

  const submitOrder = useAction(async () => {
    const res = await api.post<PaperOrder>('/paper/orders', {
      account_id: selectedId,
      symbol,
      side,
      order_type: 'MARKET',
      quantity: Number(quantity),
    });
    setLastOrder(res.data);
    accounts.reload();
    return res.data;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Paper Trading"
        description="Simulated execution against live prices, with slippage and fees"
      />

      {selected && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatTile label="Balance" value={formatUsd(selected.current_balance)} icon={<Wallet className="w-4 h-4" />} />
          <StatTile label="Initial" value={formatUsd(selected.initial_balance)} />
          <StatTile
            label="Realized PnL"
            value={formatUsd(selected.realized_pnl)}
            tone={selected.realized_pnl >= 0 ? 'positive' : 'negative'}
          />
          <StatTile
            label="Unrealized PnL"
            value={formatUsd(selected.unrealized_pnl)}
            tone={selected.unrealized_pnl >= 0 ? 'positive' : 'negative'}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Your Accounts" icon={<Wallet className="w-4 h-4 text-cyan-400" />}>
          <AsyncSection
            state={accounts}
            emptyWhen={(d) => d.length === 0}
            emptyMessage="No paper accounts yet"
            emptyHint="Create one below to start trading."
          >
            {(data) => (
              <div className="divide-y divide-slate-800/50">
                {data.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setSelectedId(a.id)}
                    className={`w-full px-5 py-3 flex items-center justify-between text-left transition-colors ${
                      a.id === selectedId ? 'bg-slate-800/50' : 'hover:bg-slate-800/30'
                    }`}
                  >
                    <div>
                      <div className="text-sm text-white font-medium">{a.name}</div>
                      <div className="text-xs text-slate-500 font-mono">{a.id.slice(0, 8)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-mono text-white">{formatUsd(a.current_balance)}</div>
                      {a.id === selectedId && <Badge tone="info">selected</Badge>}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </AsyncSection>

          <div className="p-5 border-t border-slate-800 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name">
                <TextInput value={accountName} onChange={(e) => setAccountName(e.target.value)} />
              </Field>
              <Field label="Initial balance">
                <TextInput
                  type="number"
                  min="100"
                  value={initialBalance}
                  onChange={(e) => setInitialBalance(e.target.value)}
                />
              </Field>
            </div>
            <Button onClick={() => void createAccount.run()} disabled={createAccount.pending}>
              <span className="flex items-center gap-1.5"><Plus className="w-3 h-3" /> Create account</span>
            </Button>
            {createAccount.error && <div className="text-xs text-red-400">{createAccount.error}</div>}
          </div>
        </Card>

        <Card title="Submit Order">
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Symbol">
                <Select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                  {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
              <Field label="Side">
                <Select value={side} onChange={(e) => setSide(e.target.value as 'BUY' | 'SELL')}>
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </Select>
              </Field>
            </div>
            <Field label="Quantity">
              <TextInput
                type="number"
                step="0.0001"
                min="0"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </Field>

            <Button
              onClick={() => void submitOrder.run()}
              disabled={!selectedId || submitOrder.pending}
              variant={side === 'BUY' ? 'primary' : 'danger'}
            >
              {submitOrder.pending ? 'Submitting…' : `Submit ${side} order`}
            </Button>

            {!selectedId && (
              <p className="text-xs text-slate-500">Select or create an account first.</p>
            )}
            {submitOrder.error && <div className="text-xs text-red-400">{submitOrder.error}</div>}

            {lastOrder && (
              <div className="mt-2 p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500">Status</span>
                  <Badge tone="positive">{lastOrder.status}</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Fill price</span>
                  <span className="text-white">{formatUsd(lastOrder.filled_price)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Quantity</span>
                  <span className="text-white">{lastOrder.filled_quantity}</span>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
