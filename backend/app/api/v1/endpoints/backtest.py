"""
QuantX — Backtest API Endpoints.

Synchronous runs are dispatched to the threadpool by the service; long runs
should use the queue endpoint so they execute in a Celery worker instead.
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.schemas.backtest import BacktestRequest, BacktestResult
from app.services.backtest_service import BacktestService
from app.workers.backtest import run_backtest_task

router = APIRouter(prefix="/backtest", tags=["Backtesting Engine"])


@router.post(
    "/run",
    response_model=BacktestResult,
    summary="Run a backtest simulation",
    dependencies=[Depends(RateLimiter("backtest_run", max_requests=10))],
)
async def run_backtest(
    req: BacktestRequest,
    user: CurrentUser,
    db: DBSession,
) -> BacktestResult:
    """Run a backtest and return full performance metrics."""
    return await BacktestService(db).run_backtest(req)


@router.post(
    "/queue",
    summary="Queue an asynchronous backtest in Celery",
    dependencies=[Depends(RateLimiter("backtest_queue", max_requests=20))],
)
async def queue_backtest(req: BacktestRequest, user: CurrentUser) -> dict[str, Any]:
    """Queue a backtest job for a background worker."""
    task = run_backtest_task.delay(req.model_dump(mode="json"))
    return {
        "message": f"Backtest queued for {req.symbol} ({req.strategy_name})",
        "task_id": task.id,
    }
