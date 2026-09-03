"""
QuantX — Redis Pub/Sub Channel Naming.

Single source of truth for market-data channel names.

The publisher and the gateway previously built these strings independently:
the publisher wrote ``market:btcusdt:kline_1m`` while the gateway subscribed to
``market:BTCUSDT:*``. The case mismatch meant no message ever matched, silently,
with no error anywhere. Deriving both from these helpers makes that class of
bug impossible.
"""

MARKET_PREFIX = "market"


def _norm(symbol: str) -> str:
    """Canonical symbol casing for channel names."""
    return symbol.strip().upper()


def kline_channel(symbol: str, interval: str) -> str:
    """Channel carrying kline updates for one symbol and interval."""
    return f"{MARKET_PREFIX}:{_norm(symbol)}:kline:{interval}"


def trade_channel(symbol: str) -> str:
    """Channel carrying individual trades for one symbol."""
    return f"{MARKET_PREFIX}:{_norm(symbol)}:trade"


def depth_channel(symbol: str) -> str:
    """Channel carrying order book depth updates for one symbol."""
    return f"{MARKET_PREFIX}:{_norm(symbol)}:depth"


def symbol_pattern(symbol: str) -> str:
    """Pattern matching every market channel for one symbol."""
    return f"{MARKET_PREFIX}:{_norm(symbol)}:*"


def channel_for_event(symbol: str, event_type: str, interval: str | None = None) -> str:
    """Resolve the channel for a normalized event payload."""
    if event_type == "kline":
        return kline_channel(symbol, interval or "1m")
    if event_type == "trade":
        return trade_channel(symbol)
    if event_type == "depth":
        return depth_channel(symbol)
    return f"{MARKET_PREFIX}:{_norm(symbol)}:{event_type}"
