import { Activity, RefreshCw } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime } from '../lib/format';
import { useApi, usePolling } from '../lib/useApi';
import type { SystemHealth } from '../lib/types';
import { AsyncSection, Badge, Button, Card, PageHeader } from '../components/ui';

function overallTone(status: string): 'positive' | 'warning' | 'negative' {
  if (status === 'HEALTHY') return 'positive';
  if (status === 'DEGRADED') return 'warning';
  return 'negative';
}

/** Render the extra fields a subsystem reports beyond its verdict. */
function details(entry: Record<string, unknown>): [string, string][] {
  return Object.entries(entry)
    .filter(([key, value]) => !['status', 'healthy'].includes(key) && value !== null && value !== undefined)
    .map(([key, value]) => [
      key.replace(/_/g, ' '),
      Array.isArray(value) ? value.join(', ') : String(value),
    ]);
}

export default function HealthCenterPage() {
  const health = useApi<SystemHealth>(
    () => api.get<SystemHealth>('/health/system').then((r) => r.data),
  );

  usePolling(() => health.reload(), 30_000);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Health Center"
        description="Measured status of every subsystem"
        actions={
          <div className="flex items-center gap-3">
            {health.data && <Badge tone={overallTone(health.data.status)}>{health.data.status}</Badge>}
            <Button variant="secondary" onClick={health.reload}>
              <span className="flex items-center gap-1.5">
                <RefreshCw className={`w-3 h-3 ${health.loading ? 'animate-spin' : ''}`} /> Refresh
              </span>
            </Button>
          </div>
        }
      />

      <AsyncSection state={health}>
        {(data) => (
          <>
            <p className="text-xs text-slate-600 font-mono">Checked at {formatDateTime(data.checked_at)}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Object.entries(data.subsystems).map(([name, entry]) => (
                <Card key={name} className={entry.healthy ? '' : 'border-red-500/30'}>
                  <div className="p-5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-white capitalize">
                        {name.replace(/_/g, ' ')}
                      </span>
                      <Badge tone={entry.healthy ? 'positive' : 'negative'}>{entry.status}</Badge>
                    </div>
                    <div className="space-y-1">
                      {details(entry as Record<string, unknown>).map(([key, value]) => (
                        <div key={key} className="flex justify-between text-xs">
                          <span className="text-slate-500 capitalize">{key}</span>
                          <span className="text-slate-300 font-mono truncate max-w-[60%]" title={value}>
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}
      </AsyncSection>

      <p className="text-xs text-slate-600 flex items-center gap-1.5">
        <Activity className="w-3 h-3" />
        Every value here is probed live. Nothing on this page is a fixed label.
      </p>
    </div>
  );
}
