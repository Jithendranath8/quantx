"""
QuantX — Maintenance Worker Tasks.

Periodic housekeeping that keeps the platform from degrading over time:
retention pruning, revoked-token cleanup, and order reconciliation.

Without these every append-only table grows forever. ``candles`` alone reaches
roughly 4.2M rows a year at 1m across eight symbols, and ``refresh_tokens``
accumulates a row per login that nothing ever deletes.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.market_data import Candle
from app.models.master_models import AIDecisionLog, EventLedger
from app.models.user import AuditLog
from app.repositories.user_repository import RefreshTokenRepository
from app.services.reconciliation_service import OrderReconciliationService
from app.workers.runtime import run_async

logger = get_logger(__name__)

# Deleting a year of rows in one statement locks the table and bloats WAL.
# Chunking keeps each transaction short.
DELETE_CHUNK_SIZE = 10_000


@celery_app.task(name="app.workers.maintenance.prune_expired_data", bind=True)
def prune_expired_data(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Delete rows past their configured retention window."""
    return run_async(_prune_expired_data())


async def _prune_expired_data() -> dict[str, int]:
    """Prune each retention-managed table in bounded chunks."""
    settings = get_settings()
    targets = [
        ("candles", Candle, Candle.timestamp, settings.retention_candles_days),
        ("event_ledger", EventLedger, EventLedger.timestamp, settings.retention_event_ledger_days),
        ("audit_logs", AuditLog, AuditLog.created_at, settings.retention_audit_log_days),
        (
            "ai_decision_logs",
            AIDecisionLog,
            AIDecisionLog.timestamp,
            settings.retention_ai_decision_log_days,
        ),
    ]

    deleted: dict[str, int] = {}
    async with get_session_factory()() as session:
        for name, model, column, retention_days in targets:
            if retention_days <= 0:
                deleted[name] = 0
                continue

            cutoff = datetime.now(UTC) - timedelta(days=retention_days)
            total = 0
            while True:
                ids = (
                    await session.execute(
                        select(model.id).where(column < cutoff)  # type: ignore[attr-defined]  # retention models declare id.limit(DELETE_CHUNK_SIZE)
                    )
                ).scalars().all()
                if not ids:
                    break
                await session.execute(delete(model).where(model.id.in_(ids)))  # type: ignore[attr-defined]  # retention models declare id
                await session.commit()
                total += len(ids)
                if len(ids) < DELETE_CHUNK_SIZE:
                    break

            deleted[name] = total
            if total:
                logger.info("retention_pruned", table=name, rows=total, cutoff=cutoff.isoformat())

    return deleted


@celery_app.task(name="app.workers.maintenance.cleanup_revoked_tokens", bind=True)
def cleanup_revoked_tokens(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Delete revoked refresh tokens and any that have simply expired."""
    return run_async(_cleanup_revoked_tokens())


async def _cleanup_revoked_tokens() -> dict[str, int]:
    """Remove revoked and expired refresh tokens."""
    async with get_session_factory()() as session:
        repo = RefreshTokenRepository(session)
        revoked = await repo.cleanup_revoked()
        expired = await repo.cleanup_expired()
        await session.commit()
    logger.info("refresh_tokens_cleaned", revoked=revoked, expired=expired)
    return {"revoked_deleted": revoked, "expired_deleted": expired}


@celery_app.task(name="app.workers.maintenance.reconcile_orders", bind=True)
def reconcile_orders(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Reconcile every open live order against the exchange."""
    return run_async(_reconcile_orders())


async def _reconcile_orders() -> dict[str, Any]:
    """Run reconciliation across all users."""
    async with get_session_factory()() as session:
        report = await OrderReconciliationService(session).reconcile_orders()
    if report["discrepancies_count"]:
        logger.warning(
            "reconciliation_discrepancies",
            count=report["discrepancies_count"],
            repaired=report["repaired_count"],
        )
    return report


@celery_app.task(name="app.workers.maintenance.table_sizes", bind=True)
def table_sizes(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Report row counts for the retention-managed tables."""
    return run_async(_table_sizes())


async def _table_sizes() -> dict[str, int]:
    """Count rows in each growth-prone table."""
    counts: dict[str, int] = {}
    async with get_session_factory()() as session:
        for name, model in (
            ("candles", Candle),
            ("event_ledger", EventLedger),
            ("audit_logs", AuditLog),
            ("ai_decision_logs", AIDecisionLog),
        ):
            counts[name] = int(
                (await session.execute(select(func.count()).select_from(model))).scalar_one()
            )
    return counts
