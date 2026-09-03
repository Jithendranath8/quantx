import { useCallback, useEffect, useRef, useState } from 'react';

import { getAccessToken } from './api';

export interface MarketEvent {
  event_type: 'kline' | 'trade' | 'depth';
  symbol: string;
  timestamp: number;
  interval?: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  is_final?: boolean;
  price?: number;
  quantity?: number;
  bids?: [number, number][];
  asks?: [number, number][];
}

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

const MAX_BACKOFF_MS = 30_000;
const BASE_BACKOFF_MS = 1_000;

/**
 * Subscribe to `/ws/market/{symbol}` for live ticks.
 *
 * The gateway authenticates from a query parameter because WebSocket handshakes
 * cannot carry an Authorization header. Reconnection uses exponential backoff,
 * and the socket is torn down on unmount or symbol change so a page that is no
 * longer visible does not hold a server-side subscription open — the gateway
 * has a fixed connection ceiling.
 *
 * `enabled` defaults to false: server-side ingestion is off unless
 * MARKET_STREAM_ENABLED is set, and a socket that will never receive a message
 * is worse than not opening one.
 */
export function useMarketStream(
  symbol: string,
  options: { enabled?: boolean; onEvent?: (event: MarketEvent) => void } = {},
): { status: StreamStatus; lastEvent: MarketEvent | null; messageCount: number } {
  const { enabled = false, onEvent } = options;

  const [status, setStatus] = useState<StreamStatus>('idle');
  const [lastEvent, setLastEvent] = useState<MarketEvent | null>(null);
  const [messageCount, setMessageCount] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const closedByUs = useRef(false);
  // Held in a ref so a new callback identity does not tear down the socket.
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (socketRef.current) {
      closedByUs.current = true;
      socketRef.current.close();
      socketRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !symbol) {
      cleanup();
      setStatus('idle');
      return;
    }

    let disposed = false;

    const connect = () => {
      if (disposed) return;

      const token = getAccessToken();
      if (!token) {
        setStatus('error');
        return;
      }

      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const url = `${scheme}://${window.location.host}/ws/market/${encodeURIComponent(
        symbol,
      )}?token=${encodeURIComponent(token)}`;

      setStatus('connecting');
      closedByUs.current = false;
      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.onopen = () => {
        if (disposed) return;
        retryRef.current = 0;
        setStatus('open');
      };

      socket.onmessage = (message) => {
        if (disposed) return;
        try {
          const event = JSON.parse(message.data as string) as MarketEvent;
          setLastEvent(event);
          setMessageCount((n) => n + 1);
          handlerRef.current?.(event);
        } catch {
          // A single malformed frame must not kill the subscription.
        }
      };

      socket.onerror = () => {
        if (!disposed) setStatus('error');
      };

      socket.onclose = () => {
        if (disposed || closedByUs.current) return;
        setStatus('closed');
        const delay = Math.min(BASE_BACKOFF_MS * 2 ** retryRef.current, MAX_BACKOFF_MS);
        retryRef.current += 1;
        timerRef.current = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      cleanup();
    };
  }, [symbol, enabled, cleanup]);

  return { status, lastEvent, messageCount };
}
