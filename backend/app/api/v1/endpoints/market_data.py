"""
QuantX — Market Data Endpoints.

Ticker, orderbook, stored klines, and historical download triggers.

The Binance proxy routes are authenticated and rate limited: they consume
request weight against a single shared exchange API key, so unauthenticated
access is a direct route to an IP ban.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.connectors.binance_client import get_binance_client
from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.models.market_data import Candle
from app.schemas.market_data import CandleSchema, DownloadHistoryRequest
from app.services.market_coverage_service import MarketCoverageService
from app.workers.downloader import download_historical_klines
from app.workers.market_data import sync_market_data as sync_market_data_task

router = APIRouter(prefix="/market", tags=["Market Data"])


@router.get(
    "/symbols",
    response_model=list[str],
    summary="Get active trading symbols",
)
async def get_symbols(user: CurrentUser) -> list[str]:
    """Symbols this deployment covers.

    Read from configuration rather than a hardcoded list, so the UI can only
    offer symbols the ingestion jobs actually populate.
    """
    return get_settings().market_symbol_list


@router.get(
    "/timeframes",
    response_model=list[str],
    summary="Get supported timeframes",
)
async def get_timeframes(user: CurrentUser) -> list[str]:
    """Timeframes this deployment stores candles for."""
    return get_settings().market_timeframe_list


@router.get(
    "/coverage",
    summary="Report stored candle coverage",
)
async def get_coverage(user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Which symbol/timeframe pairs have data, and whether it is current.

    Lets the UI distinguish "nothing ingested yet" from "the query failed",
    which an empty table cannot.
    """
    return await MarketCoverageService(db).summary()


@router.post(
    "/sync",
    summary="Backfill any missing or stale market data",
    dependencies=[Depends(RateLimiter("market_sync", max_requests=3))],
)
async def sync_market_data(
    user: CurrentUser,
    full: bool = Query(False, description="Refetch everything, not just gaps"),
) -> dict[str, str]:
    """Queue a background sync across every configured symbol and timeframe."""
    task = sync_market_data_task.delay(full=full)
    return {
        "message": "Market data sync queued for all configured symbols and timeframes",
        "task_id": task.id,
    }


@router.get(
    "/ticker",
    summary="Get 24h ticker price statistics",
    dependencies=[Depends(RateLimiter("market_ticker", max_requests=60))],
)
async def get_ticker(
    user: CurrentUser,
    symbol: str = Query(
        ...,
        min_length=3,
        max_length=20,
        description="Symbol e.g. BTCUSDT. Required: the all-symbols form carries "
        "very high request weight against the exchange rate limit.",
    ),
) -> dict[str, Any] | list[dict[str, Any]]:
    """Fetch 24h ticker statistics for one symbol."""
    return await get_binance_client().get_ticker_24h(symbol=symbol)


@router.get(
    "/price",
    summary="Get the latest price for a symbol",
    dependencies=[Depends(RateLimiter("market_price", max_requests=120))],
)
async def get_price(
    user: CurrentUser,
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20),
) -> dict[str, Any]:
    """Fetch the last traded price."""
    return {"symbol": symbol.upper(), "price": await get_binance_client().get_price(symbol)}


@router.get(
    "/orderbook",
    summary="Get orderbook depth",
    dependencies=[Depends(RateLimiter("market_orderbook", max_requests=60))],
)
async def get_orderbook(
    user: CurrentUser,
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20),
    limit: int = Query(100, ge=5, le=1000),
) -> dict[str, Any]:
    """Fetch live orderbook depth for a symbol."""
    return await get_binance_client().get_orderbook(symbol=symbol, limit=limit)


@router.get(
    "/klines",
    response_model=list[CandleSchema],
    summary="Get historical candles from the database",
)
async def get_klines(
    user: CurrentUser,
    db: DBSession,
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20),
    timeframe: str = Query("1m"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0, description="Skip N most recent candles, for paging back"),
) -> list[CandleSchema]:
    """Query stored candles, returned oldest-first for chart rendering."""
    stmt = (
        select(Candle)
        .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
        .order_by(Candle.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    candles = list((await db.execute(stmt)).scalars().all())
    return [CandleSchema.model_validate(c) for c in reversed(candles)]


@router.post(
    "/download-history",
    summary="Trigger a historical kline download",
    dependencies=[Depends(RateLimiter("market_download", max_requests=5))],
)
async def download_history(
    data: DownloadHistoryRequest,
    user: CurrentUser,
) -> dict[str, str]:
    """Queue a background task to backfill historical OHLCV data."""
    task = download_historical_klines.delay(
        symbol=data.symbol,
        timeframe=data.timeframe,
        days=data.days,
    )
    return {
        "message": f"Historical data download queued for {data.symbol} ({data.timeframe})",
        "task_id": task.id,
    }
