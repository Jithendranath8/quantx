"""
QuantX — Unit Tests for Notification Service & Prometheus Metrics.
"""

import pytest

from app.services.notification_service import NotificationService


@pytest.mark.unit
class TestNotificationService:
    """Unit tests for NotificationService alert dispatch."""

    @pytest.mark.asyncio
    async def test_send_alert(self) -> None:
        """Sending alert should return True without throwing exceptions."""
        result = await NotificationService.send_alert(
            title="Unit Test Alert",
            message="Testing notification dispatch.",
            level="INFO",
        )
        assert result is True
