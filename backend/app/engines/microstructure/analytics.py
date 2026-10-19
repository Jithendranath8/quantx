"""
QuantX - Order-book microstructure analytics.

Pure, dependency-free functions over an order-book snapshot. These are the
numbers a market maker actually watches: where the true price sits (microprice),
how one-sided the book is (imbalance), how wide and how deep it is. Kept
separate from any fetch/transport so they are trivially unit-testable.

Inputs are already-parsed float levels: ``bids`` sorted high-to-low and ``asks``
low-to-high, each a list of ``[price, quantity]`` (base units), as Binance
returns depth.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MicrostructureMetrics:
    """One snapshot's worth of order-book microstructure signals."""

    best_bid: float
    best_ask: float
    mid: float
    microprice: float
    spread: float
    spread_bps: float
    imbalance: float  # order-book imbalance over the top levels, in [-1, 1]
    bid_depth: float  # base volume resting within depth_bps of the mid, bid side
    ask_depth: float
    bid_levels: int
    ask_levels: int


def analyze_order_book(
    bids: list[list[float]],
    asks: list[list[float]],
    *,
    levels: int = 10,
    depth_bps: float = 25.0,
) -> MicrostructureMetrics | None:
    """Compute microstructure metrics from a depth snapshot.

    Args:
        bids: ``[[price, qty], ...]`` sorted best (highest) first.
        asks: ``[[price, qty], ...]`` sorted best (lowest) first.
        levels: How many top levels to sum for the imbalance signal.
        depth_bps: Half-window around the mid, in basis points, over which the
            resting depth on each side is totalled.

    Returns:
        The metrics, or ``None`` if either side of the book is empty.

    Notes:
        - **microprice** weights each best price by the *opposite* side's size,
          so it leans toward the heavier book - a better fair-value estimate
          than the plain mid when the book is lopsided.
        - **imbalance** is ``(bidVol - askVol) / (bidVol + askVol)`` over the top
          ``levels``: +1 is all bids (upward pressure), -1 all asks.
    """
    if not bids or not asks:
        return None

    best_bid, best_bid_qty = bids[0][0], bids[0][1]
    best_ask, best_ask_qty = asks[0][0], asks[0][1]

    mid = (best_bid + best_ask) / 2.0
    spread = best_ask - best_bid
    spread_bps = (spread / mid * 10_000.0) if mid > 0 else 0.0

    queue = best_bid_qty + best_ask_qty
    # Weight each best price by the opposite queue size (standard microprice).
    microprice = (
        (best_bid * best_ask_qty + best_ask * best_bid_qty) / queue if queue > 0 else mid
    )

    top_n = max(1, levels)
    bid_vol = sum(q for _, q in bids[:top_n])
    ask_vol = sum(q for _, q in asks[:top_n])
    total = bid_vol + ask_vol
    imbalance = (bid_vol - ask_vol) / total if total > 0 else 0.0

    # Resting depth within depth_bps of the mid, one half-window each side.
    band = mid * depth_bps / 10_000.0
    bid_floor = mid - band
    ask_ceiling = mid + band
    bid_depth = sum(q for p, q in bids if p >= bid_floor)
    ask_depth = sum(q for p, q in asks if p <= ask_ceiling)

    return MicrostructureMetrics(
        best_bid=best_bid,
        best_ask=best_ask,
        mid=mid,
        microprice=microprice,
        spread=spread,
        spread_bps=spread_bps,
        imbalance=imbalance,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        bid_levels=len(bids),
        ask_levels=len(asks),
    )
