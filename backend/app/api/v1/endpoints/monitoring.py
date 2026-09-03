"""
QuantX — Monitoring & Alerting API Endpoints.

Prometheus metrics are exposed by the instrumentator at the app root; this
router no longer registers a second ``/metrics`` and no longer shadows the
application's ``/health``.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import RateLimiter, SuperUser
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/monitoring", tags=["Monitoring & System Health"])


@router.post(
    "/notifications/test",
    summary="Send a test alert notification",
    dependencies=[Depends(RateLimiter("notification_test", max_requests=5))],
)
async def test_notification(admin: SuperUser) -> dict[str, str | bool]:
    """Dispatch a test alert to verify webhook and Telegram delivery.

    Superuser-only and rate limited: it makes outbound requests to a
    configured third party.
    """
    delivered = await NotificationService.send_alert(
        title="QuantX Health Alert",
        message="System operational test notification delivered successfully.",
        level="INFO",
    )
    return {
        "message": "Test notification dispatched",
        "all_channels_delivered": delivered,
    }
