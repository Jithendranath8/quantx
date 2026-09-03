"""
QuantX — Celery Worker for Historical Data Downloads.
"""

from typing import Any

from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.services.historical_downloader import HistoricalDownloaderService
from app.workers.runtime import run_async


@celery_app.task(name="app.workers.downloader.download_historical_klines", bind=True)
def download_historical_klines(  # type: ignore[no-untyped-def]
    self,
    symbol: str,
    timeframe: str,
    days: int = 30,
) -> dict[str, Any]:
    """Backfill historical klines for a symbol and timeframe."""

    async def _run() -> int:
        async with get_session_factory()() as session:
            downloader = HistoricalDownloaderService(session)
            return await downloader.download_history(
                symbol=symbol, timeframe=timeframe, days=days
            )

    total_count = run_async(_run())
    return {
        "status": "completed",
        "symbol": symbol,
        "timeframe": timeframe,
        "total_candles": total_count,
    }
