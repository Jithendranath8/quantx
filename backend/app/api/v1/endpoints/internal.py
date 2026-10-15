"""
QuantX — Internal scheduled-jobs endpoint.

Runs a periodic maintenance job on demand, so a free external scheduler (a
GitHub Actions cron, Cloud Scheduler, cron-job.org, …) can stand in for an
always-on Celery worker when the platform is deployed on a free tier that does
not offer background workers.

Security: the endpoint is machine-to-machine, gated by a shared ``CRON_SECRET``
compared in constant time. It is disabled entirely when ``CRON_SECRET`` is unset
(returns 503), so a deployment that forgets to set it cannot be triggered
anonymously. Each job reuses the same async service code the Celery tasks call.
"""

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import get_settings
from app.workers.ai_outcomes import _settle_ai_decisions
from app.workers.derivatives import _snapshot_derivatives
from app.workers.health import _check_system_health
from app.workers.maintenance import _cleanup_revoked_tokens, _prune_expired_data, _reconcile_orders
from app.workers.market_data import _report_coverage, _sync_market_data
from app.workers.paper_fills import _process_pending_paper_orders

router = APIRouter(prefix="/internal", tags=["Internal"])

# Name → the async job it runs. These are the same coroutines the Celery beat
# schedule invokes; exposing them here lets an external cron drive them directly.
_JOBS: dict[str, Callable[..., Awaitable[Any]]] = {
    "paper_fills": _process_pending_paper_orders,
    "reconcile": _reconcile_orders,
    "settle_ai": _settle_ai_decisions,
    "market_sync": _sync_market_data,
    "derivatives_snapshot": _snapshot_derivatives,
    "coverage": _report_coverage,
    "health": _check_system_health,
    "prune": _prune_expired_data,
    "cleanup_tokens": _cleanup_revoked_tokens,
}


@router.post(
    "/jobs/{job_name}",
    summary="Run a scheduled maintenance job (cron-triggered)",
    description=(
        "Runs one periodic maintenance job. Intended for an external scheduler on free "
        "deployments without an always-on worker. Requires the X-Cron-Secret header to match "
        "CRON_SECRET; the endpoint is disabled when CRON_SECRET is unset."
    ),
)
async def run_scheduled_job(
    job_name: str,
    x_cron_secret: str = Header(default=""),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduled-jobs endpoint is disabled (CRON_SECRET is not set).",
        )
    if not hmac.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret.")

    job = _JOBS.get(job_name)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown job {job_name!r}. Available: {', '.join(_JOBS)}",
        )

    result = await job()
    return {"job": job_name, "result": result}
