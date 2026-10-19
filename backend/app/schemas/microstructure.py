"""
QuantX - Order-book microstructure schema.

Response payload for the live microstructure endpoint: the fair-value and
book-shape signals a maker watches, plus the parameters they were computed with.
"""

from pydantic import BaseModel


class MicrostructureResponse(BaseModel):
    """Microstructure metrics for one live order-book snapshot."""

    symbol: str
    best_bid: float
    best_ask: float
    mid: float
    microprice: float
    spread: float
    spread_bps: float
    imbalance: float
    bid_depth: float
    ask_depth: float
    bid_levels: int
    ask_levels: int
    levels: int
    depth_bps: float
