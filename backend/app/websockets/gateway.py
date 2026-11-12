"""
QuantX — FastAPI WebSocket Gateway.

Exposes ``/ws/market/{symbol}`` so browser clients receive live tick updates.
Each client subscribes to the Redis pattern for its symbol and the messages are
forwarded straight through.

What this must get right:
- The PubSub object is released on every exit path. It holds a dedicated pooled
  connection, so leaking one per client permanently exhausts the Redis pool
  after ``redis_max_connections`` connect/disconnect cycles.
- Clients are authenticated like any HTTP request: a valid access token for an
  active user whose session has not been ended. The token travels in the
  ``Sec-WebSocket-Protocol`` header, never in the URL, so it is not written to
  access logs.
- A disconnect is noticed even when no tick is flowing. The handler used to
  wait only for the next tick, so a client that left a quiet symbol kept its
  slot (and, in Redis mode, a pooled connection) until a tick arrived.
- Only configured symbols can be subscribed, one user cannot take every slot,
  and a socket does not outlive the token that opened it.
"""

import asyncio
import contextlib
import time
from collections import Counter
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import DBSession, authenticate_claims
from app.core.logging import get_logger
from app.core.redis import pubsub_context
from app.core.security import verify_access_claims
from app.websockets.channels import symbol_pattern
from app.websockets.local_bus import market_bus

logger = get_logger(__name__)
router = APIRouter(tags=["WebSocket Gateway"])

MAX_CONNECTIONS = 500
MAX_CONNECTIONS_PER_USER = 10
CLIENT_SEND_TIMEOUT = 10.0
# Subprotocol the browser offers alongside its token: ``[AUTH_SUBPROTOCOL, <jwt>]``.
AUTH_SUBPROTOCOL = "quantx.bearer"


class ConnectionManager:
    """Tracks active WebSocket client connections."""

    def __init__(
        self,
        max_connections: int = MAX_CONNECTIONS,
        max_per_user: int = MAX_CONNECTIONS_PER_USER,
    ) -> None:
        self.active_connections: set[WebSocket] = set()
        self._owners: dict[WebSocket, str] = {}
        self._per_user: Counter[str] = Counter()
        self._max_connections = max_connections
        self._max_per_user = max_per_user

    @property
    def count(self) -> int:
        """Number of currently connected clients."""
        return len(self.active_connections)

    def at_capacity(self) -> bool:
        """Whether the gateway has reached its connection ceiling."""
        return len(self.active_connections) >= self._max_connections

    def user_at_capacity(self, user_id: str) -> bool:
        """Whether one user already holds their share of the gateway."""
        return self._per_user[user_id] >= self._max_per_user

    async def connect(self, websocket: WebSocket, user_id: str = "", subprotocol: str | None = None) -> None:
        """Accept and register a client."""
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.add(websocket)
        self._owners[websocket] = user_id
        self._per_user[user_id] += 1
        logger.info("websocket_client_connected", total_connections=self.count)

    def disconnect(self, websocket: WebSocket) -> None:
        """Deregister a client. Safe to call more than once."""
        if websocket in self.active_connections:
            self.active_connections.discard(websocket)
            owner = self._owners.pop(websocket, "")
            self._per_user[owner] -= 1
            if self._per_user[owner] <= 0:
                del self._per_user[owner]
            logger.info("websocket_client_disconnected", total_connections=self.count)

    async def broadcast(self, message: str) -> None:
        """Send a message to every connected client, dropping dead ones."""
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


def _offered_token(websocket: WebSocket) -> str | None:
    """The access token offered as ``Sec-WebSocket-Protocol: quantx.bearer, <jwt>``."""
    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    if len(offered) == 2 and offered[0] == AUTH_SUBPROTOCOL:
        return offered[1]
    return None


def _origin_allowed(websocket: WebSocket) -> bool:
    """Browsers always send Origin; when present it must be one we serve.

    A client that sends no Origin is not a browser page and cannot be driven by
    a third-party site, so it is judged on its token alone.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    return origin.rstrip("/") in {o.rstrip("/") for o in get_settings().allowed_origins_list}


async def _authenticate(websocket: WebSocket, db: AsyncSession) -> dict[str, Any] | None:
    """Claims of a live, authorised session, or None."""
    token = _offered_token(websocket)
    if token is None:
        return None
    try:
        claims = verify_access_claims(token)
        await authenticate_claims(claims, db)
    except Exception:
        return None
    finally:
        # The socket may stay open for a long time; the database connection
        # used to authenticate it must not.
        with contextlib.suppress(Exception):
            await db.close()
    return claims


async def _forward(websocket: WebSocket, symbol: str) -> None:
    """Relay ticks for one symbol to the client until something fails."""
    if get_settings().single_worker_mode:
        # Stream and gateway share this process: read ticks straight off the
        # in-process bus, no Redis round-trip (and no Redis quota burn).
        async with market_bus.subscribe(symbol) as queue:
            while True:
                data = await queue.get()
                await asyncio.wait_for(websocket.send_text(data), timeout=CLIENT_SEND_TIMEOUT)
    else:
        async with pubsub_context(symbol_pattern(symbol)) as pubsub:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                # A wedged client must not stall the subscription forever.
                await asyncio.wait_for(websocket.send_text(data), timeout=CLIENT_SEND_TIMEOUT)


async def _until_disconnect(websocket: WebSocket) -> None:
    """Return when the client goes away. Anything it sends is discarded."""
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            return


@router.websocket("/ws/market/{symbol}")
async def market_websocket(websocket: WebSocket, symbol: str, db: DBSession) -> None:
    """Stream real-time market data for a symbol to an authenticated client."""
    settings = get_settings()
    symbol = symbol.upper()

    claims = await _authenticate(websocket, db) if _origin_allowed(websocket) else None
    if claims is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return
    user_id = str(claims["sub"])

    # Only symbols the platform actually streams. An arbitrary string never
    # ticks, and in Redis mode it would be used as a subscription pattern.
    if symbol not in settings.market_stream_symbol_list:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown symbol")
        return

    if manager.at_capacity() or manager.user_at_capacity(user_id):
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Gateway at capacity")
        return

    await manager.connect(websocket, user_id=user_id, subprotocol=AUTH_SUBPROTOCOL)

    # The socket lives at most as long as the token that opened it; the client
    # reconnects with a fresh one.
    lifetime = max(1.0, float(claims.get("exp", 0)) - time.time())
    forward = asyncio.create_task(_forward(websocket, symbol), name=f"ws-forward-{symbol}")
    watch = asyncio.create_task(_until_disconnect(websocket), name=f"ws-watch-{symbol}")
    try:
        done, _ = await asyncio.wait({forward, watch}, timeout=lifetime, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is None or isinstance(exc, WebSocketDisconnect):
                continue
            if isinstance(exc, TimeoutError):
                logger.warning("websocket_client_send_timeout", symbol=symbol)
            else:
                logger.error("websocket_gateway_error", symbol=symbol, error=str(exc))
    finally:
        for task in (forward, watch):
            task.cancel()
        await asyncio.gather(forward, watch, return_exceptions=True)
        manager.disconnect(websocket)
        with contextlib.suppress(Exception):
            await websocket.close()


@router.websocket("/ws/health")
async def gateway_health(websocket: WebSocket) -> None:
    """Report gateway capacity without requiring a subscription."""
    await websocket.accept()
    settings = get_settings()
    await websocket.send_json(
        {
            "active_connections": manager.count,
            "max_connections": MAX_CONNECTIONS,
            "stream_enabled": settings.market_stream_enabled,
        }
    )
    await websocket.close()
