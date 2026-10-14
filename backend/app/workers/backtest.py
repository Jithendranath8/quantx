"""
QuantX — Celery Worker for Asynchronous Backtesting.
"""

from typing import Any

from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import BacktestService
from app.workers.runtime import run_async


@celery_app.task(name="app.workers.backtest.run_backtest_task", bind=True)
def run_backtest_task(self, req_dict: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Run a backtest in the background and return the serialized result."""

    async def _run() -> dict[str, Any]:
        req = BacktestRequest.model_validate(req_dict)
        async with get_session_factory()() as session:
            service = BacktestService(session)
            result = await service.run_backtest(req)
            return result.model_dump(mode="json")

    # Uses the worker's persistent event loop rather than asyncio.run(), which
    # would close the loop the connection pool is bound to.
    return run_async(_run())
