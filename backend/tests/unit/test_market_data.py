"""
QuantX — Unit Tests for the Binance connector.

The connector now routes every call through one _request helper, so these
patch httpx.AsyncClient.request rather than .get.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.binance_client import BinanceClient
from app.core.exceptions import BinanceError, ConfigurationError, OrderRejectedError

KLINE_ROW = [
    1499040000000, "0.01634790", "0.80000000", "0.01575800", "0.01577100",
    "148976.11427815", 1499644799999, "2434.19055334", 308,
    "1756.87402397", "28.46694368", "0",
]

EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "NOTIONAL", "minNotional": "10.0"},
            ],
        }
    ]
}


def mock_response(payload: Any, status: int = 200) -> AsyncMock:
    """Build a stand-in httpx response."""
    response = AsyncMock()
    response.status_code = status
    response.json = lambda: payload
    response.headers = {}
    response.text = str(payload)
    return response


@pytest.mark.unit
class TestBinanceClient:
    """Public endpoints, signing, and order pre-flight."""

    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        """Ping returns True on a healthy response."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response({})
            async with BinanceClient() as client:
                assert await client.ping() is True

    @pytest.mark.asyncio
    async def test_get_klines_returns_data(self) -> None:
        """Klines are returned as the raw Binance array."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response([KLINE_ROW])
            async with BinanceClient() as client:
                data = await client.get_klines("BTCUSDT", "1m", limit=1)
        assert len(data) == 1
        assert data[0][1] == "0.01634790"

    @pytest.mark.asyncio
    async def test_transport_failure_raises_binance_error(self) -> None:
        """Transport errors surface as BinanceError after retries."""
        import httpx

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.side_effect = httpx.ConnectError("Connection Timeout")
            async with BinanceClient() as client:
                client.MAX_RETRIES = 1
                with pytest.raises(BinanceError):
                    await client.get_klines("INVALID", "1m")

    @pytest.mark.asyncio
    async def test_error_status_raises_binance_error(self) -> None:
        """A 4xx from Binance is translated, carrying its message."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response({"code": -1121, "msg": "Invalid symbol."}, status=400)
            async with BinanceClient() as client:
                with pytest.raises(BinanceError, match="Invalid symbol"):
                    await client.get_orderbook("NOTREAL")

    @pytest.mark.asyncio
    async def test_signature_is_deterministic_hmac(self) -> None:
        """Signing produces the documented HMAC-SHA256 of the query string."""
        import hashlib
        import hmac
        from urllib.parse import urlencode

        async with BinanceClient(api_key="k", api_secret="secret") as client:
            params = {"symbol": "BTCUSDT", "timestamp": 1700000000000}
            expected = hmac.new(
                b"secret", urlencode(params).encode(), hashlib.sha256
            ).hexdigest()
            assert client._sign(params) == expected

    @pytest.mark.asyncio
    async def test_signed_call_without_credentials_is_refused(self) -> None:
        """A signed endpoint without keys fails clearly, not with a 401 loop."""
        async with BinanceClient(api_key="", api_secret="") as client:
            with pytest.raises(ConfigurationError, match="credentials"):
                await client.get_account()

    @pytest.mark.asyncio
    async def test_mainnet_order_blocked_without_explicit_opt_in(self) -> None:
        """Mainnet order placement requires ALLOW_MAINNET_TRADING.

        BINANCE_TESTNET=false alone must not be enough to move real funds.
        """
        async with BinanceClient(api_key="k", api_secret="s", testnet=False) as client:
            client._settings.allow_mainnet_trading = False
            with pytest.raises(ConfigurationError, match="ALLOW_MAINNET_TRADING"):
                await client.place_order("BTCUSDT", "BUY", "MARKET", 1.0)

    @pytest.mark.asyncio
    async def test_order_below_min_notional_is_rejected_locally(self) -> None:
        """A too-small order is caught before it reaches the exchange."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response(EXCHANGE_INFO)
            async with BinanceClient(api_key="k", api_secret="s", testnet=True) as client:
                with pytest.raises(OrderRejectedError, match="minNotional"):
                    await client.place_order(
                        "BTCUSDT", "BUY", "LIMIT", quantity=0.0001, price=1.0
                    )

    @pytest.mark.asyncio
    async def test_quantity_is_snapped_to_step_size(self) -> None:
        """Quantities are rounded down to the symbol's lot step."""
        async with BinanceClient() as client:
            assert client._snap(1.234567891, "0.00001") == pytest.approx(1.23456, abs=1e-9)
            assert client._snap(1.5, None) == 1.5

    @pytest.mark.asyncio
    async def test_exchange_info_is_cached(self) -> None:
        """exchangeInfo is fetched once, not on every pre-flight check."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response(EXCHANGE_INFO)
            async with BinanceClient() as client:
                await client.get_exchange_info()
                await client.get_exchange_info()
                await client.get_symbol_filters("BTCUSDT")
        assert request.await_count == 1


@pytest.mark.unit
class TestMarketDataHostRouting:
    """Public market data reads mainnet; order flow uses the trading venue.

    Binance testnet retains roughly 28 days of kline history against mainnet's
    400+, which silently capped every backtest, walk-forward and optimization
    run to under a month of data.
    """

    @pytest.mark.asyncio
    async def test_klines_read_mainnet_even_on_testnet(self) -> None:
        """Historical candles come from mainnet regardless of the flag."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response([KLINE_ROW])
            async with BinanceClient(testnet=True) as client:
                await client.get_klines("BTCUSDT", "1h")
        url = request.await_args.args[1]
        assert url.startswith(client.market_data_base_url)
        assert "testnet" not in url

    @pytest.mark.asyncio
    async def test_ticker_and_orderbook_read_mainnet(self) -> None:
        """Display data is the real market, not testnet's thin book."""
        for call, args in (("get_ticker_24h", ("BTCUSDT",)), ("get_orderbook", ("BTCUSDT",))):
            with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
                request.return_value = mock_response({})
                async with BinanceClient(testnet=True) as client:
                    await getattr(client, call)(*args)
            assert request.await_args.args[1].startswith(client.market_data_base_url), call
            assert "testnet" not in request.await_args.args[1], call

    @pytest.mark.asyncio
    async def test_order_preflight_price_uses_the_trading_venue(self) -> None:
        """get_price must agree with the venue the order will reach.

        Pricing an order against mainnet while placing it on testnet would
        validate min-notional against the wrong book.
        """
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response({"price": "50000.0"})
            async with BinanceClient(testnet=True) as client:
                await client.get_price("BTCUSDT")
        # Relative path means the client's own base_url, i.e. the testnet host.
        assert request.await_args.args[1] == "/api/v3/ticker/price"

    @pytest.mark.asyncio
    async def test_reference_price_reads_mainnet(self) -> None:
        """The display/simulation price is the real market."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response({"price": "50000.0"})
            async with BinanceClient(testnet=True) as client:
                await client.get_reference_price("BTCUSDT")
        assert request.await_args.args[1].startswith(client.market_data_base_url)
        assert "testnet" not in request.await_args.args[1]

    @pytest.mark.asyncio
    async def test_exchange_info_stays_on_the_trading_venue(self) -> None:
        """Symbol filters differ between venues and gate real orders."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response(EXCHANGE_INFO)
            async with BinanceClient(testnet=True) as client:
                await client.get_exchange_info()
        assert request.await_args.args[1] == "/api/v3/exchangeInfo"


@pytest.mark.unit
class TestApiKeyHeaderScoping:
    """The trading API key must ride only on signed requests, never on the
    public market-data reads that may target an operator-configurable host."""

    @pytest.mark.asyncio
    async def test_public_request_carries_no_api_key(self) -> None:
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response([KLINE_ROW])
            async with BinanceClient(api_key="k", api_secret="s", testnet=True) as client:
                await client.get_klines("BTCUSDT", "1h")
        assert request.await_args.kwargs.get("headers") is None

    @pytest.mark.asyncio
    async def test_signed_request_carries_the_api_key(self) -> None:
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as request:
            request.return_value = mock_response({"balances": []})
            async with BinanceClient(api_key="k", api_secret="s", testnet=True) as client:
                await client.get_account()
        assert request.await_args.kwargs.get("headers") == {"X-MBX-APIKEY": "k"}
