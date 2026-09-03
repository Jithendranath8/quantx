"""
QuantX — Derivatives Ingestion Workers.

Keeps ``funding_rates`` and ``open_interests`` populated for the configured
perpetual symbols. Without these tasks both tables stay empty and the AI agent
receives ``null`` for funding and open interest.
"""

from typing import Any

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.services.derivatives_ingest_service import DerivativesIngestService
from app.workers.runtime import run_async

logger = get_logger(__name__)


@celery_app.task(name="app.workers.derivatives.snapshot_derivatives", bind=True)
def snapshot_derivatives(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Store a current funding rate and open interest for each tracked symbol."""
    return run_async(_snapshot_derivatives())


async def _snapshot_derivatives() -> dict[str, Any]:
    """Take a point-in-time reading per configured symbol."""
    settings = get_settings()
    results: dict[str, Any] = {}
    async with get_session_factory()() as session:
        service = DerivativesIngestService(session)
        for symbol in settings.derivatives_symbol_list:
            try:
                results[symbol] = await service.snapshot_current(symbol)
            except Exception as exc:
                # One bad symbol must not abandon the rest of the list.
                logger.error("derivatives_snapshot_failed", symbol=symbol, error=str(exc))
                results[symbol] = {"error": str(exc)}
    return results


@celery_app.task(name="app.workers.derivatives.backfill_derivatives", bind=True)
def backfill_derivatives(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Backfill funding and open-interest history for each tracked symbol."""
    return run_async(_backfill_derivatives())


async def _backfill_derivatives() -> dict[str, Any]:
    """Fill any gaps left by missed snapshots or downtime."""
    settings = get_settings()
    results: dict[str, Any] = {}
    async with get_session_factory()() as session:
        service = DerivativesIngestService(session)
        for symbol in settings.derivatives_symbol_list:
            try:
                results[symbol] = {
                    "funding_rows": await service.ingest_funding_rates(
                        symbol, days=settings.derivatives_backfill_days
                    ),
                    # Binance retains only ~30 days of open-interest history,
                    # so this cannot reach further back regardless of settings.
                    "open_interest_rows": await service.ingest_open_interest(symbol),
                }
            except Exception as exc:
                logger.error("derivatives_backfill_failed", symbol=symbol, error=str(exc))
                results[symbol] = {"error": str(exc)}
    return results
