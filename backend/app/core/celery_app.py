"""
QuantX — Celery Application.

Configures Celery for background task processing using Redis as broker.
Handles historical data downloads, periodic analytics, retention pruning,
reconciliation, and notifications.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "quantx",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Redelivery window for acks_late; must exceed the hard time limit or a
    # long task is handed to a second worker while the first is still running.
    broker_transport_options={"visibility_timeout": 3900},
    result_backend_transport_options={"visibility_timeout": 3900},

    # Result expiration
    result_expires=86400,  # 24 hours

    # Retry
    task_default_retry_delay=60,
    task_max_retries=3,

    # Beat schedule (periodic tasks)
    beat_schedule={
        "health-check-every-5-min": {
            "task": "app.workers.health.check_system_health",
            "schedule": 300.0,
        },
        "reconcile-orders-every-15-min": {
            "task": "app.workers.maintenance.reconcile_orders",
            "schedule": 900.0,
        },
        # Keeps every configured symbol/timeframe current. Only missing or
        # stale pairs are fetched, so the steady-state cost is small.
        "sync-market-data-every-10-min": {
            "task": "app.workers.market_data.sync_market_data",
            "schedule": 600.0,
        },
        # Funding publishes every 8 hours; open interest moves continuously.
        # Half-hourly snapshots keep the AI agent's context fresh without
        # meaningful request-weight cost.
        "snapshot-derivatives-every-30-min": {
            "task": "app.workers.derivatives.snapshot_derivatives",
            "schedule": 1800.0,
        },
        "backfill-derivatives-daily": {
            "task": "app.workers.derivatives.backfill_derivatives",
            "schedule": crontab(hour=4, minute=15),
        },
        # Resting paper orders are checked frequently; a stop that triggers
        # ten minutes late is not a simulation of anything useful.
        "process-pending-paper-orders-every-minute": {
            "task": "app.workers.paper_fills.process_pending_paper_orders",
            "schedule": 60.0,
        },
        "settle-ai-decisions-hourly": {
            "task": "app.workers.ai_outcomes.settle_ai_decisions",
            "schedule": 3600.0,
        },
        "prune-expired-data-daily": {
            "task": "app.workers.maintenance.prune_expired_data",
            "schedule": crontab(hour=3, minute=30),
        },
        "cleanup-revoked-tokens-daily": {
            "task": "app.workers.maintenance.cleanup_revoked_tokens",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)

# Task modules are imported explicitly rather than auto-discovered.
#
# autodiscover_tasks(["app.workers"]) looks for a `tasks` submodule inside each
# listed package -- i.e. app/workers/tasks.py -- which does not exist here. The
# worker therefore started with an EMPTY task registry and rejected every
# scheduled job as unregistered, silently disabling retention, reconciliation,
# derivatives ingestion, AI settlement and resting-order fills.
#
# Keep this list in sync when adding a worker module; a missing entry is caught
# by test_celery_registry.py.
celery_app.conf.imports = (
    "app.workers.ai_outcomes",
    "app.workers.market_data",
    "app.workers.backtest",
    "app.workers.derivatives",
    "app.workers.downloader",
    "app.workers.health",
    "app.workers.maintenance",
    "app.workers.paper_fills",
)
