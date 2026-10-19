import { useEffect, useRef, useState } from 'react';
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type MouseEventParams,
  type UTCTimestamp,
} from 'lightweight-charts';

import type { Candle } from '../lib/types';
import { macd as calcMacd, rsi as calcRsi, sma } from '../lib/indicators';

export interface LiveCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const UP = '#0ecb81';
const DOWN = '#f6465d';
// Binance-style indicator colours.
const C_MA = ['#f0b90b', '#ec4899', '#8b5cf6']; // MA7 / MA25 / MA99
const C_VOLMA = ['#f0b90b', '#8b5cf6']; // MA5 / MA10
const MA_P = [7, 25, 99];
const VOLMA_P = [5, 10];

const baseLayout = {
  // attributionLogo: false removes the default "TradingView" logo in the corner.
  layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8', fontSize: 11, attributionLogo: false },
  grid: { vertLines: { color: 'rgba(148,163,184,0.05)' }, horzLines: { color: 'rgba(148,163,184,0.05)' } },
  rightPriceScale: { borderColor: 'rgba(148,163,184,0.12)' },
  timeScale: { timeVisible: true, borderColor: 'rgba(148,163,184,0.12)' },
  crosshair: { mode: 1 as const },
  autoSize: true,
};

const sec = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;
const fmt = (n: number, d = 2) => n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const compact = (n: number) => Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 2 }).format(n);
const line = (times: number[], vals: (number | null)[]): LineData[] => {
  const out: LineData[] = [];
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i];
    if (v !== null) out.push({ time: times[i] as UTCTimestamp, value: v });
  }
  return out;
};

interface Meta {
  times: number[];
  o: number[]; h: number[]; l: number[]; c: number[]; v: number[]; quote: number[]; txn: number[];
  ma: (number | null)[][];
  volMa: (number | null)[][];
  macd: ReturnType<typeof calcMacd>;
  rsi: (number | null)[];
  idxOf: Map<number, number>;
}

/**
 * Binance-style multi-pane chart: candles + MA(7/25/99), a volume pane with
 * MA(5/10), a MACD pane, and an RSI pane - time-synced, with a boxed OHLCV
 * crosshair tooltip. lightweight-charts v4 has no native panes, so the panes
 * are separate chart instances with their time scales and crosshair kept in
 * step.
 */
export default function ProChart({ candles, live }: { candles: Candle[]; live?: LiveCandle | null }) {
  const mainEl = useRef<HTMLDivElement>(null);
  const volEl = useRef<HTMLDivElement>(null);
  const macdEl = useRef<HTMLDivElement>(null);
  const rsiEl = useRef<HTMLDivElement>(null);

  const charts = useRef<IChartApi[]>([]);
  const candleS = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volS = useRef<ISeriesApi<'Histogram'> | null>(null);
  const maS = useRef<ISeriesApi<'Line'>[]>([]);
  const volMaS = useRef<ISeriesApi<'Line'>[]>([]);
  const macdHistS = useRef<ISeriesApi<'Histogram'> | null>(null);
  const difS = useRef<ISeriesApi<'Line'> | null>(null);
  const deaS = useRef<ISeriesApi<'Line'> | null>(null);
  const rsiS = useRef<ISeriesApi<'Line'> | null>(null);

  const [meta, setMeta] = useState<Meta | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  // ── Build the four synced charts once ──────────────────────────────
  useEffect(() => {
    if (!mainEl.current || !volEl.current || !macdEl.current || !rsiEl.current) return;
    const main = createChart(mainEl.current, {
      ...baseLayout,
      // Our own watermark in place of the library's attribution.
      watermark: {
        visible: true,
        text: 'QuantX',
        color: 'rgba(148,163,184,0.07)',
        fontSize: 52,
        horzAlign: 'center',
        vertAlign: 'center',
      },
    });
    const vol = createChart(volEl.current, baseLayout);
    const macd = createChart(macdEl.current, baseLayout);
    const rsi = createChart(rsiEl.current, baseLayout);
    charts.current = [main, vol, macd, rsi];

    candleS.current = main.addCandlestickSeries({ upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN });
    maS.current = C_MA.map((color) => main.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }));
    volS.current = vol.addHistogramSeries({ priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false });
    volMaS.current = C_VOLMA.map((color) => vol.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }));
    macdHistS.current = macd.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
    difS.current = macd.addLineSeries({ color: C_MA[0], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    deaS.current = macd.addLineSeries({ color: C_MA[1], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    rsiS.current = rsi.addLineSeries({ color: C_MA[0], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });

    // Keep every pane's visible time range in step.
    let syncing = false;
    charts.current.forEach((src) => {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        charts.current.forEach((dst) => { if (dst !== src) dst.timeScale().setVisibleLogicalRange(range); });
        syncing = false;
      });
    });

    return () => {
      charts.current.forEach((c) => c.remove());
      charts.current = [];
    };
  }, []);

  // ── Crosshair: update the legend index and sync the vertical line ──
  useEffect(() => {
    const [main, vol, macd, rsi] = charts.current;
    if (!main || !meta) return;
    const handler = (param: MouseEventParams) => {
      if (param.time === undefined) {
        setHover(null);
        [vol, macd, rsi].forEach((c) => c.clearCrosshairPosition());
        return;
      }
      const i = meta.idxOf.get(param.time as number);
      setHover(i ?? null);
      if (i !== undefined) {
        if (volS.current) vol.setCrosshairPosition(meta.v[i], param.time, volS.current);
        if (difS.current) macd.setCrosshairPosition(meta.macd.dif[i] ?? 0, param.time, difS.current);
        if (rsiS.current) rsi.setCrosshairPosition(meta.rsi[i] ?? 50, param.time, rsiS.current);
      }
    };
    main.subscribeCrosshairMove(handler);
    return () => main.unsubscribeCrosshairMove(handler);
  }, [meta]);

  // ── Load data + indicators whenever candles change ─────────────────
  useEffect(() => {
    if (!candleS.current) return;
    const times = candles.map((c) => sec(c.timestamp));
    const o = candles.map((c) => c.open);
    const h = candles.map((c) => c.high);
    const l = candles.map((c) => c.low);
    const c = candles.map((x) => x.close);
    const v = candles.map((x) => x.volume);
    const quote = candles.map((x) => x.quote_volume ?? 0);
    const txn = candles.map((x) => x.trades_count ?? 0);
    const ma = MA_P.map((p) => sma(c, p));
    const volMa = VOLMA_P.map((p) => sma(v, p));
    const macd = calcMacd(c);
    const rsi = calcRsi(c, 6);
    const idxOf = new Map<number, number>();
    times.forEach((t, i) => idxOf.set(t, i));

    candleS.current.setData(candles.map((x, i) => ({ time: times[i], open: x.open, high: x.high, low: x.low, close: x.close })));
    maS.current.forEach((s, i) => s.setData(line(times, ma[i])));
    volS.current?.setData(candles.map((x, i) => ({ time: times[i], value: x.volume, color: x.close >= x.open ? 'rgba(14,203,129,0.5)' : 'rgba(246,70,93,0.5)' })));
    volMaS.current.forEach((s, i) => s.setData(line(times, volMa[i])));
    macdHistS.current?.setData(line(times, macd.hist).map((d) => ({ ...d, color: d.value >= 0 ? 'rgba(14,203,129,0.5)' : 'rgba(246,70,93,0.5)' })));
    difS.current?.setData(line(times, macd.dif));
    deaS.current?.setData(line(times, macd.dea));
    rsiS.current?.setData(line(times, rsi));

    setMeta({ times, o, h, l, c, v, quote, txn, ma, volMa, macd, rsi, idxOf });
    charts.current[0]?.timeScale().fitContent();
  }, [candles]);

  // ── Live-update the forming candle + its volume bar ────────────────
  useEffect(() => {
    if (!live || !candleS.current) return;
    candleS.current.update({ time: live.time as UTCTimestamp, open: live.open, high: live.high, low: live.low, close: live.close });
    volS.current?.update({ time: live.time as UTCTimestamp, value: live.volume, color: live.close >= live.open ? 'rgba(14,203,129,0.5)' : 'rgba(246,70,93,0.5)' });
  }, [live]);

  const i = hover ?? (meta ? meta.times.length - 1 : 0);
  const chg = meta ? meta.c[i] - meta.o[i] : 0;
  const pct = meta && meta.o[i] ? (chg / meta.o[i]) * 100 : 0;
  const rangePct = meta && meta.o[i] ? ((meta.h[i] - meta.l[i]) / meta.o[i]) * 100 : 0;
  const maVal = (arr: (number | null)[]) => (arr[i] !== null && arr[i] !== undefined ? fmt(arr[i] as number) : '—');

  return (
    <div className="space-y-px">
      {/* Candle pane + boxed OHLCV tooltip + MA legend */}
      <div className="relative">
        {/* MA readout: always on, like Binance's top legend line. */}
        {meta && (
          <div className="absolute left-2 top-1.5 z-10 flex flex-wrap gap-x-3 text-[11px] font-mono">
            {MA_P.map((p, k) => (
              <span key={p} style={{ color: C_MA[k] }}>MA({p}): {maVal(meta.ma[k])}</span>
            ))}
          </div>
        )}
        {/* Boxed OHLCV tooltip: only while the crosshair is over a candle. */}
        {meta && hover !== null && (
          <div className="absolute left-2 top-7 z-10 w-36 rounded-md border border-slate-700/60 bg-slate-900/90 p-2 text-[11px] font-mono text-slate-400 backdrop-blur-sm">
            {([
              ['Time', new Date(meta.times[i] * 1000).toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })],
              ['Open', fmt(meta.o[i])],
              ['High', fmt(meta.h[i])],
              ['Low', fmt(meta.l[i])],
              ['Close', fmt(meta.c[i])],
            ] as [string, string][]).map(([k, val]) => (
              <div key={k} className="flex justify-between gap-2"><span>{k}</span><span className="text-slate-200">{val}</span></div>
            ))}
            <div className="flex justify-between gap-2"><span>Chg</span><span className={chg >= 0 ? 'text-emerald-400' : 'text-red-400'}>{chg >= 0 ? '+' : ''}{fmt(chg)}</span></div>
            <div className="flex justify-between gap-2"><span>%Chg</span><span className={pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>{pct >= 0 ? '+' : ''}{fmt(pct)}%</span></div>
            <div className="flex justify-between gap-2"><span>Range</span><span className="text-slate-300">{fmt(rangePct)}%</span></div>
            <div className="flex justify-between gap-2"><span>Vol</span><span className="text-slate-300">{fmt(meta.v[i])}</span></div>
            <div className="flex justify-between gap-2"><span>Txn</span><span className="text-slate-300">{compact(meta.txn[i])}</span></div>
          </div>
        )}
        <div ref={mainEl} className="h-72 w-full" />
      </div>

      {/* Volume pane */}
      <div className="relative border-t border-slate-800/60">
        {meta && (
          <div className="absolute left-2 top-1 z-10 flex flex-wrap gap-x-3 text-[10px] font-mono text-slate-400">
            <span>Vol <span className="text-slate-300">{compact(meta.v[i])}</span></span>
            <span style={{ color: C_VOLMA[0] }}>MA(5): {maVal(meta.volMa[0])}</span>
            <span style={{ color: C_VOLMA[1] }}>MA(10): {maVal(meta.volMa[1])}</span>
          </div>
        )}
        <div ref={volEl} className="h-24 w-full" />
      </div>

      {/* MACD pane */}
      <div className="relative border-t border-slate-800/60">
        {meta && (
          <div className="absolute left-2 top-1 z-10 flex flex-wrap gap-x-3 text-[10px] font-mono">
            <span style={{ color: C_MA[0] }}>DIF: {maVal(meta.macd.dif)}</span>
            <span style={{ color: C_MA[1] }}>DEA: {maVal(meta.macd.dea)}</span>
            <span style={{ color: C_MA[2] }}>MACD: {maVal(meta.macd.hist)}</span>
          </div>
        )}
        <div ref={macdEl} className="h-24 w-full" />
      </div>

      {/* RSI pane */}
      <div className="relative border-t border-slate-800/60">
        {meta && (
          <div className="absolute left-2 top-1 z-10 text-[10px] font-mono" style={{ color: C_MA[0] }}>
            RSI(6): {maVal(meta.rsi)}
          </div>
        )}
        <div ref={rsiEl} className="h-20 w-full" />
      </div>
    </div>
  );
}
