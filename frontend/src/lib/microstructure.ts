import type { MicrostructureMetrics } from './types';

/**
 * Compute order-book microstructure from a live depth snapshot, client-side.
 *
 * Mirrors the backend `engines/microstructure/analytics.py` (the authoritative,
 * unit-tested version). Done here too so the panel can update on every depth
 * tick from the WebSocket instead of waiting on the 15s REST poll.
 */
export function computeMicrostructure(
  symbol: string,
  bids: [number, number][],
  asks: [number, number][],
  levels = 10,
  depthBps = 25,
): MicrostructureMetrics | null {
  if (bids.length === 0 || asks.length === 0) return null;

  const [bestBid, bestBidQty] = bids[0];
  const [bestAsk, bestAskQty] = asks[0];
  const mid = (bestBid + bestAsk) / 2;
  const spread = bestAsk - bestBid;
  const spreadBps = mid > 0 ? (spread / mid) * 10_000 : 0;

  const queue = bestBidQty + bestAskQty;
  const microprice =
    queue > 0 ? (bestBid * bestAskQty + bestAsk * bestBidQty) / queue : mid;

  const topN = Math.max(1, levels);
  const bidVol = bids.slice(0, topN).reduce((s, [, q]) => s + q, 0);
  const askVol = asks.slice(0, topN).reduce((s, [, q]) => s + q, 0);
  const total = bidVol + askVol;
  const imbalance = total > 0 ? (bidVol - askVol) / total : 0;

  const band = (mid * depthBps) / 10_000;
  const bidDepth = bids.filter(([p]) => p >= mid - band).reduce((s, [, q]) => s + q, 0);
  const askDepth = asks.filter(([p]) => p <= mid + band).reduce((s, [, q]) => s + q, 0);

  return {
    symbol,
    best_bid: bestBid,
    best_ask: bestAsk,
    mid,
    microprice,
    spread,
    spread_bps: spreadBps,
    imbalance,
    bid_depth: bidDepth,
    ask_depth: askDepth,
    bid_levels: bids.length,
    ask_levels: asks.length,
    levels,
    depth_bps: depthBps,
  };
}
