"""
QuantX — Position book reconstructed from fills.

The risk engine needs the account's real book (holdings, today's realised P&L,
recent losing exits) to enforce exposure, concurrency, daily-loss and cooldown
limits. Live trading stores fills, not positions, so the book is rebuilt here
with average-cost accounting. This module is pure: same fills, same book.

Only fills recorded by QuantX are visible. Assets bought elsewhere have no cost
basis here, so a sell beyond the tracked quantity realises nothing for the
untracked part. Exchange commissions are charged in varying assets and are not
included in realised P&L.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

_EPSILON = 1e-12


@dataclass(frozen=True)
class Fill:
    """One executed order, or the executed part of one."""

    symbol: str
    side: str  # BUY / SELL
    quantity: float
    price: float
    at: datetime


@dataclass
class Holding:
    quantity: float
    avg_cost: float


@dataclass
class Book:
    holdings: dict[str, Holding] = field(default_factory=dict)
    realized_since_day_start: float = 0.0
    last_loss_at: dict[str, datetime] = field(default_factory=dict)


def build_book(fills: Iterable[Fill], day_start: datetime) -> Book:
    """Replay fills in time order into holdings and realised P&L."""
    book = Book()
    for f in sorted(fills, key=lambda x: x.at):
        if f.quantity <= 0 or f.price <= 0:
            continue
        held = book.holdings.get(f.symbol)
        if f.side.upper() == "BUY":
            if held is None:
                book.holdings[f.symbol] = Holding(quantity=f.quantity, avg_cost=f.price)
            else:
                total = held.quantity + f.quantity
                held.avg_cost = (held.avg_cost * held.quantity + f.price * f.quantity) / total
                held.quantity = total
            continue

        if held is None:
            continue
        matched = min(f.quantity, held.quantity)
        pnl = (f.price - held.avg_cost) * matched
        if f.at >= day_start:
            book.realized_since_day_start += pnl
        if pnl < 0:
            book.last_loss_at[f.symbol] = f.at
        held.quantity -= matched
        if held.quantity <= _EPSILON:
            del book.holdings[f.symbol]
    return book
