import { useCallback, useEffect, useRef, useState } from 'react';

import { errorMessage } from './api';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Run an async request on mount and whenever `deps` change.
 *
 * Results from a superseded request are discarded, so rapidly changing inputs
 * (typing a symbol, switching timeframe) cannot render a stale response over a
 * newer one.
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: { enabled?: boolean } = {},
): AsyncState<T> {
  const { enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    const id = ++requestId.current;
    let cancelled = false;

    setLoading(true);
    setError(null);

    fetcher()
      .then((result) => {
        if (cancelled || id !== requestId.current) return;
        setData(result);
      })
      .catch((err) => {
        if (cancelled || id !== requestId.current) return;
        setError(errorMessage(err));
      })
      .finally(() => {
        if (cancelled || id !== requestId.current) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  return { data, loading, error, reload };
}

/**
 * Wrap a mutating action with pending/error state.
 */
export function useAction<Args extends unknown[], R>(
  action: (...args: Args) => Promise<R>,
): {
  run: (...args: Args) => Promise<R | null>;
  pending: boolean;
  error: string | null;
  reset: () => void;
} {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (...args: Args): Promise<R | null> => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (err) {
        setError(errorMessage(err));
        return null;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, reset: () => setError(null) };
}

/** Re-run a callback on an interval while the tab is visible. */
export function usePolling(callback: () => void, intervalMs: number, enabled = true): void {
  const saved = useRef(callback);
  saved.current = callback;

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;

    const tick = () => {
      // Polling a hidden tab burns API budget for output nobody can see.
      if (document.visibilityState === 'visible') saved.current();
    };
    const handle = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(handle);
  }, [intervalMs, enabled]);
}
