"""
QuantX — Shared input shapes for market identifiers.

Symbols and timeframes arrive from the browser, from tool arguments chosen by a
model, and from job payloads. They are then used as database keys, metric
labels, cache keys, subscription patterns and upstream request parameters, so
their shape is bounded once, here, and every schema reuses it.
"""

from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field

# Binance symbols are short upper-case alphanumerics (e.g. BTCUSDT, 1000SHIBUSDT).
SYMBOL_PATTERN = r"^[A-Z0-9]{3,20}$"
# Binance kline intervals: 1m, 15m, 4h, 1d, 1w, 1M ...
TIMEFRAME_PATTERN = r"^[0-9]{1,2}[smhdwM]$"

# Finite ceilings no real order approaches. They exist so the fields reject
# inf/NaN and cannot overflow downstream arithmetic.
MAX_PRICE = 1e12
MAX_QUANTITY = 1e12


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _printable(value: str) -> str:
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ValueError("must not contain control characters")
    return value


Symbol = Annotated[str, BeforeValidator(_upper), Field(pattern=SYMBOL_PATTERN)]
Timeframe = Annotated[str, BeforeValidator(_strip), Field(pattern=TIMEFRAME_PATTERN)]
Price = Annotated[float, Field(gt=0.0, le=MAX_PRICE, allow_inf_nan=False)]
Quantity = Annotated[float, Field(gt=0.0, le=MAX_QUANTITY, allow_inf_nan=False)]
# Free text that reaches logs, alerts and exports: bounded, no control bytes.
ShortText = Annotated[str, Field(max_length=255), AfterValidator(_printable)]
