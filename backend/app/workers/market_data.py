"""
QuantX — Market Data Sync Worker.

Keeps stored candles complete and current for every symbol and timeframe the
platform advertises. Without this, only whatever was manually downloaded once
ever has data, and most of the UI renders empty tables.
"""

from typing import Any

from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.services.market_coverage_service import MarketCoverageService
from app.workers.runtime import run_async

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.market_data.sync_market_data",
    bind=True,
    # A full cold-start backfill across 48 pairs takes minutes.
    time_limit=3600,
    soft_time_limit=3300,
)
def sync_market_data(self, full: bool = False) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Backfill or top up every configured symbol/timeframe pair.

    Args:
        full: Refetch everything rather than only what is missing or stale.
    """
    return run_async(_sync_market_data(full=full))


async def _sync_market_data(full: bool = False) -> dict[str, Any]:
    """Run the coverage sync against a worker-owned session."""
    async with get_session_factory()() as session:
        result = await MarketCoverageService(session).sync(only_missing_or_stale=not full)
    # Trim the per-pair detail; the full list is available from the API.
    result.pop("details", None)
    return result


@celery_app.task(name="app.workers.market_data.report_coverage", bind=True)
def report_coverage(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Report which symbol/timeframe pairs are missing or stale."""
    return run_async(_report_coverage())


async def _report_coverage() -> dict[str, Any]:
    """Summarize coverage completeness."""
    async with get_session_factory()() as session:
        summary = await MarketCoverageService(session).summary()
    summary.pop("coverage", None)
    if summary["pairs_missing"] or summary["pairs_stale"]:
        logger.warning(
            "market_data_incomplete",
            missing=summary["pairs_missing"], stale=summary["pairs_stale"],
        )
    return summary
