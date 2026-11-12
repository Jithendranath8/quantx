"""
QuantX — Shared, bounded query and path parameters.

Routes used to take ``symbol``, ``timeframe`` and ``strategy_name`` as plain
strings. Those values become database filters, upstream request parameters,
cache keys and log fields, so their shape is declared once here and reused.
Declare the default at the use site: ``symbol: SymbolQuery = "BTCUSDT"``.
"""

from typing import Annotated

from fastapi import Path, Query

from app.schemas.validators import TIMEFRAME_PATTERN

# Case-insensitive on the way in; handlers upper-case before use.
_SYMBOL_IN = r"^[A-Za-z0-9]{3,20}$"
_STRATEGY_NAME = r"^[a-z0-9_]{1,64}$"

SymbolQuery = Annotated[str, Query(pattern=_SYMBOL_IN, description="Trading pair, e.g. BTCUSDT")]
SymbolPath = Annotated[str, Path(pattern=_SYMBOL_IN, description="Trading pair, e.g. BTCUSDT")]
TimeframeQuery = Annotated[str, Query(pattern=TIMEFRAME_PATTERN, description="Candle interval, e.g. 1h")]
StrategyNameQuery = Annotated[str, Query(pattern=_STRATEGY_NAME, description="Registered strategy name")]
