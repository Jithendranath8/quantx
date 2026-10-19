import { useEffect, useRef, useState } from 'react';
import {
  ColorType,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type MouseEventParams,
  type UTCTimestamp,
} from 'lightweight-charts';

import type { Candle } from '../lib/types';

export interface LiveCandle {
  time: number; // bar open time, UNIX seconds
  open: number;
  high: number;
  low: number;
  close: number;
}

const UP = '#10b981';
const DOWN = '#ef4444';
// Binance-style moving averages.
const MAS = [
  { period: 7, color: '#eab308' },
  { period: 25, color: '#a855f7' },
  { period: 99, color: '#38bdf8' },
];
const sec = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;
const fmt = (n: number, d = 2) =>
  n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

/** Simple moving average of close over `period`, aligned to each bar's time. */
function sma(candles: Candle[], period: number): LineData[] {
  const out: LineData[] = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close;
    if (i >= period) sum -= candles[i - period].close;
    if (i >= period - 1) out.push({ time: sec(candles[i].timestamp), value: sum / period });
  }
  return out;
}

interface Legend {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma: (number | undefined)[];
}

/**
 * TradingView-style candlestick + volume chart with MA overlays and an OHLCV
 * hover legend. Historical bars come from stored candles; `live` replaces the
 * forming bar each stream tick so the chart shows market flow in real time.
 */
export default function CandlestickChart({
  candles,
  live,
}: {
  candles: Candle[];
  live?: LiveCandle | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const maRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const defaultLegend = useRef<Legend | null>(null);
  const hovering = useRef(false);
  const [legend, setLegend] = useState<Legend | null>(null);

  // Build the chart once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8', fontSize: 11 },
      grid: {
        vertLines: { color: 'rgba(148,163,184,0.06)' },
        horzLines: { color: 'rgba(148,163,184,0.06)' },
      },
      timeScale: { timeVisible: true, borderColor: 'rgba(148,163,184,0.15)' },
      rightPriceScale: { borderColor: 'rgba(148,163,184,0.15)' },
      crosshair: { mode: 1 },
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });
    const volumeSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    maRefs.current = MAS.map((m) =>
      chart.addLineSeries({ color: m.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    );

    chartRef.current = chart;
    candleRef.current = candleSeries;
    volumeRef.current = volumeSeries;

    const onMove = (param: MouseEventParams) => {
      if (!param.time || param.seriesData.size === 0) {
        hovering.current = false;
        setLegend(defaultLegend.current);
        return;
      }
      const c = param.seriesData.get(candleSeries) as CandlestickData | undefined;
      if (!c) {
        hovering.current = false;
        setLegend(defaultLegend.current);
        return;
      }
      const v = param.seriesData.get(volumeSeries) as HistogramData | undefined;
      hovering.current = true;
      setLegend({
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: v?.value ?? 0,
        ma: maRefs.current.map((s) => (param.seriesData.get(s) as LineData | undefined)?.value),
      });
    };
    chart.subscribeCrosshairMove(onMove);

    return () => {
      chart.remove();
      chartRef.current = candleRef.current = volumeRef.current = null;
      maRefs.current = [];
    };
  }, []);

  // Load the historical series + MAs whenever candles change.
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
    candleRef.current.setData(
      candles.map((c) => ({ time: sec(c.timestamp), open: c.open, high: c.high, low: c.low, close: c.close })),
    );
    volumeRef.current.setData(
      candles.map((c) => ({
        time: sec(c.timestamp),
        value: c.volume,
        color: c.close >= c.open ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)',
      })),
    );
    maRefs.current.forEach((s, i) => s.setData(sma(candles, MAS[i].period)));

    const last = candles[candles.length - 1];
    if (last) {
      defaultLegend.current = {
        open: last.open,
        high: last.high,
        low: last.low,
        close: last.close,
        volume: last.volume,
        ma: MAS.map((m) => {
          const d = sma(candles, m.period);
          return d.length ? d[d.length - 1].value : undefined;
        }),
      };
      if (!hovering.current) setLegend(defaultLegend.current);
    }
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Live-update the forming bar.
  useEffect(() => {
    if (!live || !candleRef.current) return;
    candleRef.current.update({ time: live.time as UTCTimestamp, open: live.open, high: live.high, low: live.low, close: live.close });
    if (defaultLegend.current) {
      defaultLegend.current = { ...defaultLegend.current, open: live.open, high: live.high, low: live.low, close: live.close };
      if (!hovering.current) setLegend(defaultLegend.current);
    }
  }, [live]);

  const chg = legend ? legend.close - legend.open : 0;
  const pct = legend && legend.open ? (chg / legend.open) * 100 : 0;

  return (
    <div className="relative">
      {legend && (
        <div className="absolute left-2 top-1.5 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] font-mono text-slate-400">
          <span>O <span className="text-slate-200">{fmt(legend.open)}</span></span>
          <span>H <span className="text-emerald-400">{fmt(legend.high)}</span></span>
          <span>L <span className="text-red-400">{fmt(legend.low)}</span></span>
          <span>C <span className="text-slate-200">{fmt(legend.close)}</span></span>
          <span className={chg >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            {chg >= 0 ? '+' : ''}{fmt(chg)} ({chg >= 0 ? '+' : ''}{fmt(pct)}%)
          </span>
          <span>Range <span className="text-slate-300">{fmt(legend.high - legend.low)}</span></span>
          <span>Vol <span className="text-slate-300">{fmt(legend.volume)}</span></span>
          {MAS.map((m, i) => (
            <span key={m.period} style={{ color: m.color }}>
              MA{m.period} {legend.ma[i] !== undefined ? fmt(legend.ma[i] as number) : '—'}
            </span>
          ))}
        </div>
      )}
      <div ref={containerRef} className="h-80 w-full" />
    </div>
  );
}
