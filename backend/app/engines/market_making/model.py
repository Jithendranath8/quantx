"""
QuantX — Avellaneda-Stoikov optimal market-making quotes.

Pure, dependency-free quoting math, deliberately separated from the simulation
loop so it can be reasoned about and unit-tested in isolation. Reference:
Avellaneda & Stoikov, "High-frequency trading in a limit order book" (2008).

The model answers two questions each step:
  1. Where is the *reservation price* — the inventory-adjusted fair value the
     maker is indifferent to trading around? Holding a long position pushes it
     below the mid, so the maker quotes to sell the position down (and vice
     versa). This is what keeps inventory mean-reverting toward flat.
  2. How wide should the quotes be? The optimal half-spread trades the risk of
     holding inventory (the gamma*sigma^2*tau term) off against the edge available from the
     book's order-arrival intensity (the (2/gamma)*ln(1+gamma/k) term).
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Quote:
    """A reservation price and the symmetric bid/ask placed around it."""

    reservation: float
    bid: float
    ask: float

    @property
    def half_spread(self) -> float:
        """Distance from the reservation price to each quote (price units)."""
        return (self.ask - self.bid) / 2.0


def avellaneda_stoikov_quote(
    mid: float,
    inventory: float,
    sigma: float,
    *,
    gamma: float,
    k: float,
    time_remaining: float = 1.0,
) -> Quote:
    """Optimal bid/ask around an inventory-skewed reservation price.

    Args:
        mid: Current mid price (price units).
        inventory: Signed inventory in base units; positive is long.
        sigma: Volatility of the mid price per step, in **price** units.
        gamma: Inventory risk aversion (> 0). Higher tightens inventory control
            (bigger skew) and widens the spread.
        k: Order-book liquidity / arrival-rate decay (> 0). Higher means fills
            come easily, so the optimal spread is tighter.
        time_remaining: Normalized time to the risk horizon in (0, 1]. As it
            decays toward 0 the inventory penalty shrinks; at 1 it is full.

    Returns:
        The reservation price and the bid/ask quotes around it.

    Raises:
        ValueError: If gamma or k is non-positive (the log term is undefined).
    """
    if gamma <= 0 or k <= 0:
        raise ValueError("gamma and k must be positive")

    # gamma*sigma^2*tau: the inventory-risk term, in price^2 * (1/price) = price when scaled by
    # inventory. It both skews the reservation price and forms half the spread.
    variance_term = gamma * sigma * sigma * time_remaining
    reservation = mid - inventory * variance_term

    # Optimal total spread delta = gamma*sigma^2*tau + (2/gamma)*ln(1 + gamma/k); quotes sit half of it
    # either side of the reservation price (NOT the mid).
    half_spread = 0.5 * (variance_term + (2.0 / gamma) * math.log1p(gamma / k))
    return Quote(
        reservation=reservation,
        bid=reservation - half_spread,
        ask=reservation + half_spread,
    )
