"""
QuantX — Notification & Alerting Service.

Sends real-time trade execution alerts and risk circuit breaker notifications
via Webhook and Telegram.
"""

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class NotificationService:
    """Service broadcasting notifications for trade fills and risk alerts."""

    @staticmethod
    async def send_alert(title: str, message: str, level: str = "INFO") -> bool:
        """Send notification via Webhook and/or Telegram.

        Delivery is best effort: an unreachable webhook must never break the
        trading action that triggered the alert. Returns True when every
        configured channel accepted the message.

        Args:
            title: Alert headline.
            message: Detailed alert body.
            level: INFO, WARNING, or CRITICAL.
        """
        settings = get_settings()
        payload = {
            "title": title,
            "message": message,
            "level": level,
            "platform": "QuantX Trading Engine",
        }

        if level == "CRITICAL":
            logger.critical("notification_sent", title=title, msg=message)
        elif level == "WARNING":
            logger.warning("notification_sent", title=title, msg=message)
        else:
            logger.info("notification_sent", title=title, msg=message)

        tasks = []
        if settings.alert_webhook_url:
            tasks.append(NotificationService._post_webhook(settings.alert_webhook_url, payload))
        if settings.telegram_bot_token and settings.telegram_chat_id:
            tasks.append(
                NotificationService._post_telegram(
                    settings.telegram_bot_token,
                    settings.telegram_chat_id,
                    f"<b>[{level}] {title}</b>\n{message}",
                )
            )

        if not tasks:
            return True

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(r is True for r in results)

    @staticmethod
    async def _post_webhook(url: str, payload: dict[str, Any]) -> bool:
        """POST the alert payload to the configured webhook."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            return True
        except Exception as e:
            logger.error("webhook_dispatch_failed", error=str(e))
            return False

    @staticmethod
    async def _post_telegram(token: str, chat_id: str, text: str) -> bool:
        """Send the alert as an HTML Telegram message."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                )
                response.raise_for_status()
            return True
        except Exception as e:
            logger.error("telegram_dispatch_failed", error=str(e))
            return False
