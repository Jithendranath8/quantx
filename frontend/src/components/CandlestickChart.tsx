import { useEffect, useRef } from 'react';
import {
  ColorType,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
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
const sec = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;

/**
 * TradingView-style candlestick + volume chart. Historical bars come from the
 * stored candles; `live` replaces/extends the forming bar on each stream tick,
 * so the chart shows market flow in real time without a reload.
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
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    chartRef.current = chart;
    candleRef.current = candleSeries;
    volumeRef.current = volumeSeries;
    return () => {
      chart.remove();
      chartRef.current = candleRef.current = volumeRef.current = null;
    };
  }, []);

  // Load the historical series whenever it changes.
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
    const bars: CandlestickData[] = candles.map((c) => ({
      time: sec(c.timestamp),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const vol: HistogramData[] = candles.map((c) => ({
      time: sec(c.timestamp),
      value: c.volume,
      color: c.close >= c.open ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)',
    }));
    candleRef.current.setData(bars);
    volumeRef.current.setData(vol);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Live-update the forming bar.
  useEffect(() => {
    if (!live || !candleRef.current) return;
    candleRef.current.update({
      time: live.time as UTCTimestamp,
      open: live.open,
      high: live.high,
      low: live.low,
      close: live.close,
    });
  }, [live]);

  return <div ref={containerRef} className="h-80 w-full" />;
}
