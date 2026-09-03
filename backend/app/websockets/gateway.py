"""
QuantX — FastAPI WebSocket Gateway.

Exposes ``/ws/market/{symbol}`` so browser clients receive live tick updates.
Each client subscribes to the Redis pattern for its symbol and the messages are
forwarded straight through.

Two things this must get right:
- The PubSub object is released on every exit path. It holds a dedicated pooled
  connection, so leaking one per client permanently exhausts the Redis pool
  after ``redis_max_connections`` connect/disconnect cycles.
- Clients are authenticated. WebSocket routes do not go through the HTTP
  dependency chain, so the token is taken from a query parameter and verified
  explicitly.
"""

import asyncio
import contextlib

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import pubsub_context
from app.core.security import verify_access_token
from app.websockets.channels import symbol_pattern

logger = get_logger(__name__)
router = APIRouter(tags=["WebSocket Gateway"])

MAX_CONNECTIONS = 500
CLIENT_SEND_TIMEOUT = 10.0


class ConnectionManager:
    """Tracks active WebSocket client connections."""

    def __init__(self, max_connections: int = MAX_CONNECTIONS) -> None:
        self.active_connections: set[WebSocket] = set()
        self._max_connections = max_connections

    @property
    def count(self) -> int:
        """Number of currently connected clients."""
        return len(self.active_connections)

    def at_capacity(self) -> bool:
        """Whether the gateway has reached its connection ceiling."""
        return len(self.active_connections) >= self._max_connections

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a client."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("websocket_client_connected", total_connections=self.count)

    def disconnect(self, websocket: WebSocket) -> None:
        """Deregister a client. Safe to call more than once."""
        if websocket in self.active_connections:
            self.active_connections.discard(websocket)
            logger.info("websocket_client_disconnected", total_connections=self.count)

    async def broadcast(self, message: str) -> None:
        """Send a message to every connected client, dropping dead ones."""
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


@router.websocket("/ws/market/{symbol}")
async def market_websocket(
    websocket: WebSocket,
    symbol: str,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """Stream real-time market data for a symbol to an authenticated client."""
    try:
        verify_access_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    if manager.at_capacity():
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Gateway at capacity")
        return

    pattern = symbol_pattern(symbol)
    await manager.connect(websocket)

    try:
        async with pubsub_context(pattern) as pubsub:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                # A wedged client must not stall the subscription forever.
                await asyncio.wait_for(websocket.send_text(data), timeout=CLIENT_SEND_TIMEOUT)
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        logger.warning("websocket_client_send_timeout", symbol=symbol)
    except Exception as e:
        logger.error("websocket_gateway_error", symbol=symbol, error=str(e))
    finally:
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
