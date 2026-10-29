/**
 * Order-book liquidity (depth) chart: cumulative volume vs price, bids rising
 * away from the mid on the left, asks on the right - the classic "walls" view.
 * Inline SVG because depth is indexed by price, not time (so lightweight-charts,
 * which is a time-series library, is the wrong tool here).
 */
export default function DepthChart({
  bids,
  asks,
}: {
  bids: [number, number][];
  asks: [number, number][];
}) {
  if (bids.length < 2 || asks.length < 2) {
    return <div className="p-5 text-xs text-zinc-500">No depth data.</div>;
  }

  // Cumulative volume outward from the mid.
  let cum = 0;
  const bidCum = bids.map(([p, q]) => { cum += q; return [p, cum] as [number, number]; }); // price desc
  cum = 0;
  const askCum = asks.map(([p, q]) => { cum += q; return [p, cum] as [number, number]; }); // price asc

  const minP = bidCum[bidCum.length - 1][0];
  const maxP = askCum[askCum.length - 1][0];
  const rangeP = maxP - minP || 1;
  const maxC = Math.max(bidCum[bidCum.length - 1][1], askCum[askCum.length - 1][1]) || 1;
  const x = (p: number) => ((p - minP) / rangeP) * 100;
  const y = (v: number) => 40 - (v / maxC) * 40;

  // Draw each side left→right (price ascending); bids are stored descending.
  const bidLine = [...bidCum].reverse().map(([p, v]) => `${x(p).toFixed(2)},${y(v).toFixed(2)}`);
  const askLine = askCum.map(([p, v]) => `${x(p).toFixed(2)},${y(v).toFixed(2)}`);
  const bestBidX = x(bids[0][0]);
  const bestAskX = x(asks[0][0]);
  const bidPoly = `${x(minP).toFixed(2)},40 ${bidLine.join(' ')} ${bestBidX.toFixed(2)},40`;
  const askPoly = `${bestAskX.toFixed(2)},40 ${askLine.join(' ')} ${x(maxP).toFixed(2)},40`;
  const midX = ((bestBidX + bestAskX) / 2).toFixed(2);

  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-40" role="img" aria-label="Order-book liquidity depth">
      <polygon points={bidPoly} fill="rgba(16,185,129,0.22)" stroke="#10b981" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
      <polygon points={askPoly} fill="rgba(239,68,68,0.22)" stroke="#ef4444" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
      <line x1={midX} y1="0" x2={midX} y2="40" stroke="#64748b" strokeWidth="0.3" strokeDasharray="1 1" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
