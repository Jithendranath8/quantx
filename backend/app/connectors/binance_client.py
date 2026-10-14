"""
QuantX — Async Binance Exchange Connector.

Provides a unified, async interface for interacting with Binance SPOT APIs.
Supports public endpoints (klines, orderbook, ticker) and HMAC-SHA256 signed
private endpoints (account, order placement, cancellation).

Safety model
------------
Placing or cancelling orders against Binance *mainnet* requires BOTH
``BINANCE_TESTNET=false`` and ``ALLOW_MAINNET_TRADING=true``. A single
misconfigured flag therefore cannot move real money. Read-only calls are
unaffected.
"""

import asyncio
import hashlib
import hmac
import time
from typing import Any, Literal, Self, cast
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.exceptions import BinanceError, ConfigurationError, OrderRejectedError
from app.core.logging import get_logger

logger = get_logger(__name__)

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"]

# Binance returns 429 when a rate limit is breached and 418 once it has started
# banning the IP. Both carry Retry-After. Anything else is not worth retrying.
_RETRYABLE_STATUS = {429, 418, 500, 502, 503, 504}


class BinanceClient:
    """Async Binance API client.

    Uses httpx for async HTTP with bounded retries and rate-limit handling.
    Compatible with both Binance mainnet and testnet.

    The underlying connection pool is reused for the lifetime of the instance,
    so prefer one long-lived client (see :func:`get_binance_client`) over
    constructing one per request.
    """

    SPOT_URL = "https://api.binance.com"
    SPOT_TESTNET_URL = "https://testnet.binance.vision"

    FUTURES_URL = "https://fapi.binance.com"
    FUTURES_TESTNET_URL = "https://testnet.binancefuture.com"

    RECV_WINDOW_MS = 5000
    MAX_RETRIES = 3

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool | None = None,
    ) -> None:
        settings = get_settings()
        self._settings = settings
        self.api_key = api_key if api_key is not None else settings.binance_api_key
        self.api_secret = api_secret if api_secret is not None else settings.binance_secret
        self.testnet = testnet if testnet is not None else settings.binance_testnet

        self.base_url = self.SPOT_TESTNET_URL if self.testnet else self.SPOT_URL
        self.futures_base_url = self.FUTURES_TESTNET_URL if self.testnet else self.FUTURES_URL
        # Funding rates and open interest are read-only public market data, and
        # the testnet futures host serves synthetic values for them. Research
        # needs the real series, and a public GET cannot move funds, so these
        # always read mainnet regardless of the testnet setting.
        self.derivatives_base_url = self.FUTURES_URL

        # Historical klines and reference quotes come from mainnet for the same
        # reason. Binance testnet retains only ~28 days of kline history against
        # mainnet's 400+, which silently capped every backtest, walk-forward and
        # optimization run to under a month of data. Order placement still uses
        # the trading host below, so this changes what is *read*, never where
        # funds move. The host is configurable and defaults to Binance's public
        # data mirror, which — unlike api.binance.com — is not geo-blocked from
        # most datacenter regions.
        self.market_data_base_url = settings.binance_market_data_url

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._exchange_info: dict[str, Any] | None = None
        self._exchange_info_fetched_at: float = 0.0
        self._exchange_info_lock = asyncio.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # ── Request plumbing ─────────────────────────────────────────────

    def _sign(self, params: dict[str, Any]) -> str:
        """Produce the HMAC-SHA256 signature for a query string."""
        query = urlencode(params, doseq=True)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _require_credentials(self) -> None:
        """Ensure API credentials are present before a signed call."""
        if not self.api_key or not self.api_secret:
            raise ConfigurationError(
                "Binance API credentials are not configured. "
                "Set BINANCE_API_KEY and BINANCE_SECRET."
            )

    def _require_trading_permission(self, operation: str) -> None:
        """Block order-mutating operations unless explicitly permitted.

        Testnet is always allowed. Mainnet requires the operator to have set
        ALLOW_MAINNET_TRADING=true in addition to BINANCE_TESTNET=false.
        """
        if self.testnet:
            return
        if not self._settings.allow_mainnet_trading:
            raise ConfigurationError(
                f"Refusing to {operation} against Binance mainnet: "
                "ALLOW_MAINNET_TRADING is not enabled. Set it to true only when "
                "you intend to trade real funds.",
                {"operation": operation, "testnet": False},
            )
        logger.warning("binance_mainnet_operation", operation=operation)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
        base_url: str | None = None,
    ) -> Any:
        """Execute a Binance REST call with retries and error translation.

        Args:
            base_url: Override the host for this call. Funding rate and open
                interest live on the FUTURES host, not the SPOT one the client
                is otherwise bound to.
        """
        params = {k: v for k, v in (params or {}).items() if v is not None}
        url = path if base_url is None else f"{base_url.rstrip('/')}{path}"

        if signed:
            self._require_credentials()
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.RECV_WINDOW_MS
            params["signature"] = self._sign(params)

        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._client.request(method, url, params=params)

                if response.status_code in _RETRYABLE_STATUS:
                    retry_after = float(response.headers.get("Retry-After", 2**attempt))
                    if attempt == self.MAX_RETRIES - 1:
                        raise BinanceError(
                            f"{method} {path} failed after {self.MAX_RETRIES} attempts "
                            f"(HTTP {response.status_code})"
                        )
                    logger.warning(
                        "binance_retrying",
                        path=path,
                        status=response.status_code,
                        retry_after=retry_after,
                    )
                    await asyncio.sleep(min(retry_after, 60.0))
                    continue

                if response.status_code >= 400:
                    # Binance encodes domain failures in the body, not the status.
                    try:
                        body = response.json()
                        code, msg = body.get("code"), body.get("msg", response.text)
                    except Exception:
                        code, msg = None, response.text
                    raise BinanceError(
                        f"{method} {path} rejected: {msg}",
                        {"status": response.status_code, "code": code},
                    )

                return response.json()

            except BinanceError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == self.MAX_RETRIES - 1:
                    break
                await asyncio.sleep(2**attempt)

        raise BinanceError(f"{method} {path} failed: {last_error}") from last_error

    # ── Public market data ───────────────────────────────────────────

    async def ping(self) -> bool:
        """Test connectivity to Binance API."""
        try:
            await self._request("GET", "/api/v3/ping")
            return True
        except Exception as e:
            logger.error("binance_ping_failed", error=str(e))
            return False

    async def get_server_time(self) -> int:
        """Fetch Binance server time in milliseconds."""
        data = await self._request("GET", "/api/v3/time")
        return int(data["serverTime"])

    async def get_exchange_info(self, force_refresh: bool = False) -> dict[str, Any]:
        """Fetch exchange trading rules and symbol information.

        The payload is several megabytes and changes rarely, so it is cached
        for an hour. Without this cache every order pre-flight check would
        re-download it.
        """
        async with self._exchange_info_lock:
            age = time.time() - self._exchange_info_fetched_at
            if self._exchange_info is None or force_refresh or age > 3600:
                self._exchange_info = await self._request("GET", "/api/v3/exchangeInfo")
                self._exchange_info_fetched_at = time.time()
            return self._exchange_info

    async def get_symbol_filters(self, symbol: str) -> dict[str, Any]:
        """Get the LOT_SIZE / PRICE_FILTER / NOTIONAL rules for one symbol.

        Raises:
            BinanceError: If the symbol is not listed.
        """
        info = await self.get_exchange_info()
        for entry in info.get("symbols", []):
            if entry.get("symbol") == symbol.upper():
                return {f["filterType"]: f for f in entry.get("filters", [])}
        raise BinanceError(f"Symbol {symbol.upper()} is not listed on this Binance endpoint")

    async def get_ticker_24h(self, symbol: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        """Fetch 24-hour price change statistics for symbol or all symbols."""
        params = {"symbol": symbol.upper()} if symbol else {}
        return cast(
            "dict[str, Any] | list[dict[str, Any]]",
            await self._request(
                "GET", "/api/v3/ticker/24hr", params=params, base_url=self.market_data_base_url
            ),
        )

    async def get_price(self, symbol: str) -> float:
        """Fetch the latest trade price from the TRADING venue.

        Deliberately not the mainnet market-data host: this feeds order
        pre-flight checks, so it must agree with the venue the order will
        actually reach. Use get_reference_price for display and simulation.
        """
        data = await self._request("GET", "/api/v3/ticker/price", params={"symbol": symbol.upper()})
        return float(data["price"])

    async def get_reference_price(self, symbol: str) -> float:
        """Fetch the latest mainnet price, for display and simulation."""
        data = await self._request(
            "GET",
            "/api/v3/ticker/price",
            params={"symbol": symbol.upper()},
            base_url=self.market_data_base_url,
        )
        return float(data["price"])

    async def get_orderbook(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        """Fetch current order book depth for a symbol.

        Args:
            symbol: Trading pair symbol (e.g. BTCUSDT)
            limit: Depth limit (default 100, max 5000)
        """
        return cast(
            "dict[str, Any]",
            await self._request(
                "GET",
                "/api/v3/depth",
                params={"symbol": symbol.upper(), "limit": limit},
                base_url=self.market_data_base_url,
            ),
        )

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[list[Any]]:
        """Fetch historical OHLCV klines (candlesticks).

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            interval: Kline interval ('1m', '5m', '15m', '1h', '4h', '1d', etc.).
            start_time: Start timestamp in milliseconds.
            end_time: End timestamp in milliseconds.
            limit: Max candles to return (default 500, max 1000).

        Returns:
            List of Binance kline arrays: [open_time, open, high, low, close,
            volume, close_time, quote_volume, trades, taker_base, taker_quote, ignore].
        """
        return cast(
            "list[list[Any]]",
            await self._request(
                "GET",
                "/api/v3/klines",
                params={
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": limit,
                    "startTime": start_time,
                    "endTime": end_time,
                },
                base_url=self.market_data_base_url,
            ),
        )

    # ── Derivatives market data (FUTURES host, public) ───────────────

    async def get_funding_rate_history(
        self,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch historical funding rates for a perpetual contract.

        Funding is published every 8 hours. Returns entries shaped
        ``{"symbol", "fundingRate", "fundingTime"}``.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._request(
                "GET",
                "/fapi/v1/fundingRate",
                params={
                    "symbol": symbol.upper(),
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": min(max(1, limit), 1000),
                },
                base_url=self.derivatives_base_url,
            ),
        )

    async def get_premium_index(self, symbol: str) -> dict[str, Any]:
        """Fetch mark price, index price and the current funding rate."""
        return cast(
            "dict[str, Any]",
            await self._request(
                "GET",
                "/fapi/v1/premiumIndex",
                params={"symbol": symbol.upper()},
                base_url=self.derivatives_base_url,
            ),
        )

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        """Fetch the current open interest for a perpetual contract."""
        return cast(
            "dict[str, Any]",
            await self._request(
                "GET",
                "/fapi/v1/openInterest",
                params={"symbol": symbol.upper()},
                base_url=self.derivatives_base_url,
            ),
        )

    async def get_open_interest_history(
        self,
        symbol: str,
        period: str = "1h",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch historical open interest.

        Binance only retains roughly the last 30 days of this series, so a
        backfill cannot reach further back than that however early a start
        time is requested.

        Args:
            period: One of 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._request(
                "GET",
                "/futures/data/openInterestHist",
                params={
                    "symbol": symbol.upper(),
                    "period": period,
                    "limit": min(max(1, limit), 500),
                },
                base_url=self.derivatives_base_url,
            ),
        )

    # ── Signed account endpoints ─────────────────────────────────────

    async def get_account(self) -> dict[str, Any]:
        """Fetch account information including balances and permissions."""
        return cast("dict[str, Any]", await self._request("GET", "/api/v3/account", signed=True))

    async def get_balances(self) -> dict[str, float]:
        """Return non-zero free balances keyed by asset."""
        account = await self.get_account()
        return {
            b["asset"]: float(b["free"])
            for b in account.get("balances", [])
            if float(b.get("free", 0)) > 0
        }

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """List currently open orders, optionally filtered by symbol."""
        params = {"symbol": symbol.upper()} if symbol else {}
        result = await self._request("GET", "/api/v3/openOrders", params=params, signed=True)
        return list(result)

    async def get_order(self, symbol: str, order_id: int | str) -> dict[str, Any]:
        """Fetch a single order's current state."""
        return cast(
            "dict[str, Any]",
            await self._request(
                "GET",
                "/api/v3/order",
                params={"symbol": symbol.upper(), "orderId": order_id},
                signed=True,
            ),
        )

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        client_order_id: str | None = None,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """Place an order on Binance SPOT.

        Quantity and price are snapped to the symbol's LOT_SIZE / PRICE_FILTER
        step, and the resulting notional is checked against MIN_NOTIONAL before
        anything is sent, so predictable rejections are caught locally.

        Args:
            symbol: Trading pair (e.g. 'BTCUSDT').
            side: 'BUY' or 'SELL'.
            order_type: Binance order type.
            quantity: Base-asset quantity.
            price: Limit price (required for LIMIT-family orders).
            stop_price: Trigger price (required for STOP/TAKE_PROFIT orders).
            client_order_id: Idempotency key echoed back by Binance.
            time_in_force: GTC / IOC / FOK for LIMIT-family orders.

        Raises:
            ConfigurationError: If mainnet trading is not explicitly enabled.
            OrderRejectedError: If the order fails local pre-flight validation.
        """
        self._require_trading_permission("place an order")

        symbol = symbol.upper()
        filters = await self.get_symbol_filters(symbol)

        quantity = self._snap(quantity, filters.get("LOT_SIZE", {}).get("stepSize"))
        if price is not None:
            price = self._snap(price, filters.get("PRICE_FILTER", {}).get("tickSize"))
        if stop_price is not None:
            stop_price = self._snap(stop_price, filters.get("PRICE_FILTER", {}).get("tickSize"))

        if quantity <= 0:
            raise OrderRejectedError(f"Quantity rounds to zero at this symbol's step size ({symbol})")

        lot = filters.get("LOT_SIZE", {})
        min_qty = float(lot.get("minQty", 0) or 0)
        if min_qty and quantity < min_qty:
            raise OrderRejectedError(f"Quantity {quantity} is below minQty {min_qty} for {symbol}")

        notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
        min_notional = float(notional_filter.get("minNotional", 0) or 0)
        if min_notional:
            reference_price = price or stop_price or await self.get_price(symbol)
            notional = quantity * reference_price
            if notional < min_notional:
                raise OrderRejectedError(
                    f"Order notional {notional:.2f} is below minNotional {min_notional} for {symbol}"
                )

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": self._format(quantity),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "FULL",
        }
        if order_type != "MARKET":
            if price is None:
                raise OrderRejectedError(f"{order_type} orders require a price")
            params["price"] = self._format(price)
            params["timeInForce"] = time_in_force
        if stop_price is not None:
            params["stopPrice"] = self._format(stop_price)

        logger.info(
            "binance_placing_order",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            testnet=self.testnet,
        )
        result = await self._request("POST", "/api/v3/order", params=params, signed=True)
        logger.info(
            "binance_order_placed",
            symbol=symbol,
            order_id=result.get("orderId"),
            status=result.get("status"),
        )
        return cast("dict[str, Any]", result)

    async def cancel_order(self, symbol: str, order_id: int | str) -> dict[str, Any]:
        """Cancel a single open order."""
        self._require_trading_permission("cancel an order")
        return cast(
            "dict[str, Any]",
            await self._request(
                "DELETE",
                "/api/v3/order",
                params={"symbol": symbol.upper(), "orderId": order_id},
                signed=True,
            ),
        )

    async def cancel_all_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Cancel every open order for one symbol."""
        self._require_trading_permission("cancel all orders")
        result = await self._request(
            "DELETE", "/api/v3/openOrders", params={"symbol": symbol.upper()}, signed=True
        )
        return list(result) if isinstance(result, list) else [result]

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _snap(value: float, step: str | None) -> float:
        """Round a value down to the nearest multiple of a Binance filter step."""
        if not step:
            return value
        step_f = float(step)
        if step_f <= 0:
            return value
        return (int(value / step_f)) * step_f

    @staticmethod
    def _format(value: float) -> str:
        """Render a float without scientific notation or trailing zeros."""
        return f"{value:.8f}".rstrip("0").rstrip(".") or "0"


# ── Process-wide shared client ───────────────────────────────────────

_shared_client: BinanceClient | None = None


def get_binance_client() -> BinanceClient:
    """Get the shared Binance client, creating it on first use.

    Reusing one client keeps the HTTP connection pool and the cached
    exchangeInfo warm. Constructing a client per request throws both away and
    pays a fresh TLS handshake every time.
    """
    global _shared_client
    if _shared_client is None:
        _shared_client = BinanceClient()
    return _shared_client


async def close_binance_client() -> None:
    """Close the shared Binance client during application shutdown."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.close()
        _shared_client = None
