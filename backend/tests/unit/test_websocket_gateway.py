"""
QuantX — WebSocket gateway tests.

Security audit finding 8: a client that disconnected from a symbol with no
ticks kept its gateway slot until a tick arrived or the process restarted,
because the handler only ever waited for the next tick. These tests drive the
handler directly with a fake socket.
"""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User
from app.repositories.user_repository import RefreshTokenRepository
from app.websockets import gateway
from app.websockets.local_bus import market_bus


class FakeWebSocket:
    """Just enough of a Starlette WebSocket for the gateway handler."""

    def __init__(self, token: str | None, origin: str | None = None) -> None:
        self.headers: dict[str, str] = {}
        if token is not None:
            self.headers["sec-websocket-protocol"] = f"{gateway.AUTH_SUBPROTOCOL}, {token}"
        if origin is not None:
            self.headers["origin"] = origin
        self.accepted_subprotocol: str | None = None
        self.accepted = False
        self.close_code: int | None = None
        self.sent: list[str] = []
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted = True
        self.accepted_subprotocol = subprotocol

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        if self.close_code is None:
            self.close_code = code

    async def receive(self) -> dict[str, Any]:
        return await self._incoming.get()

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    def client_goes_away(self) -> None:
        self._incoming.put_nowait({"type": "websocket.disconnect", "code": 1001})


@pytest.fixture(autouse=True)
def _fresh_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway, "manager", gateway.ConnectionManager())


async def _until(condition: Any, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@pytest.mark.unit
class TestGatewayAdmission:
    @pytest.mark.asyncio
    async def test_no_token_is_refused(self, db_session: AsyncSession) -> None:
        ws = FakeWebSocket(token=None)
        await gateway.market_websocket(ws, "BTCUSDT", db_session)  # type: ignore[arg-type]
        assert ws.accepted is False and ws.close_code == 1008

    @pytest.mark.asyncio
    async def test_a_deactivated_user_is_refused(self, db_session: AsyncSession, test_user: User) -> None:
        test_user.is_active = False
        await db_session.commit()
        ws = FakeWebSocket(create_access_token(subject=str(test_user.id)))
        await gateway.market_websocket(ws, "BTCUSDT", db_session)  # type: ignore[arg-type]
        assert ws.accepted is False and ws.close_code == 1008

    @pytest.mark.asyncio
    async def test_an_ended_session_is_refused(self, db_session: AsyncSession, test_user: User) -> None:
        session_id = uuid.uuid4()
        await RefreshTokenRepository(db_session).create(test_user.id, "refresh-token", family_id=session_id)
        await RefreshTokenRepository(db_session).revoke_all_for_user(test_user.id)
        await db_session.commit()
        token = create_access_token(subject=str(test_user.id), extra_claims={"sid": str(session_id)})
        ws = FakeWebSocket(token)
        await gateway.market_websocket(ws, "BTCUSDT", db_session)  # type: ignore[arg-type]
        assert ws.accepted is False and ws.close_code == 1008

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["NOTASYMBOL", "*", "BTCUSDT:*", "A" * 5000])
    async def test_only_streamed_symbols_can_be_subscribed(
        self, db_session: AsyncSession, test_user: User, symbol: str
    ) -> None:
        ws = FakeWebSocket(create_access_token(subject=str(test_user.id)))
        await gateway.market_websocket(ws, symbol, db_session)  # type: ignore[arg-type]
        assert ws.accepted is False and ws.close_code == 1008
        assert market_bus.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_a_foreign_origin_is_refused(self, db_session: AsyncSession, test_user: User) -> None:
        ws = FakeWebSocket(create_access_token(subject=str(test_user.id)), origin="https://evil.example")
        await gateway.market_websocket(ws, "BTCUSDT", db_session)  # type: ignore[arg-type]
        assert ws.accepted is False and ws.close_code == 1008


@pytest.mark.unit
class TestGatewayLifecycle:
    @pytest.mark.asyncio
    async def test_a_disconnect_on_a_quiet_symbol_frees_the_slot(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Finding 8: no tick ever arrives, yet the slot is released when the client leaves."""
        ws = FakeWebSocket(create_access_token(subject=str(test_user.id)))
        handler = asyncio.create_task(gateway.market_websocket(ws, "BTCUSDT", db_session))  # type: ignore[arg-type]
        await _until(lambda: gateway.manager.count == 1 and market_bus.subscriber_count == 1)
        assert ws.accepted_subprotocol == gateway.AUTH_SUBPROTOCOL

        ws.client_goes_away()
        await asyncio.wait_for(handler, timeout=2.0)

        assert gateway.manager.count == 0
        assert market_bus.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_ticks_are_forwarded_while_connected(self, db_session: AsyncSession, test_user: User) -> None:
        ws = FakeWebSocket(create_access_token(subject=str(test_user.id)))
        handler = asyncio.create_task(gateway.market_websocket(ws, "BTCUSDT", db_session))  # type: ignore[arg-type]
        await _until(lambda: market_bus.subscriber_count == 1)

        market_bus.publish("BTCUSDT", '{"event_type":"trade"}')
        await _until(lambda: ws.sent == ['{"event_type":"trade"}'])

        ws.client_goes_away()
        await asyncio.wait_for(handler, timeout=2.0)

    @pytest.mark.asyncio
    async def test_one_user_cannot_take_every_slot(
        self, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gateway, "manager", gateway.ConnectionManager(max_per_user=1))
        token = create_access_token(subject=str(test_user.id))
        first = FakeWebSocket(token)
        handler = asyncio.create_task(gateway.market_websocket(first, "BTCUSDT", db_session))  # type: ignore[arg-type]
        await _until(lambda: gateway.manager.count == 1)

        second = FakeWebSocket(token)
        await gateway.market_websocket(second, "BTCUSDT", db_session)  # type: ignore[arg-type]
        assert second.accepted is False and second.close_code == 1013

        first.client_goes_away()
        await asyncio.wait_for(handler, timeout=2.0)

    @pytest.mark.asyncio
    async def test_a_socket_does_not_outlive_its_token(
        self, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        ws = FakeWebSocket(create_access_token(subject=str(test_user.id)))
        real = gateway.verify_access_claims
        monkeypatch.setattr(gateway, "verify_access_claims", lambda t: {**real(t), "exp": time.time() + 1.2})

        await asyncio.wait_for(gateway.market_websocket(ws, "BTCUSDT", db_session), timeout=4.0)  # type: ignore[arg-type]

        assert ws.accepted is True and gateway.manager.count == 0
