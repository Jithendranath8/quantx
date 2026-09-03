"""
QuantX — Celery task registration.

The worker previously started with an empty registry: autodiscover_tasks
looks for a `tasks` submodule inside each listed package (app/workers/tasks.py),
which does not exist. Every scheduled job was rejected as unregistered, so
retention, reconciliation, derivatives ingestion, AI settlement and
resting-order fills silently never ran.

This only shows up when a worker actually starts, so it is pinned here.
"""

import pytest

from app.core.celery_app import celery_app


@pytest.mark.unit
class TestCeleryRegistry:
    """Every scheduled task must resolve to a registered callable."""

    def test_worker_modules_are_imported(self) -> None:
        """The imports list is non-empty and names real modules."""
        imports = celery_app.conf.imports
        assert imports, "no worker modules configured; the registry would be empty"

        import importlib

        for module in imports:
            importlib.import_module(module)

    def test_every_beat_entry_is_registered(self) -> None:
        """A scheduled task the worker cannot execute is worse than no schedule."""
        celery_app.loader.import_default_modules()
        registered = set(celery_app.tasks)

        missing = [
            (name, cfg["task"])
            for name, cfg in celery_app.conf.beat_schedule.items()
            if cfg["task"] not in registered
        ]
        assert not missing, f"beat schedules unregistered tasks: {missing}"

    def test_schedule_covers_the_maintenance_surface(self) -> None:
        """The jobs that keep the platform healthy are actually scheduled."""
        scheduled = {cfg["task"] for cfg in celery_app.conf.beat_schedule.values()}
        for task in (
            "app.workers.health.check_system_health",
            "app.workers.maintenance.prune_expired_data",
            "app.workers.maintenance.cleanup_revoked_tokens",
            "app.workers.maintenance.reconcile_orders",
            "app.workers.derivatives.snapshot_derivatives",
            "app.workers.ai_outcomes.settle_ai_decisions",
            "app.workers.paper_fills.process_pending_paper_orders",
        ):
            assert task in scheduled, f"{task} is not scheduled"

    def test_on_demand_tasks_are_registered(self) -> None:
        """Tasks triggered from the API resolve too."""
        celery_app.loader.import_default_modules()
        registered = set(celery_app.tasks)
        assert "app.workers.downloader.download_historical_klines" in registered
        assert "app.workers.backtest.run_backtest_task" in registered
