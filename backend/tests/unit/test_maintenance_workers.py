"""
QuantX — Unit Tests for maintenance workers.

Retention pruning, refresh-token cleanup, and reconciliation. Without these
tasks every append-only table grows forever: candles alone reach roughly 4.2M
rows a year at 1m across eight symbols.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.live_trading import LiveOrder
from app.models.market_data import Candle
from app.models.master_models import EventLedger
from app.models.user import RefreshToken, User
from app.repositories.user_repository import RefreshTokenRepository
from app.services.reconciliation_service import OrderReconciliationService
from app.workers import maintenance


def candle(symbol: str, when: datetime) -> Candle:
    """Build a candle at a specific timestamp."""
    return Candle(
        symbol=symbol,
        timeframe="1h",
        timestamp=when,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
        close_time=when + timedelta(minutes=59),
        quote_volume=15.0,
        trades_count=5,
        is_closed=True,
    )


@pytest.mark.unit
class TestRetentionPruning:
    """Rows past the retention window are deleted in bounded chunks."""

    @pytest.mark.asyncio
    async def test_prunes_only_rows_past_the_cutoff(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Old candles go; recent ones stay."""
        now = datetime.now(UTC)
        db_session.add_all(
            [
                candle("OLDPAIR", now - timedelta(days=500)),
                candle("OLDPAIR", now - timedelta(days=450)),
                candle("NEWPAIR", now - timedelta(days=1)),
            ]
        )
        db_session.add(
            EventLedger(
                event_id=f"EVT-{uuid.uuid4().hex[:8]}",
                timestamp=now - timedelta(days=500),
                source="TEST",
                event_type="OLD",
                payload={},
            )
        )
        await db_session.commit()

        # Point the worker at the test session instead of a real engine.
        monkeypatch.setattr(
            maintenance, "get_session_factory", lambda: lambda: _SessionCtx(db_session)
        )
        deleted = await maintenance._prune_expired_data()

        assert deleted["candles"] == 2
        assert deleted["event_ledger"] == 1

        remaining = (
            await db_session.execute(select(func.count()).select_from(Candle))
        ).scalar_one()
        assert remaining == 1

    @pytest.mark.asyncio
    async def test_zero_retention_disables_pruning(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retention of 0 means keep everything."""
        db_session.add(candle("KEEPME", datetime.now(UTC) - timedelta(days=5000)))
        await db_session.commit()

        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "retention_candles_days", 0)
        monkeypatch.setattr(
            maintenance, "get_session_factory", lambda: lambda: _SessionCtx(db_session)
        )

        deleted = await maintenance._prune_expired_data()
        assert deleted["candles"] == 0

    @pytest.mark.asyncio
    async def test_table_sizes_reports_counts(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Row counts are reported for the growth-prone tables."""
        db_session.add(candle("SIZED", datetime.now(UTC)))
        await db_session.commit()
        monkeypatch.setattr(
            maintenance, "get_session_factory", lambda: lambda: _SessionCtx(db_session)
        )
        counts = await maintenance._table_sizes()
        assert counts["candles"] >= 1
        assert set(counts) == {"candles", "event_ledger", "audit_logs", "ai_decision_logs"}


@pytest.mark.unit
class TestRefreshTokenCleanup:
    """Revoked and expired tokens are removed.

    cleanup_revoked existed but had no caller, so refresh_tokens accumulated a
    row per login forever.
    """

    @pytest.mark.asyncio
    async def test_removes_revoked_and_expired(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Both revoked and aged-out tokens are deleted; live ones survive."""
        now = datetime.now(UTC)
        db_session.add_all(
            [
                RefreshToken(
                    user_id=test_user.id,
                    token_hash="a" * 64,
                    expires_at=now + timedelta(days=7),
                    is_revoked=True,
                ),
                RefreshToken(
                    user_id=test_user.id,
                    token_hash="b" * 64,
                    expires_at=now - timedelta(days=1),
                    is_revoked=False,
                ),
                RefreshToken(
                    user_id=test_user.id,
                    token_hash="c" * 64,
                    expires_at=now + timedelta(days=7),
                    is_revoked=False,
                ),
            ]
        )
        await db_session.commit()

        repo = RefreshTokenRepository(db_session)
        assert await repo.cleanup_revoked() == 1
        assert await repo.cleanup_expired() == 1
        await db_session.commit()

        remaining = (
            await db_session.execute(select(func.count()).select_from(RefreshToken))
        ).scalar_one()
        assert remaining == 1

    @pytest.mark.asyncio
    async def test_expired_token_is_not_accepted(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """An aged-out token cannot be looked up even before cleanup runs."""
        repo = RefreshTokenRepository(db_session)
        await repo.create(
            test_user.id, "expired-token", expires_at=datetime.now(UTC) - timedelta(days=1)
        )
        await db_session.commit()
        assert await repo.find_by_token("expired-token") is None


@pytest.mark.unit
class TestReconciliation:
    """Local order state is cross-checked against the exchange."""

    @pytest.mark.asyncio
    async def test_status_mismatch_is_detected_and_repaired(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A locally-open order that the exchange filled is corrected."""
        db_session.add(
            LiveOrder(
                user_id=test_user.id,
                client_order_id="qx-recon-1",
                exchange_order_id="555",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=1.0,
                status="NEW",
            )
        )
        await db_session.commit()

        class Client:
            async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
                return [
                    {
                        "clientOrderId": "qx-recon-1",
                        "orderId": 555,
                        "status": "PARTIALLY_FILLED",
                        "executedQty": "0.4",
                    }
                ]

            async def get_order(self, symbol: str, order_id: object) -> dict:
                return {"status": "PARTIALLY_FILLED", "executedQty": "0.4"}

        report = await OrderReconciliationService(db_session, client=Client()).reconcile_orders()
        assert report["status"] == "DISCREPANCY_DETECTED"
        assert report["repaired_count"] == 1
        assert report["mismatches"][0]["type"] == "STATUS_MISMATCH"

    @pytest.mark.asyncio
    async def test_unreachable_symbol_does_not_produce_false_findings(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A failed exchange query yields no conclusion, not a false mismatch."""
        db_session.add(
            LiveOrder(
                user_id=test_user.id,
                client_order_id="qx-recon-2",
                exchange_order_id="666",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=1.0,
                status="NEW",
            )
        )
        await db_session.commit()

        class BrokenClient:
            async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
                raise RuntimeError("exchange unreachable")

        report = await OrderReconciliationService(
            db_session, client=BrokenClient()
        ).reconcile_orders()
        assert report["mismatches"] == []
        assert report["unreachable_symbols"] == ["BTCUSDT"]

    @pytest.mark.asyncio
    async def test_report_timestamp_is_real(
        self, db_session: AsyncSession
    ) -> None:
        """The reconciliation timestamp is generated, not a fixed literal."""

        class Client:
            async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
                return []

        report = await OrderReconciliationService(db_session, client=Client()).reconcile_orders()
        stamp = datetime.fromisoformat(report["last_reconciliation_timestamp"])
        assert abs((datetime.now(UTC) - stamp).total_seconds()) < 60


class _SessionCtx:
    """Adapt an existing session to the `async with factory()` protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None
