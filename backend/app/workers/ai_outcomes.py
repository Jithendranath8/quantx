"""
QuantX — AI Decision Settlement Worker.

Runs the forward test that turns AI win rate and expectancy from nulls into
measurements. See ``app.services.ai_outcome_service`` for the method and its
limitations.
"""

from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.services.ai_outcome_service import AIOutcomeService
from app.workers.runtime import run_async


@celery_app.task(name="app.workers.ai_outcomes.settle_ai_decisions", bind=True)
def settle_ai_decisions(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Attribute an outcome to every AI decision old enough to have resolved."""
    return run_async(_settle_ai_decisions())


async def _settle_ai_decisions() -> dict[str, int]:
    """Settle a bounded batch of pending decisions."""
    async with get_session_factory()() as session:
        return await AIOutcomeService(session).settle_pending()
