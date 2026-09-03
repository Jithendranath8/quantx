"""
QuantX — Indicator API Endpoints.

Multi-timeframe technical indicator analysis.

Authenticated and rate limited: each timeframe costs a query plus a full
indicator pass, so an unbounded comma-separated list on an open endpoint was a
single-request denial of service.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.engines.indicators.multi_timeframe import (
    SUPPORTED_TIMEFRAMES,
    MultiTimeframeEngine,
)

router = APIRouter(prefix="/indicators", tags=["Indicator Engine"])


@router.get(
    "/timeframes",
    summary="List supported timeframes",
)
async def list_timeframes() -> dict[str, list[str]]:
    """Timeframes accepted by the indicator engine."""
    return {"timeframes": list(SUPPORTED_TIMEFRAMES)}


@router.get(
    "/{symbol}",
    summary="Get multi-timeframe indicator analysis for a symbol",
    dependencies=[Depends(RateLimiter("indicators", max_requests=60))],
)
async def get_indicators(
    symbol: str,
    user: CurrentUser,
    db: DBSession,
    timeframes: str = Query("1m,5m,15m,1h,4h", description="Comma-separated timeframes"),
    limit: int = Query(200, ge=20, le=1000),
) -> dict[str, Any]:
    """Compute indicators across the requested timeframes.

    Timeframes are validated against a whitelist, de-duplicated, and capped by
    MAX_TIMEFRAMES_PER_REQUEST.
    """
    requested = [tf.strip() for tf in timeframes.split(",") if tf.strip()]
    engine = MultiTimeframeEngine(db)
    results = await engine.get_multi_timeframe_indicators(
        symbol=symbol, timeframes=requested, limit=limit
    )
    return {"symbol": symbol.upper(), "indicators": results}
