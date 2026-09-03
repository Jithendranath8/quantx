"""
QuantX — Real-Time Market Data Primitives.

Provides the pieces the ingestion stream is built from:
- MarketDataNormalizer: raw Binance JSON -> unified domain events
- MarketDataValidator: freshness and sanity checks
- MarketDataCache: bounded in-memory latest-value cache
- MarketDataMetrics: connection health counters

Connection handling itself lives in :mod:`app.websockets.binance_stream`. This
module previously carried a second, unused ``ConnectionManager`` that collided
by name with the gateway's, and had no call sites at all.
"""

import time
from collections import OrderedDict

from pydantic import BaseModel


class MarketDataMetrics(BaseModel):
    """Health counters for a live market data connection."""

    last_event_timestamp: float = 0.0
    market_data_age_ms: float = 0.0
    connection_status: str = "DISCONNECTED"
    reconnect_count: int = 0
    messages_received: int = 0
    latency_ms: float = 0.0

    def observe(self, event_timestamp_ms: float) -> None:
        """Record an inbound event and update freshness/latency."""
        now = time.time()
        self.last_event_timestamp = now
        self.messages_received += 1
        self.market_data_age_ms = max(0.0, now * 1000 - event_timestamp_ms)

    @property
    def age_seconds(self) -> float:
        """Seconds since the last event, or infinity if none has arrived."""
        if self.last_event_timestamp == 0.0:
            return float("inf")
        return time.time() - self.last_event_timestamp


class MarketDataValidator:
    """Validates real-time market data messages for freshness and sanity."""

    @staticmethod
    def validate_candle(candle_data: dict) -> bool:
        """Verify candle fields are present, positive, and internally consistent."""
        try:
            open_p = float(candle_data["open"])
            high_p = float(candle_data["high"])
            low_p = float(candle_data["low"])
            close_p = float(candle_data["close"])
        except (KeyError, ValueError, TypeError):
            return False

        if min(open_p, high_p, low_p, close_p) <= 0:
            return False
        if high_p < low_p:
            return False
        # Open and close must sit inside the bar's range.
        return low_p <= open_p <= high_p and low_p <= close_p <= high_p

    @staticmethod
    def is_stale(timestamp_ms: float, max_age_seconds: float = 10.0) -> bool:
        """Check whether a message is older than the allowed maximum age."""
        return (time.time() * 1000 - timestamp_ms) > (max_age_seconds * 1000)


class MarketDataNormalizer:
    """Normalizes raw Binance streams into a unified QuantX payload."""

    @staticmethod
    def normalize_kline(raw: dict) -> dict:
        """Convert a Binance kline event into the domain shape.

        Carries close_time, quote_volume and trade count as well as OHLCV: a
        closed candle from this stream is persisted directly, and those columns
        are NOT NULL on the candles table.
        """
        k = raw.get("k", {})
        return {
            "event_type": "kline",
            "symbol": str(k.get("s") or raw.get("s") or "").upper(),
            "timestamp": raw.get("E", int(time.time() * 1000)),
            # Bar open time: this is the candle's identity, not the event time.
            "open_time": k.get("t"),
            "close_time": k.get("T"),
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
            "quote_volume": float(k.get("q", 0)),
            "trades_count": int(k.get("n", 0)),
            "is_final": bool(k.get("x", False)),
            "interval": k.get("i", "1m"),
        }

    @staticmethod
    def normalize_trade(raw: dict) -> dict:
        """Convert a Binance trade event into the domain shape."""
        return {
            "event_type": "trade",
            "symbol": str(raw.get("s", "")).upper(),
            "timestamp": raw.get("E", int(time.time() * 1000)),
            "price": float(raw.get("p", 0)),
            "quantity": float(raw.get("q", 0)),
            "is_buyer_maker": bool(raw.get("m", False)),
        }

    @staticmethod
    def normalize_depth(raw: dict) -> dict:
        """Convert a Binance depth event into the domain shape."""
        return {
            "event_type": "depth",
            "symbol": str(raw.get("s", "")).upper(),
            "timestamp": raw.get("E", int(time.time() * 1000)),
            "bids": [[float(p), float(q)] for p, q in raw.get("b", [])],
            "asks": [[float(p), float(q)] for p, q in raw.get("a", [])],
        }

    @classmethod
    def normalize(cls, raw: dict) -> dict | None:
        """Dispatch on the Binance event shape; None when unrecognized."""
        if "k" in raw:
            return cls.normalize_kline(raw)
        if "p" in raw and "q" in raw:
            return cls.normalize_trade(raw)
        if "b" in raw and "a" in raw:
            return cls.normalize_depth(raw)
        return None


class MarketDataCache:
    """Bounded in-memory cache of the latest candle/trade/depth per symbol.

    The cap matters: an unbounded dict keyed by symbol grows without limit in a
    long-lived process if the upstream ever emits unexpected symbols.
    """

    def __init__(self, max_symbols: int = 256) -> None:
        self._max_symbols = max_symbols
        self._candles: OrderedDict[str, dict] = OrderedDict()
        self._trades: OrderedDict[str, dict] = OrderedDict()
        self._depth: OrderedDict[str, dict] = OrderedDict()

    def _put(self, store: OrderedDict[str, dict], symbol: str, value: dict) -> None:
        """Insert with LRU eviction once the symbol cap is reached."""
        key = symbol.upper()
        store[key] = value
        store.move_to_end(key)
        while len(store) > self._max_symbols:
            store.popitem(last=False)

    def update_candle(self, symbol: str, candle: dict) -> None:
        """Store the latest candle for a symbol."""
        self._put(self._candles, symbol, candle)

    def get_candle(self, symbol: str) -> dict | None:
        """Latest candle for a symbol, if cached."""
        return self._candles.get(symbol.upper())

    def update_trade(self, symbol: str, trade: dict) -> None:
        """Store the latest trade for a symbol."""
        self._put(self._trades, symbol, trade)

    def get_trade(self, symbol: str) -> dict | None:
        """Latest trade for a symbol, if cached."""
        return self._trades.get(symbol.upper())

    def update_depth(self, symbol: str, depth: dict) -> None:
        """Store the latest depth snapshot for a symbol."""
        self._put(self._depth, symbol, depth)

    def get_depth(self, symbol: str) -> dict | None:
        """Latest depth snapshot for a symbol, if cached."""
        return self._depth.get(symbol.upper())

    def update(self, event: dict) -> None:
        """Route a normalized event into the right store."""
        symbol = event.get("symbol", "")
        if not symbol:
            return
        match event.get("event_type"):
            case "kline":
                self.update_candle(symbol, event)
            case "trade":
                self.update_trade(symbol, event)
            case "depth":
                self.update_depth(symbol, event)


# Process-wide cache shared by the ingestion stream and the health endpoints.
market_cache = MarketDataCache()
