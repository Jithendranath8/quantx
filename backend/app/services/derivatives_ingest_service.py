"""
QuantX — Funding Rate & Open Interest Ingestion.

Populates the ``funding_rates`` and ``open_interests`` tables that the AI agent
reads when assembling market context.

Both tables and their models already existed, but nothing ever wrote to them,
so the agent was handed ``null`` for funding and open interest on every call.
(Before that it was handed hardcoded constants, which is worse: confident output
derived from fiction.)

Binance retains roughly 30 days of open-interest history, so a backfill cannot
reach further back than that no matter what start time is requested.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.logging import get_logger
from app.models.market_data import FundingRate, OpenInterest

logger = get_logger(__name__)

REQUEST_INTERVAL_SECONDS = 0.2
FUNDING_PAGE_LIMIT = 1000
OI_PAGE_LIMIT = 500
MAX_PAGES = 200


class DerivativesIngestService:
    """Fetches and stores perpetual funding rates and open interest."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()

    async def ingest_funding_rates(self, symbol: str, days: int = 30) -> int:
        """Backfill funding rate history for a perpetual symbol.

        Returns:
            Number of funding rows upserted.
        """
        symbol = symbol.upper()
        end_ms = int(datetime.now(UTC).timestamp() * 1000)
        start_ms = end_ms - max(1, days) * 86_400_000

        total = 0
        cursor = start_ms
        for _ in range(MAX_PAGES):
            page = await self._client.get_funding_rate_history(
                symbol, start_time=cursor, end_time=end_ms, limit=FUNDING_PAGE_LIMIT
            )
            if not page:
                break

            rows = [
                {
                    "symbol": symbol,
                    "rate": float(entry["fundingRate"]),
                    "timestamp": datetime.fromtimestamp(
                        int(entry["fundingTime"]) / 1000, tz=UTC
                    ),
                }
                for entry in page
            ]
            total += await self._upsert_funding(rows)
            await self._session.commit()

            last = int(page[-1]["fundingTime"])
            if last <= cursor:
                break
            cursor = last + 1

            if len(page) < FUNDING_PAGE_LIMIT:
                break
            await asyncio.sleep(REQUEST_INTERVAL_SECONDS)

        logger.info("funding_rates_ingested", symbol=symbol, rows=total, days=days)
        return total

    async def ingest_open_interest(self, symbol: str, period: str = "1h") -> int:
        """Backfill open interest history for a perpetual symbol.

        Returns:
            Number of open-interest rows upserted.
        """
        symbol = symbol.upper()
        page = await self._client.get_open_interest_history(
            symbol, period=period, limit=OI_PAGE_LIMIT
        )
        if not page:
            return 0

        rows = [
            {
                "symbol": symbol,
                "open_interest": float(entry["sumOpenInterest"]),
                "timestamp": datetime.fromtimestamp(
                    int(entry["timestamp"]) / 1000, tz=UTC
                ),
            }
            for entry in page
        ]
        count = await self._upsert_open_interest(rows)
        await self._session.commit()

        logger.info("open_interest_ingested", symbol=symbol, rows=count, period=period)
        return count

    async def snapshot_current(self, symbol: str) -> dict[str, float | None]:
        """Store a point-in-time funding rate and open interest reading.

        Used by the periodic worker to keep the tables fresh between backfills.
        """
        symbol = symbol.upper()
        now = datetime.now(UTC)
        result: dict[str, float | None] = {"funding_rate": None, "open_interest": None}

        try:
            premium = await self._client.get_premium_index(symbol)
            rate = float(premium["lastFundingRate"])
            await self._upsert_funding([{"symbol": symbol, "rate": rate, "timestamp": now}])
            result["funding_rate"] = rate
        except Exception as exc:
            # One feed failing must not prevent the other from being stored.
            logger.warning("funding_snapshot_failed", symbol=symbol, error=str(exc))

        try:
            oi = await self._client.get_open_interest(symbol)
            value = float(oi["openInterest"])
            await self._upsert_open_interest(
                [{"symbol": symbol, "open_interest": value, "timestamp": now}]
            )
            result["open_interest"] = value
        except Exception as exc:
            logger.warning("open_interest_snapshot_failed", symbol=symbol, error=str(exc))

        await self._session.commit()
        return result

    # ── Internals ────────────────────────────────────────────────────

    async def _upsert_funding(self, rows: list[dict]) -> int:
        """Upsert funding rows on the (symbol, timestamp) unique index."""
        if not rows:
            return 0
        stmt = insert(FundingRate).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timestamp"],
            set_={"rate": stmt.excluded.rate},
        )
        await self._session.execute(stmt)
        return len(rows)

    async def _upsert_open_interest(self, rows: list[dict]) -> int:
        """Upsert open-interest rows on the (symbol, timestamp) unique index."""
        if not rows:
            return 0
        stmt = insert(OpenInterest).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timestamp"],
            set_={"open_interest": stmt.excluded.open_interest},
        )
        await self._session.execute(stmt)
        return len(rows)
