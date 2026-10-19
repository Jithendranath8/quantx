"""
QuantX — Binance WebSocket Ingestion.

Connects to Binance combined streams, normalizes each message, and republishes
it onto Redis Pub/Sub for the gateway to fan out to browser clients.

Started from the FastAPI lifespan when ``MARKET_STREAM_ENABLED=true``. Before,
this class existed but had no call site anywhere, so the entire live data path
was dead code.
"""

import asyncio
import contextlib
import json
from typing import Any, cast

import websockets
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.websockets.candle_persister import CandlePersister
from app.websockets.channels import channel_for_event
from app.websockets.local_bus import market_bus
from app.websockets.market_data_engine import (
    MarketDataMetrics,
    MarketDataNormalizer,
    MarketDataValidator,
    market_cache,
)
from app.websockets.stream_leader import StreamLeader

logger = get_logger(__name__)

MAX_BACKOFF_SECONDS = 60.0
PING_INTERVAL_SECONDS = 20.0


class BinanceStreamManager:
    """Manages a Binance combined-stream connection with auto-reconnect."""

    WS_BASE_URL = "wss://stream.binance.com:9443/stream"
    # The testnet WebSocket lives on stream.testnet.binance.vision, NOT on
    # testnet.binance.vision (which serves the REST API and answers 404 to a
    # WebSocket upgrade). Getting this wrong makes the stream reconnect-loop
    # forever with zero messages while reporting itself as merely
    # "RECONNECTING".
    WS_TESTNET_URL = "wss://stream.testnet.binance.vision/stream"

    # Partial order-book depth feed for live microstructure: top N levels pushed
    # every SPEED ms. This is what makes the imbalance/microprice real-time
    # rather than a periodic REST snapshot.
    DEPTH_LEVELS = 20
    DEPTH_SPEED_MS = 100

    def __init__(
        self,
        symbols: list[str] | None = None,
        intervals: list[str] | None = None,
    ) -> None:
        settings = get_settings()
        self.symbols = [s.upper() for s in (symbols or settings.market_stream_symbol_list)]
        self.intervals = intervals or settings.market_stream_interval_list
        # Live data is read-only public info; use the geo-free public mirror
        # regardless of BINANCE_TESTNET (the testnet feed is thin and stalls).
        self.base_url = settings.binance_market_ws_url
        # One-process deploy: fan ticks out in-process instead of via Redis.
        self._single_worker = settings.single_worker_mode
        self.metrics = MarketDataMetrics()
        # Closed candles go to the database as they arrive; without this the
        # candles table only advances when the ten-minute REST sync runs.
        self.persister = CandlePersister()

        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def stream_url(self) -> str:
        """Combined-stream URL: a kline stream per (symbol, interval) plus a
        partial order-book depth stream per symbol for live microstructure."""
        klines = [
            f"{symbol.lower()}@kline_{interval}"
            for symbol in self.symbols
            for interval in self.intervals
        ]
        depth = [
            f"{symbol.lower()}@depth{self.DEPTH_LEVELS}@{self.DEPTH_SPEED_MS}ms"
            for symbol in self.symbols
        ]
        return f"{self.base_url}?streams={'/'.join(klines + depth)}"

    async def start(self) -> None:
        """Start consuming the Binance stream in the background."""
        if self._running or not self.symbols:
            return
        self._running = True
        await self.persister.start()
        self._task = asyncio.create_task(self._listen_loop(), name="binance-stream")
        logger.info(
            "binance_stream_started",
            symbols=self.symbols,
            intervals=self.intervals,
        )

    async def stop(self) -> None:
        """Stop consuming and await task teardown."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.persister.stop()
        self.metrics.connection_status = "DISCONNECTED"
        logger.info("binance_stream_stopped", symbols=self.symbols)

    async def _listen_loop(self) -> None:
        """Reconnecting consume loop with exponential backoff."""
        # In single-worker mode ticks never touch Redis, so do not hold a client.
        redis = None if self._single_worker else await get_redis_client()
        backoff = 1.0

        while self._running:
            try:
                self.metrics.connection_status = "CONNECTING"
                async with websockets.connect(
                    self.stream_url,
                    ping_interval=PING_INTERVAL_SECONDS,
                    ping_timeout=PING_INTERVAL_SECONDS,
                    max_queue=256,
                ) as ws:
                    self.metrics.connection_status = "CONNECTED"
                    backoff = 1.0
                    logger.info("binance_websocket_connected", symbols=self.symbols)

                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(redis, message)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.metrics.connection_status = "RECONNECTING"
                self.metrics.reconnect_count += 1
                logger.error("binance_stream_error", error=str(e), backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

        self.metrics.connection_status = "DISCONNECTED"

    async def _handle_message(self, redis: object, message: str | bytes) -> None:
        """Normalize, validate, cache and republish one stream message."""
        try:
            envelope = json.loads(message)
        except (ValueError, TypeError):
            logger.warning("binance_stream_unparseable_message")
            return

        # Combined streams wrap the payload; single streams do not. The stream
        # key names the symbol for partial-depth events that lack their own.
        raw = envelope.get("data", envelope)
        stream_name = envelope.get("stream", "") if isinstance(envelope, dict) else ""

        event = MarketDataNormalizer.normalize(raw, stream_name)
        if event is None or not event.get("symbol"):
            return

        if event["event_type"] == "kline" and not MarketDataValidator.validate_candle(event):
            logger.warning("binance_stream_invalid_candle", symbol=event.get("symbol"))
            return

        self.metrics.observe(float(event.get("timestamp", 0) or 0))
        market_cache.update(event)

        # Store the bar the moment it closes, so the candles table is as
        # current as the price ticker beside it.
        await self.persister.offer(event)

        payload = json.dumps(event)
        if self._single_worker:
            # Same process as the gateway: hand the tick over directly, no Redis.
            market_bus.publish(event["symbol"], payload)
            return

        channel = channel_for_event(
            event["symbol"], event["event_type"], event.get("interval")
        )
        try:
            await redis.publish(channel, payload)  # type: ignore[attr-defined]
        except Exception as e:
            logger.error("binance_stream_publish_failed", channel=channel, error=str(e))


# Process-wide stream manager, started and stopped by the application lifespan.
_stream_manager: BinanceStreamManager | None = None


def get_stream_manager() -> BinanceStreamManager:
    """Get the shared stream manager, creating it on first use."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = BinanceStreamManager()
    return _stream_manager


_leader: StreamLeader | None = None


async def _start_owned_stream() -> None:
    await get_stream_manager().start()


async def _stop_owned_stream() -> None:
    global _stream_manager
    if _stream_manager is not None:
        await _stream_manager.stop()
        _stream_manager = None
    # Only the multi-worker path publishes a Redis status record to clear.
    if not get_settings().single_worker_mode:
        with contextlib.suppress(Exception):
            redis = await get_redis_client()
            await redis.delete(STATUS_KEY)


async def start_market_stream() -> None:
    """Campaign to own ingestion, starting it only if this worker wins.

    The lifespan runs in every uvicorn worker. Without the election each worker
    would hold its own Binance socket and write the same candles, multiplying
    upstream connections and database load by the worker count.
    """
    global _leader
    settings = get_settings()
    if not settings.market_stream_enabled:
        logger.info("market_stream_disabled")
        return
    if settings.single_worker_mode:
        # One process owns ingestion unconditionally — no Redis lock to renew.
        logger.info("market_stream_single_worker")
        await _start_owned_stream()
        return
    if _leader is None:
        _leader = StreamLeader(
            _start_owned_stream, _stop_owned_stream, on_heartbeat=publish_stream_status
        )
    await _leader.start()


async def stop_market_stream() -> None:
    """Stop ingestion and give up ownership so another worker can take over."""
    global _leader
    if _leader is not None:
        await _leader.stop()
        _leader = None
    else:
        await _stop_owned_stream()


STATUS_KEY = "quantx:stream:status"
# Comfortably longer than the publish interval so a brief hiccup does not blank
# the status, short enough that a dead owner's numbers do not linger.
STATUS_TTL_SECONDS = 30
STATUS_PUBLISH_INTERVAL_SECONDS = 5.0


async def publish_stream_status() -> None:
    """Write the owner's live metrics to Redis.

    Health requests land on an arbitrary worker, and only one worker owns the
    stream. Reading in-process metrics therefore reported zeros three times out
    of four. The owner publishes; every worker reads the same record.
    """
    if _stream_manager is None:
        return
    payload = {
        "status": _stream_manager.metrics.connection_status,
        "messages_received": _stream_manager.metrics.messages_received,
        "age_seconds": _stream_manager.metrics.age_seconds,
        "candles_persisted": _stream_manager.persister.persisted_count,
        "persist_failures": _stream_manager.persister.failed_flushes,
        "owner": _leader.token if _leader is not None else "",
    }
    with contextlib.suppress(Exception):
        redis = await get_redis_client()
        await redis.set(STATUS_KEY, json.dumps(payload), ex=STATUS_TTL_SECONDS)


async def read_stream_status() -> dict[str, Any] | None:
    """Read the owner-published metrics, or None if no owner is reporting."""
    # Single-worker deploys never publish to Redis; the health endpoints fall
    # back to this process's own live metrics, which are the authoritative ones.
    if get_settings().single_worker_mode:
        return None
    try:
        redis = await get_redis_client()
        raw = await redis.get(STATUS_KEY)
    except Exception:
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    with contextlib.suppress(ValueError):
        return cast("dict[str, Any]", json.loads(raw))
    return None


def is_stream_owner() -> bool:
    """Whether this worker currently owns ingestion."""
    return _leader is not None and _leader.is_leader
