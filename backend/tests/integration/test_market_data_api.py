"""
QuantX — Integration Tests for Market Data REST Endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestMarketDataEndpoints:
    """Symbol list, stored klines, and the exchange proxies."""

    @pytest.mark.asyncio
    async def test_get_symbols(self, client: AsyncClient, auth_headers: dict) -> None:
        """The supported symbol list is returned."""
        response = await client.get("/api/v1/market/symbols", headers=auth_headers)
        assert response.status_code == 200
        symbols = response.json()
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    @pytest.mark.asyncio
    async def test_get_klines_empty(self, client: AsyncClient, auth_headers: dict) -> None:
        """No stored candles yields an empty list, not an error."""
        response = await client.get(
            "/api/v1/market/klines?symbol=NOSUCHPAIR&timeframe=1m", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_klines_returns_oldest_first(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Candles come back in chronological order for charting."""
        response = await client.get(
            "/api/v1/market/klines?symbol=BTCUSDT&timeframe=1h&limit=50", headers=auth_headers
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 50
        timestamps = [r["timestamp"] for r in rows]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_get_ticker(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """The ticker proxy returns the exchange payload."""
        response = await client.get("/api/v1/market/ticker?symbol=BTCUSDT", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_ticker_requires_a_symbol(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """The all-symbols form is not exposed.

        It carries very high request weight against the shared exchange rate
        limit, which is the fastest route to an IP ban.
        """
        response = await client.get("/api/v1/market/ticker", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_orderbook_depth_is_bounded(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """Depth beyond the documented maximum is rejected."""
        ok = await client.get(
            "/api/v1/market/orderbook?symbol=BTCUSDT&limit=100", headers=auth_headers
        )
        assert ok.status_code == 200

        too_deep = await client.get(
            "/api/v1/market/orderbook?symbol=BTCUSDT&limit=99999", headers=auth_headers
        )
        assert too_deep.status_code == 422


@pytest.mark.integration
class TestCoverageEndpoints:
    """The UI must be able to tell "not ingested" from "query failed"."""

    @pytest.mark.asyncio
    async def test_symbols_and_timeframes_come_from_config(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """The advertised lists are configuration, not a hardcoded constant.

        A hardcoded list let the UI offer eight symbols while ingestion only
        ever populated two.
        """
        from app.core.config import get_settings

        settings = get_settings()
        symbols = (await client.get("/api/v1/market/symbols", headers=auth_headers)).json()
        timeframes = (await client.get("/api/v1/market/timeframes", headers=auth_headers)).json()

        assert symbols == settings.market_symbol_list
        assert timeframes == settings.market_timeframe_list

    @pytest.mark.asyncio
    async def test_coverage_reports_every_advertised_pair(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Every symbol/timeframe the UI offers appears in the report."""
        response = await client.get("/api/v1/market/coverage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["pairs_total"] == len(data["symbols"]) * len(data["timeframes"])
        reported = {(c["symbol"], c["timeframe"]) for c in data["coverage"]}
        expected = {(s, t) for s in data["symbols"] for t in data["timeframes"]}
        assert reported == expected

    @pytest.mark.asyncio
    async def test_coverage_marks_seeded_pair_as_present(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """A pair with stored candles reports has_data."""
        data = (await client.get("/api/v1/market/coverage", headers=auth_headers)).json()
        btc_1h = next(
            c for c in data["coverage"] if c["symbol"] == "BTCUSDT" and c["timeframe"] == "1h"
        )
        assert btc_1h["has_data"] is True
        assert btc_1h["candle_count"] == seeded_candles
        assert data["pairs_with_data"] >= 1

    @pytest.mark.asyncio
    async def test_missing_pair_is_reported_not_omitted(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """An un-ingested pair appears with a zero count."""
        data = (await client.get("/api/v1/market/coverage", headers=auth_headers)).json()
        empty = [c for c in data["coverage"] if not c["has_data"]]
        assert empty, "expected at least one un-ingested pair"
        assert all(c["candle_count"] == 0 for c in empty)
