import { useEffect, useState } from 'react';
import { Activity, RefreshCw, TrendingUp } from 'lucide-react';

import api from '../lib/api';
import { formatDateTime, formatNumber, formatSignedPercent } from '../lib/format';
import { useAction, useApi, usePolling } from '../lib/useApi';
import { useMarketStream } from '../lib/useMarketStream';
import { computeMicrostructure } from '../lib/microstructure';
import ProChart, { type LiveCandle } from '../components/ProChart';
import DepthChart from '../components/DepthChart';
import type { Candle, MarketCoverage, MicrostructureMetrics, Orderbook, Ticker } from '../lib/types';
import {
  AsyncSection,
  Badge,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  StatTile,
} from '../components/ui';

interface StreamStatusResponse {
  enabled: boolean;
  status: string;
  symbols: string[];
  age_seconds: number | null;
}

export default function MarketDataPage() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [livePrice, setLivePrice] = useState<number | null>(null);
  const [liveMicro, setLiveMicro] = useState<MicrostructureMetrics | null>(null);
  const [liveBook, setLiveBook] = useState<{ bids: [number, number][]; asks: [number, number][] } | null>(null);
  const [liveCandle, setLiveCandle] = useState<LiveCandle | null>(null);

  // Only open a socket when the server is actually ingesting.
  const stream = useApi<StreamStatusResponse>(
    () => api.get<StreamStatusResponse>('/health/stream').then((r) => r.data),
  );
  const streamEnabled = stream.data?.enabled ?? false;

  const live = useMarketStream(symbol, {
    enabled: streamEnabled,
    onEvent: (event) => {
      if (event.event_type === 'kline' && typeof event.close === 'number') {
        setLivePrice(event.close);
        // Live-update the chart's forming bar, but only for the timeframe shown
        // (the stream carries every interval for the symbol).
        if (event.interval === timeframe && typeof event.open_time === 'number') {
          setLiveCandle({
            time: Math.floor(event.open_time / 1000),
            open: event.open ?? event.close,
            high: event.high ?? event.close,
            low: event.low ?? event.close,
            close: event.close,
            volume: event.volume ?? 0,
          });
        }
      } else if (event.event_type === 'depth' && event.bids && event.asks) {
        // Real-time microstructure + liquidity: recompute on every depth tick.
        const m = computeMicrostructure(symbol, event.bids, event.asks);
        if (m) setLiveMicro(m);
        setLiveBook({ bids: event.bids, asks: event.asks });
      }
    },
  });

  useEffect(() => {
    setLivePrice(null);
    setLiveMicro(null);
    setLiveBook(null);
    setLiveCandle(null);
  }, [symbol, timeframe]);

  const symbols = useApi<string[]>(() => api.get<string[]>('/market/symbols').then((r) => r.data));
  const timeframes = useApi<string[]>(
    () => api.get<string[]>('/market/timeframes').then((r) => r.data),
  );
  const coverage = useApi<MarketCoverage>(
    () => api.get<MarketCoverage>('/market/coverage').then((r) => r.data),
  );

  // What the backend actually holds for the pair on screen, so an empty table
  // can say why it is empty instead of looking like a failed request.
  const pairCoverage = coverage.data?.coverage.find(
    (c) => c.symbol === symbol && c.timeframe === timeframe,
  );

  const sync = useAction(async () => {
    await api.post('/market/sync');
  });
  const ticker = useApi<Ticker>(
    () => api.get<Ticker>('/market/ticker', { params: { symbol } }).then((r) => r.data),
    [symbol],
  );
  const candles = useApi<Candle[]>(
    () =>
      api
        // Pull deep history (the backend caps at 1000): enough to draw MA99 and
        // scroll back well over a week on the common timeframes. ProChart opens
        // on the most recent bars and lets you pan back through the rest.
        .get<Candle[]>('/market/klines', { params: { symbol, timeframe, limit: 1000 } })
        .then((r) => r.data),
    [symbol, timeframe],
  );
  const book = useApi<Orderbook>(
    () => api.get<Orderbook>('/market/orderbook', { params: { symbol, limit: 10 } }).then((r) => r.data),
    [symbol],
  );
  const micro = useApi<MicrostructureMetrics>(
    () => api.get<MicrostructureMetrics>('/market/microstructure', { params: { symbol } }).then((r) => r.data),
    [symbol],
  );

  // Polling is the fallback. When the WebSocket is delivering ticks the price
  // is already live, so only the depth snapshot needs refreshing.
  usePolling(
    () => {
      if (live.status !== 'open') ticker.reload();
      book.reload();
      micro.reload();
    },
    15_000,
  );

  const change = ticker.data?.priceChangePercent ? Number(ticker.data.priceChangePercent) : null;
  const restPrice = ticker.data?.lastPrice ? Number(ticker.data.lastPrice) : null;
  const displayPrice = livePrice ?? restPrice;
  // Prefer the real-time value computed from the depth stream; fall back to the
  // 15s REST snapshot until the first depth tick arrives.
  const microData = liveMicro ?? micro.data ?? null;
  const depthBook =
    liveBook ??
    (book.data
      ? {
          bids: book.data.bids.map(([p, q]) => [Number(p), Number(q)] as [number, number]),
          asks: book.data.asks.map(([p, q]) => [Number(p), Number(q)] as [number, number]),
        }
      : null);

  const streamBadge =
    live.status === 'open'
      ? { tone: 'positive' as const, label: `live · ${live.messageCount} ticks` }
      : streamEnabled
        ? { tone: 'warning' as const, label: `stream ${live.status}` }
        : { tone: 'neutral' as const, label: 'polling (stream disabled)' };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Market Data"
        description="Live prices, depth, and stored candles"
        actions={
          <div className="flex items-center gap-3">
            {coverage.data && (
              <Badge tone={coverage.data.pairs_missing === 0 ? 'positive' : 'warning'}>
                {coverage.data.pairs_with_data}/{coverage.data.pairs_total} pairs ·{' '}
                {coverage.data.total_candles.toLocaleString()} candles
              </Badge>
            )}
            <Badge tone={streamBadge.tone}>{streamBadge.label}</Badge>
            <Button
              variant="secondary"
              onClick={async () => {
                await sync.run();
                coverage.reload();
              }}
              disabled={sync.pending}
            >
              {sync.pending ? 'Syncing…' : 'Sync market data'}
            </Button>
            <Button variant="secondary" onClick={() => { ticker.reload(); candles.reload(); book.reload(); coverage.reload(); }}>
              <span className="flex items-center gap-1.5"><RefreshCw className="w-3 h-3" /> Refresh</span>
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-4">
        <Field label="Symbol">
          <Select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {(symbols.data ?? [symbol]).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </Select>
        </Field>
        <Field label="Timeframe">
          <Select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
            {(timeframes.data ?? [timeframe]).map((tf) => (
              <option key={tf} value={tf}>{tf}</option>
            ))}
          </Select>
        </Field>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile
          label="Last Price"
          value={displayPrice !== null ? formatNumber(displayPrice) : '—'}
          sub={
            livePrice !== null
              ? 'streaming'
              : change !== null
                ? formatSignedPercent(change)
                : undefined
          }
          tone={change === null ? 'neutral' : change >= 0 ? 'positive' : 'negative'}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatTile label="24h High" value={ticker.data?.highPrice ? formatNumber(Number(ticker.data.highPrice)) : '—'} />
        <StatTile label="24h Low" value={ticker.data?.lowPrice ? formatNumber(Number(ticker.data.lowPrice)) : '—'} />
        <StatTile
          label="24h Volume"
          value={ticker.data?.volume ? formatNumber(Number(ticker.data.volume), 0) : '—'}
        />
      </div>

      <Card title={`Microstructure · ${symbol}`} icon={<Activity className="w-4 h-4 text-cyan-400" />}>
        {microData ? (
          <div className="p-5 space-y-4">
            <div className="flex justify-end">
              <Badge tone={liveMicro ? 'positive' : 'neutral'}>
                {liveMicro ? 'live · depth stream' : 'polling · 15s'}
              </Badge>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatTile label="Microprice" value={formatNumber(microData.microprice)} sub={`mid ${formatNumber(microData.mid)}`} />
              <StatTile label="Spread" value={`${formatNumber(microData.spread_bps, 2)} bps`} sub={formatNumber(microData.spread)} />
              <StatTile
                label="Imbalance"
                value={formatNumber(microData.imbalance, 3)}
                sub={`top ${microData.levels} levels`}
                tone={microData.imbalance >= 0 ? 'positive' : 'negative'}
              />
              <StatTile
                label={`Depth ±${microData.depth_bps}bps`}
                value={`${formatNumber(microData.bid_depth, 2)} / ${formatNumber(microData.ask_depth, 2)}`}
                sub="bid / ask"
              />
            </div>
            <div>
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span className="text-emerald-400">bids</span>
                <span>order-book imbalance</span>
                <span className="text-red-400">asks</span>
              </div>
              <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-800">
                <div
                  className="bg-emerald-500/70 transition-all duration-150"
                  style={{ width: `${((1 + microData.imbalance) / 2) * 100}%` }}
                />
                <div
                  className="bg-red-500/70 transition-all duration-150"
                  style={{ width: `${((1 - microData.imbalance) / 2) * 100}%` }}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="p-5 text-sm text-slate-500">{micro.error ?? 'Loading microstructure…'}</div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title={`Chart · ${symbol}`} className="lg:col-span-2">
          <div className="flex gap-1.5 px-4 pt-3">
            {(timeframes.data ?? ['15m', '1h', '4h', '1d']).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  tf === timeframe ? 'bg-cyan-500/15 text-cyan-300' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
          <AsyncSection
            state={candles}
            emptyWhen={(d) => d.length === 0}
            emptyMessage={`No stored candles for ${symbol} ${timeframe}`}
            emptyHint={
              pairCoverage && !pairCoverage.has_data
                ? 'This pair has not been ingested yet. Use Sync market data above; a background job also tops up every pair every 10 minutes.'
                : 'The backfill may still be running for this pair.'
            }
          >
            {(data) => (
              <div className="p-3">
                <ProChart candles={data} live={liveCandle} />
              </div>
            )}
          </AsyncSection>
        </Card>

        <Card title="Order Book">
          <AsyncSection state={book}>
            {(data) => (
              <div className="p-5 space-y-4">
                <div>
                  <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Asks</div>
                  <div className="space-y-1">
                    {[...data.asks].reverse().map(([price, qty], i) => (
                      <div key={`ask-${i}`} className="flex justify-between text-xs font-mono">
                        <span className="text-red-400">{formatNumber(Number(price))}</span>
                        <span className="text-slate-500">{formatNumber(Number(qty), 4)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Bids</div>
                  <div className="space-y-1">
                    {data.bids.map(([price, qty], i) => (
                      <div key={`bid-${i}`} className="flex justify-between text-xs font-mono">
                        <span className="text-emerald-400">{formatNumber(Number(price))}</span>
                        <span className="text-slate-500">{formatNumber(Number(qty), 4)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </AsyncSection>
        </Card>
      </div>

      <Card title={`Liquidity · ${symbol}`} icon={<Activity className="w-4 h-4 text-cyan-400" />}>
        <div className="p-5">
          {depthBook ? (
            <>
              <DepthChart bids={depthBook.bids} asks={depthBook.asks} />
              <div className="flex justify-between text-xs font-mono text-slate-500 mt-2">
                <span className="text-emerald-400">cumulative bids</span>
                <span>{liveBook ? 'live · depth stream' : 'snapshot'}</span>
                <span className="text-red-400">cumulative asks</span>
              </div>
            </>
          ) : (
            <div className="text-sm text-slate-500">Loading depth…</div>
          )}
        </div>
      </Card>

      {symbols.error && (
        <div className="text-xs text-amber-400">
          <Badge tone="warning">Symbols unavailable</Badge> {symbols.error}
        </div>
      )}

      {pairCoverage && pairCoverage.has_data && pairCoverage.is_stale && (
        <p className="text-xs text-amber-400">
          <Badge tone="warning">stale</Badge> Newest {symbol} {timeframe} candle is from{' '}
          {formatDateTime(pairCoverage.newest)}. The sync job tops this up every 10 minutes.
        </p>
      )}

      {coverage.data && coverage.data.pairs_missing > 0 && (
        <p className="text-xs text-slate-500">
          {coverage.data.pairs_missing} of {coverage.data.pairs_total} symbol/timeframe pairs have
          no data yet. A background job is filling them; use Sync market data to start it now.
        </p>
      )}

      {sync.error && <p className="text-xs text-red-400">{sync.error}</p>}

      {!streamEnabled && (
        <p className="text-xs text-slate-600">
          Live streaming is off. Set <span className="font-mono">MARKET_STREAM_ENABLED=true</span> on
          the backend to push ticks over the WebSocket gateway instead of polling.
        </p>
      )}
    </div>
  );
}
