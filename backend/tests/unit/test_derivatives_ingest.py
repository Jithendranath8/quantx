"""
QuantX — Unit Tests for funding rate & open interest ingestion.

These tables and their models already existed, but nothing ever wrote to them,
so the AI agent received null for funding and open interest on every call.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import FundingRate, OpenInterest
from app.services.derivatives_ingest_service import DerivativesIngestService

BASE_MS = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp() * 1000)


class StubDerivativesClient:
    """Serves scripted derivatives payloads."""

    def __init__(self, funding_pages: list[list[dict]] | None = None, **overrides: Any) -> None:
        self._funding_pages = funding_pages if funding_pages is not None else [[]]
        self._page_index = 0
        self._overrides = overrides
        self.funding_calls = 0

    async def get_funding_rate_history(self, symbol: str, **kwargs: Any) -> list[dict]:
        self.funding_calls += 1
        if self._page_index >= len(self._funding_pages):
            return []
        page = self._funding_pages[self._page_index]
        self._page_index += 1
        return page

    async def get_open_interest_history(self, symbol: str, **kwargs: Any) -> list[dict]:
        return self._overrides.get("oi_history", [])

    async def get_premium_index(self, symbol: str) -> dict:
        if "premium_error" in self._overrides:
            raise self._overrides["premium_error"]
        return {"lastFundingRate": "0.00012345"}

    async def get_open_interest(self, symbol: str) -> dict:
        if "oi_error" in self._overrides:
            raise self._overrides["oi_error"]
        return {"openInterest": "54321.5"}


def funding_entry(offset_hours: int, rate: str) -> dict:
    """One Binance funding-rate row."""
    return {
        "symbol": "BTCUSDT",
        "fundingRate": rate,
        "fundingTime": BASE_MS + offset_hours * 3_600_000,
    }


@pytest.mark.unit
class TestFundingIngestion:
    """Funding rate backfill."""

    @pytest.mark.asyncio
    async def test_rows_are_stored(self, db_session: AsyncSession) -> None:
        """Funding entries land in the table with correct types."""
        client = StubDerivativesClient(
            funding_pages=[[funding_entry(0, "0.0001"), funding_entry(8, "-0.00005")]]
        )
        count = await DerivativesIngestService(db_session, client=client).ingest_funding_rates(
            "BTCUSDT", days=7
        )
        assert count == 2

        rows = list(
            (await db_session.execute(select(FundingRate).order_by(FundingRate.timestamp)))
            .scalars()
            .all()
        )
        assert [r.rate for r in rows] == [pytest.approx(0.0001), pytest.approx(-0.00005)]
        assert rows[0].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_reingestion_is_idempotent(self, db_session: AsyncSession) -> None:
        """Re-running a backfill updates rather than duplicating."""
        page = [funding_entry(0, "0.0001")]
        service = DerivativesIngestService(db_session, client=StubDerivativesClient([page]))
        await service.ingest_funding_rates("BTCUSDT", days=7)

        # Same timestamp, revised rate.
        revised = [funding_entry(0, "0.0009")]
        service2 = DerivativesIngestService(db_session, client=StubDerivativesClient([revised]))
        await service2.ingest_funding_rates("BTCUSDT", days=7)

        rows = list((await db_session.execute(select(FundingRate))).scalars().all())
        assert len(rows) == 1
        assert rows[0].rate == pytest.approx(0.0009)

    @pytest.mark.asyncio
    async def test_pagination_advances_and_terminates(self, db_session: AsyncSession) -> None:
        """A full page triggers another fetch; a short page ends the walk."""
        client = StubDerivativesClient(
            funding_pages=[
                [funding_entry(i, "0.0001") for i in range(0, 8000, 8)][:1000],
                [funding_entry(9000, "0.0002")],
            ]
        )
        count = await DerivativesIngestService(db_session, client=client).ingest_funding_rates(
            "BTCUSDT", days=400
        )
        assert count == 1001
        assert client.funding_calls == 2

    @pytest.mark.asyncio
    async def test_empty_response_stores_nothing(self, db_session: AsyncSession) -> None:
        """No upstream data means no rows, not an error."""
        service = DerivativesIngestService(db_session, client=StubDerivativesClient([[]]))
        assert await service.ingest_funding_rates("BTCUSDT") == 0


@pytest.mark.unit
class TestOpenInterestIngestion:
    """Open interest backfill."""

    @pytest.mark.asyncio
    async def test_rows_are_stored(self, db_session: AsyncSession) -> None:
        """Open-interest history is converted and stored."""
        history = [
            {"timestamp": BASE_MS, "sumOpenInterest": "1000.5"},
            {"timestamp": BASE_MS + 3_600_000, "sumOpenInterest": "1100.25"},
        ]
        service = DerivativesIngestService(
            db_session, client=StubDerivativesClient(oi_history=history)
        )
        assert await service.ingest_open_interest("BTCUSDT") == 2

        rows = list(
            (await db_session.execute(select(OpenInterest).order_by(OpenInterest.timestamp)))
            .scalars()
            .all()
        )
        assert [r.open_interest for r in rows] == [pytest.approx(1000.5), pytest.approx(1100.25)]


@pytest.mark.unit
class TestSnapshot:
    """Point-in-time readings."""

    @pytest.mark.asyncio
    async def test_snapshot_stores_both_feeds(self, db_session: AsyncSession) -> None:
        """A snapshot writes a funding rate and an open interest."""
        service = DerivativesIngestService(db_session, client=StubDerivativesClient())
        result = await service.snapshot_current("BTCUSDT")

        assert result["funding_rate"] == pytest.approx(0.00012345)
        assert result["open_interest"] == pytest.approx(54321.5)
        assert len((await db_session.execute(select(FundingRate))).scalars().all()) == 1
        assert len((await db_session.execute(select(OpenInterest))).scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_one_failing_feed_does_not_block_the_other(
        self, db_session: AsyncSession
    ) -> None:
        """A funding outage must not also lose the open-interest reading."""
        client = StubDerivativesClient(premium_error=RuntimeError("funding endpoint down"))
        result = await DerivativesIngestService(db_session, client=client).snapshot_current("BTCUSDT")

        assert result["funding_rate"] is None
        assert result["open_interest"] == pytest.approx(54321.5)


@pytest.mark.unit
class TestAgentContextUsesIngestedData:
    """The point of ingesting: the agent stops seeing null."""

    @pytest.mark.asyncio
    async def test_agent_context_picks_up_stored_values(self, db_session: AsyncSession) -> None:
        """Once ingested, funding and OI appear in the AI market context."""
        from app.services.agent_service import AgentService

        now = datetime.now(UTC)
        db_session.add(FundingRate(symbol="BTCUSDT", rate=0.00042, timestamp=now))
        db_session.add(
            OpenInterest(symbol="BTCUSDT", open_interest=98765.0, timestamp=now - timedelta(minutes=5))
        )
        await db_session.commit()

        context = await AgentService(db_session).build_context("BTCUSDT")
        assert context.funding_rate == pytest.approx(0.00042)
        assert context.open_interest == pytest.approx(98765.0)
