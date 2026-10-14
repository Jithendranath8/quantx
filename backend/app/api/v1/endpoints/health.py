"""
QuantX — System Health Center REST API Endpoints.

Reports the real state of every subsystem: API, database, Redis, Celery
workers, the Binance REST API, the market data stream, the AI service, the
execution engine, and the risk engine.

Every value here is measured. The previous version returned literals
("redis_cache": "CONNECTED", "celery_workers": "ACTIVE", freshness 0.4s), so
the health dashboard was structurally incapable of reporting an outage.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import get_binance_client
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DBSession
from app.core.logging import get_logger
from app.core.metrics import SYSTEM_HEALTH_GAUGE
from app.core.redis import get_redis_client
from app.models.master_models import AIDecisionLog
from app.services.risk_state_service import RiskStateService
from app.websockets.binance_stream import (
    get_stream_manager,
    is_stream_owner,
    read_stream_status,
)
from app.websockets.gateway import manager as ws_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["Health Center"])

PROBE_TIMEOUT_SECONDS = 5.0
STALE_MARKET_DATA_SECONDS = 30.0
# Window of recent AI decisions consulted when judging provider health.
AI_HEALTH_WINDOW_HOURS = 24


async def _timed(coro: Any) -> tuple[bool, float, str | None]:
    """Run a probe with a timeout, returning (ok, latency_ms, error)."""
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro, timeout=PROBE_TIMEOUT_SECONDS)
        return bool(result), (time.perf_counter() - started) * 1000, None
    except TimeoutError:
        return False, PROBE_TIMEOUT_SECONDS * 1000, "timeout"
    except Exception as exc:
        return False, (time.perf_counter() - started) * 1000, str(exc)


@router.get(
    "/stream",
    summary="Market data stream availability",
)
async def stream_status(user: CurrentUser) -> dict[str, Any]:
    """Report whether a live WebSocket subscription is worth opening.

    The frontend checks this before connecting: ingestion is off unless
    MARKET_STREAM_ENABLED is set, and a socket that will never receive a
    message is worse than not opening one.
    """
    settings = get_settings()
    # Only one worker owns the stream, so in-process metrics are zeros in every
    # other worker. Prefer the record the owner publishes to Redis and fall
    # back to local metrics when this worker is the owner (or none is running).
    shared = await read_stream_status()
    if shared is None:
        stream = get_stream_manager()
        shared = {
            "status": stream.metrics.connection_status,
            "messages_received": stream.metrics.messages_received,
            "age_seconds": stream.metrics.age_seconds,
            "candles_persisted": stream.persister.persisted_count,
            "persist_failures": stream.persister.failed_flushes,
        }
    age = shared.get("age_seconds")
    return {
        "enabled": settings.market_stream_enabled,
        "status": shared.get("status"),
        "symbols": settings.market_stream_symbol_list,
        "intervals": settings.market_stream_interval_list,
        "messages_received": shared.get("messages_received"),
        "age_seconds": None if age is None or age == float("inf") else round(age, 2),
        "active_connections": ws_manager.count,
        # Closed bars written straight from the stream. If this stays at zero
        # while messages climb, the live feed is running but the stored history
        # is not advancing -- which is what made charts lag the price ticker.
        "candles_persisted": shared.get("candles_persisted"),
        "persist_failures": shared.get("persist_failures"),
        "is_owner": is_stream_owner(),
    }


@router.get(
    "/system",
    summary="Comprehensive system health status",
)
async def system_health_center(user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Probe every subsystem and report measured status."""
    settings = get_settings()
    subsystems: dict[str, Any] = {}

    # ── Database ─────────────────────────────────────────────────────
    async def _db_probe() -> bool:
        return (await db.execute(text("SELECT 1"))).scalar() == 1

    db_ok, db_ms, db_err = await _timed(_db_probe())
    subsystems["database"] = _entry(db_ok, db_ms, db_err)

    # ── Redis ────────────────────────────────────────────────────────
    async def _redis_probe() -> bool:
        client = await get_redis_client()
        return bool(await client.ping())

    redis_ok, redis_ms, redis_err = await _timed(_redis_probe())
    subsystems["redis_cache"] = _entry(redis_ok, redis_ms, redis_err)

    # ── Celery workers (real broker ping) ────────────────────────────
    celery_ok, celery_detail = await _celery_status()
    subsystems["celery_workers"] = {
        "status": "ACTIVE" if celery_ok else "UNAVAILABLE",
        "healthy": celery_ok,
        **celery_detail,
    }

    # ── Binance REST ─────────────────────────────────────────────────
    binance_ok, binance_ms, binance_err = await _timed(get_binance_client().ping())
    subsystems["binance_rest"] = {
        **_entry(binance_ok, binance_ms, binance_err),
        "testnet": settings.binance_testnet,
    }

    # ── Market data stream freshness ─────────────────────────────────
    stream = get_stream_manager()
    shared_stream = await read_stream_status()
    if shared_stream is None:
        stream_status_label = stream.metrics.connection_status
        age = stream.metrics.age_seconds
        messages = stream.metrics.messages_received
    else:
        stream_status_label = shared_stream.get("status", "UNKNOWN")
        age = shared_stream.get("age_seconds", float("inf"))
        messages = shared_stream.get("messages_received", 0)
    stream_fresh = settings.market_stream_enabled and age <= STALE_MARKET_DATA_SECONDS
    subsystems["market_data_stream"] = {
        "status": stream_status_label,
        "healthy": stream_fresh,
        "enabled": settings.market_stream_enabled,
        "age_seconds": None if age == float("inf") else round(age, 2),
        "messages_received": messages,
        "reconnect_count": stream.metrics.reconnect_count,
    }

    # ── WebSocket gateway ────────────────────────────────────────────
    subsystems["websocket_gateway"] = {
        "status": "ONLINE",
        "healthy": True,
        "active_connections": ws_manager.count,
    }

    # ── AI service ───────────────────────────────────────────────────
    # A configured key is not a working key: it can be revoked, rate limited,
    # or out of credit. Reporting OPERATIONAL on key presence alone gives a
    # health check that cannot detect the most common real failure. The recent
    # decision log is consulted instead, which costs nothing and reflects what
    # actually happened on the last calls.
    subsystems["ai_service"] = await _ai_service_status(db, settings)

    # ── Execution engine ─────────────────────────────────────────────
    creds = bool(settings.binance_api_key and settings.binance_secret)
    subsystems["execution_engine"] = {
        "status": "READY" if creds else "NO_CREDENTIALS",
        "healthy": creds,
        "mainnet_trading_enabled": settings.mainnet_trading_enabled,
    }

    # ── Risk engine (persisted state) ────────────────────────────────
    risk_state = await RiskStateService(db).get_or_create(user.id)
    halted = risk_state.circuit_breaker_active
    subsystems["risk_engine"] = {
        "status": "CIRCUIT_BREAKER_HALT" if halted else "ACTIVE",
        "healthy": not halted,
        "reason": risk_state.circuit_breaker_reason,
        "daily_loss_usd": risk_state.daily_loss_usd,
    }

    subsystems["api_server"] = {"status": "ONLINE", "healthy": True}

    # Critical subsystems determine the overall verdict; optional ones
    # (stream, AI, exchange credentials) degrade but do not fail the system.
    critical = ["database", "redis_cache", "api_server"]
    overall_ok = all(subsystems[name]["healthy"] for name in critical)
    degraded = not all(s.get("healthy", True) for s in subsystems.values())

    SYSTEM_HEALTH_GAUGE.set(1 if overall_ok else 0)

    return {
        "status": "HEALTHY" if overall_ok and not degraded else ("DEGRADED" if overall_ok else "UNHEALTHY"),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "subsystems": subsystems,
    }


async def _ai_service_status(db: AsyncSession, settings: Any) -> dict[str, Any]:
    """Report AI availability from configuration plus recent call outcomes."""
    # A self-hosted endpoint needs no key, so key presence is not the test.
    if not settings.ai_provider_configured:
        return {
            "status": "NOT_CONFIGURED",
            "healthy": False,
            "model": settings.openai_model,
            "detail": (
                "No AI provider set. Provide OPENAI_API_KEY, or OPENAI_BASE_URL "
                "for a local or alternative OpenAI-compatible endpoint."
            ),
        }

    since = datetime.now(UTC) - timedelta(hours=AI_HEALTH_WINDOW_HOURS)
    rows = (
        await db.execute(
            select(
                func.count().label("total"),
                func.sum(
                    case((AIDecisionLog.output_decision["action"].astext == "WAIT", 1), else_=0)
                ).label("waits"),
            ).where(AIDecisionLog.timestamp >= since)
        )
    ).one()

    total = int(rows.total or 0)
    if total == 0:
        return {
            "status": "CONFIGURED",
            "healthy": True,
            "model": settings.openai_model,
            "endpoint": settings.openai_base_url or "https://api.openai.com/v1",
            "detail": "Provider configured; no decisions yet in the health window.",
        }

    # The agent degrades to WAIT on any provider error, so an all-WAIT window
    # is the signature of a key that is present but not usable.
    waits = int(rows.waits or 0)
    failing = waits == total
    return {
        "status": "DEGRADED" if failing else "OPERATIONAL",
        "healthy": not failing,
        "model": settings.openai_model,
        "endpoint": settings.openai_base_url or "https://api.openai.com/v1",
        "recent_decisions": total,
        "recent_wait_decisions": waits,
        "detail": (
            "Every recent decision was WAIT, which is what the agent returns "
            "when the provider call fails. Check the provider's status, and the "
            "key's quota if one is in use."
            if failing
            else None
        ),
    }


def _entry(ok: bool, latency_ms: float, error: str | None) -> dict[str, Any]:
    """Shape one probe result."""
    return {
        "status": "CONNECTED" if ok else "DISCONNECTED",
        "healthy": ok,
        "latency_ms": round(latency_ms, 2),
        "error": error,
    }


async def _celery_status() -> tuple[bool, dict[str, Any]]:
    """Ping Celery workers over the broker.

    ``control.ping`` is a blocking call, so it runs off the event loop.
    """
    def _ping() -> list[dict[str, Any]]:
        return celery_app.control.ping(timeout=1.0) or []

    try:
        replies = await asyncio.wait_for(asyncio.to_thread(_ping), timeout=PROBE_TIMEOUT_SECONDS)
    except Exception as exc:
        return False, {"worker_count": 0, "error": str(exc)}

    return bool(replies), {
        "worker_count": len(replies),
        "workers": [name for reply in replies for name in reply],
    }
