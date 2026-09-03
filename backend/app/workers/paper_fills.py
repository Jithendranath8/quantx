"""
QuantX — Paper Order Fill Worker.

Triggers resting LIMIT, STOP_LOSS and TAKE_PROFIT paper orders when the market
reaches their level. Without this task those orders would sit PENDING forever.
"""

from typing import Any

from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.services.paper_trading_service import PaperTradingService
from app.workers.runtime import run_async

logger = get_logger(__name__)


@celery_app.task(name="app.workers.paper_fills.process_pending_paper_orders", bind=True)
def process_pending_paper_orders(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Fill any resting paper orders the market has reached."""
    return run_async(_process_pending_paper_orders())


async def _process_pending_paper_orders() -> dict[str, Any]:
    """Sweep every account's pending orders once."""
    async with get_session_factory()() as session:
        result = await PaperTradingService(session).process_pending_orders()
    if result["triggered"] or result["rejected"]:
        logger.info("paper_orders_processed", **result)
    return result
