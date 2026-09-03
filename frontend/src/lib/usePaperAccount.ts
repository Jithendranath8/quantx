import { useEffect, useState } from 'react';

import api from './api';
import { useApi } from './useApi';
import type { PaperAccount } from './types';

/**
 * Load the caller's paper accounts and track the selected one.
 *
 * Positions, orders and the paper-trading screen all need this, and the
 * selection has to survive a reload of the account list.
 */
export function usePaperAccounts() {
  const accounts = useApi<PaperAccount[]>(
    () => api.get<PaperAccount[]>('/paper/accounts').then((r) => r.data),
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!accounts.data?.length) {
      setSelectedId(null);
      return;
    }
    // Keep the current selection if it still exists, else fall back to the first.
    setSelectedId((current) =>
      current && accounts.data!.some((a) => a.id === current) ? current : accounts.data![0].id,
    );
  }, [accounts.data]);

  const selected = accounts.data?.find((a) => a.id === selectedId) ?? null;

  return { accounts, selectedId, setSelectedId, selected };
}
