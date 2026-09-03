"""
QuantX — Health Check Worker.

Periodic task verifying PostgreSQL, Redis and the exchange API are reachable.

Probes issue real protocol-level requests. Opening a TCP socket only proves
something is listening on the port; it does not prove PostgreSQL can answer a
query or that Redis is accepting commands.
"""

from typing import Any

from sqlalchemy import text

from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.core.metrics import SYSTEM_HEALTH_GAUGE
from app.core.redis import get_redis_client
from app.services.notification_service import NotificationService
from app.workers.runtime import run_async

logger = get_logger(__name__)


@celery_app.task(name="app.workers.health.check_system_health", bind=True)
def check_system_health(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Check PostgreSQL, Redis, and Binance connectivity."""
    return run_async(_check_system_health())


async def _check_system_health() -> dict[str, Any]:
    """Run each health probe and alert if anything critical is down."""
    results: dict[str, Any] = {}

    try:
        async with get_session_factory()() as session:
            value = (await session.execute(text("SELECT 1"))).scalar()
        results["postgres"] = "healthy" if value == 1 else "unhealthy"
    except Exception as exc:
        results["postgres"] = "unhealthy"
        results["postgres_error"] = str(exc)

    try:
        client = await get_redis_client()
        results["redis"] = "healthy" if await client.ping() else "unhealthy"
    except Exception as exc:
        results["redis"] = "unhealthy"
        results["redis_error"] = str(exc)

    try:
        from app.connectors.binance_client import BinanceClient

        async with BinanceClient() as client:
            results["binance"] = "healthy" if await client.ping() else "unhealthy"
    except Exception as exc:
        results["binance"] = "unhealthy"
        results["binance_error"] = str(exc)

    results["worker"] = "healthy"

    critical_down = [
        name for name in ("postgres", "redis") if results.get(name) != "healthy"
    ]
    SYSTEM_HEALTH_GAUGE.set(0 if critical_down else 1)

    if critical_down:
        logger.error("system_health_degraded", failed=critical_down, results=results)
        await NotificationService.send_alert(
            title="QuantX health check failed",
            message=f"Unreachable critical subsystems: {', '.join(critical_down)}",
            level="CRITICAL",
        )

    return results
