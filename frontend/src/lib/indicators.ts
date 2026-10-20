/**
 * Client-side technical indicators for the chart panes (SMA, EMA, MACD, RSI).
 * Visualization math only — the backend engine remains the source of truth for
 * anything that drives decisions. Each returns an array aligned 1:1 with the
 * input, using `null` for the warm-up region so series can skip those points.
 */

export function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

/** EMA seeded from the first value (runs from index 0); fine for display. */
function emaFull(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const out: number[] = [];
  let prev = values.length ? values[0] : 0;
  for (let i = 0; i < values.length; i++) {
    prev = i === 0 ? values[0] : values[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

export interface MacdResult {
  dif: (number | null)[]; // MACD line (fast EMA - slow EMA)
  dea: (number | null)[]; // signal line (EMA of DIF)
  hist: (number | null)[]; // DIF - DEA
}

export function macd(close: number[], fast = 12, slow = 26, signal = 9): MacdResult {
  const n = close.length;
  const dif: (number | null)[] = new Array(n).fill(null);
  const dea: (number | null)[] = new Array(n).fill(null);
  const hist: (number | null)[] = new Array(n).fill(null);
  if (n < slow) return { dif, dea, hist };

  const ef = emaFull(close, fast);
  const es = emaFull(close, slow);
  const start = slow - 1;
  const difVals: number[] = [];
  for (let i = start; i < n; i++) {
    const d = ef[i] - es[i];
    dif[i] = d;
    difVals.push(d);
  }
  const sig = emaFull(difVals, signal);
  for (let j = 0; j < difVals.length; j++) {
    const i = start + j;
    if (j >= signal - 1) {
      dea[i] = sig[j];
      hist[i] = (dif[i] as number) - (sig[j]);
    }
  }
  return { dif, dea, hist };
}

/** Wilder-smoothed RSI. */
export function rsi(close: number[], period = 6): (number | null)[] {
  const n = close.length;
  const out: (number | null)[] = new Array(n).fill(null);
  if (n <= period) return out;

  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const ch = close[i] - close[i - 1];
    if (ch >= 0) gain += ch;
    else loss -= ch;
  }
  gain /= period;
  loss /= period;
  out[period] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  for (let i = period + 1; i < n; i++) {
    const ch = close[i] - close[i - 1];
    gain = (gain * (period - 1) + (ch > 0 ? ch : 0)) / period;
    loss = (loss * (period - 1) + (ch < 0 ? -ch : 0)) / period;
    out[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  }
  return out;
}
