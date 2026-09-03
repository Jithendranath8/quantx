import { useState } from 'react';
import { RefreshCw, Terminal } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime } from '../lib/format';
import { useApi, usePolling } from '../lib/useApi';
import { AsyncSection, Button, Card, Field, PageHeader, Select } from '../components/ui';

interface LedgerEvent {
  event_id: string;
  timestamp: string | null;
  source: string;
  event_type: string;
  symbol: string | null;
  payload: Record<string, unknown>;
  correlation_id: string | null;
}

const EVENT_TYPES = [
  '',
  'LIVE_ORDER_PLACED',
  'EMERGENCY_KILL_SWITCH_ACTIVATED',
  'KILL_SWITCH_DEACTIVATED',
];

function levelColor(eventType: string): string {
  if (eventType.includes('KILL_SWITCH')) return 'text-red-400';
  if (eventType.includes('REJECT') || eventType.includes('FAIL')) return 'text-amber-400';
  return 'text-cyan-400';
}

export default function LogsPage() {
  const [eventType, setEventType] = useState('');

  const events = useApi<LedgerEvent[]>(
    () =>
      api
        .get<LedgerEvent[]>('/events', {
          params: { limit: 200, ...(eventType ? { event_type: eventType } : {}) },
        })
        .then((r) => r.data),
    [eventType],
  );

  usePolling(() => events.reload(), 20_000);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Event Ledger"
        description="Immutable audit trail of everything the platform did on your behalf"
        actions={
          <Button variant="secondary" onClick={events.reload}>
            <span className="flex items-center gap-1.5">
              <RefreshCw className={`w-3 h-3 ${events.loading ? 'animate-spin' : ''}`} /> Refresh
            </span>
          </Button>
        }
      />

      <Field label="Event type">
        <Select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{t || 'All events'}</option>
          ))}
        </Select>
      </Field>

      <Card title="Events" icon={<Terminal className="w-4 h-4 text-cyan-400" />}>
        <AsyncSection
          state={events}
          emptyWhen={(d) => d.length === 0}
          emptyMessage="No events recorded"
          emptyHint="Ledger entries are written when you place orders or trigger the kill switch."
        >
          {(data) => (
            <div className="p-4 font-mono text-xs space-y-1.5 max-h-[70vh] overflow-y-auto">
              {data.map((e) => (
                <div
                  key={e.event_id}
                  className="flex items-start gap-3 py-1.5 border-b border-slate-900 last:border-0"
                >
                  <span className="text-slate-500 shrink-0 w-40">{formatDateTime(e.timestamp)}</span>
                  <span className={`font-bold shrink-0 ${levelColor(e.event_type)}`}>
                    [{e.event_type}]
                  </span>
                  <span className="text-purple-400 shrink-0">[{e.source}]</span>
                  {e.symbol && <span className="text-slate-300 shrink-0">{e.symbol}</span>}
                  <span className="text-slate-400 break-all">{JSON.stringify(e.payload)}</span>
                </div>
              ))}
            </div>
          )}
        </AsyncSection>
      </Card>

      <p className="text-xs text-slate-600">
        This is the database event ledger, not the application log stream. Container logs are
        available with <span className="font-mono">docker compose logs -f backend</span>.
      </p>
    </div>
  );
}
