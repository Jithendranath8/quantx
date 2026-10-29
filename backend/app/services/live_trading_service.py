"""
QuantX — Live Trading Execution Service.

Executes orders against Binance behind mandatory, persisted risk checks.

Every order is written to ``live_orders`` *before* it is sent, carrying a
locally generated client_order_id. If the HTTP call then fails or times out we
still have a durable record to reconcile against, rather than an order that may
or may not exist on the exchange with no local trace.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.config import get_settings
from app.core.exceptions import (
    ConfigurationError,
    NotFoundError,
    OrderRejectedError,
    RiskLimitExceededError,
)
from app.core.logging import get_logger
from app.core.metrics import TRADES_EXECUTED_TOTAL
from app.engines.risk.book import Book, Fill, build_book
from app.engines.risk.manager import RiskManager, oversize_reason
from app.models.live_trading import LiveOrder
from app.schemas.live_trading import LiveOrderRequest, LiveOrderResponse
from app.schemas.risk import RiskConfig, TradeRiskRequest
from app.services.event_ledger_service import EventLedgerService
from app.services.notification_service import NotificationService
from app.services.risk_state_service import RiskStateService

logger = get_logger(__name__)


class LiveTradingService:
    """Service handling live trading execution and risk verification."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()
        self._risk_state = RiskStateService(session)
        self._ledger = EventLedgerService(session)
        self._settings = get_settings()

    async def execute_live_order(
        self,
        user_id: uuid.UUID,
        req: LiveOrderRequest,
        account_balance: float | None = None,
    ) -> LiveOrderResponse:
        """Validate against the risk engine, then place the order on Binance.

        Args:
            user_id: Owner of the order.
            req: Validated order request.
            account_balance: Override for the balance used in risk sizing.
                When omitted the live quote-asset balance is read from Binance.

        Raises:
            ConfigurationError: If credentials are missing or mainnet is not enabled.
            RiskLimitExceededError: If the risk engine rejects the trade.
            OrderRejectedError: If Binance or local pre-flight rejects the order.
        """
        symbol = req.symbol.upper()

        # 1. Check the persisted halt FIRST, before any network call. A halted
        #    account must be told it is halted; resolving prices and balances
        #    first meant a missing-credentials error masked the real reason,
        #    and made exchange requests on behalf of an account that is
        #    forbidden from trading.
        config = await self._risk_state.load_config(user_id)
        if config.circuit_breaker_active:
            state = await self._risk_state.get_or_create(user_id)
            TRADES_EXECUTED_TOTAL.labels(symbol=symbol, side=req.side, status="HALTED").inc()
            raise RiskLimitExceededError(
                rule="circuit_breaker",
                message=(
                    "Trade rejected: circuit breaker is ACTIVE and trading is halted"
                    + (f" ({state.circuit_breaker_reason})" if state.circuit_breaker_reason else "")
                ),
            )

        # 2. Resolve the reference price from the exchange rather than trusting
        #    a caller-supplied number or a hardcoded constant.
        reference_price = req.price or req.stop_price
        if reference_price is None:
            reference_price = await self._client.get_price(symbol)

        # 3. Resolve the account balance from the exchange when not supplied.
        if account_balance is None:
            account_balance = await self._resolve_quote_balance(symbol)

        # 4. Remaining hard risk rules, for BUYs only. On spot a SELL can only
        #    reduce exposure, so sizing limits do not apply to it (the halt above
        #    still does); scoring it as new exposure blocked exits for no reason.
        if req.side.upper() == "BUY":
            await self._enforce_buy_risk(user_id, config, symbol, req, reference_price, account_balance)

        # 5. Record intent before touching the network.
        client_order_id = f"qx{uuid.uuid4().hex[:30]}"
        order = LiveOrder(
            user_id=user_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price,
            stop_price=req.stop_price,
            status="PENDING_SUBMIT",
            is_testnet=self._client.testnet,
        )
        self._session.add(order)
        await self._session.commit()

        # 6. Submit.
        try:
            result = await self._client.place_order(
                symbol=symbol,
                side=req.side,
                order_type=req.order_type,
                quantity=req.quantity,
                price=req.price,
                stop_price=req.stop_price,
                client_order_id=client_order_id,
            )
        except (ConfigurationError, OrderRejectedError) as exc:
            order.status = "REJECTED"
            order.rejection_reason = str(exc.message)[:500]
            await self._session.commit()
            TRADES_EXECUTED_TOTAL.labels(symbol=symbol, side=req.side, status="REJECTED").inc()
            raise
        except Exception as exc:
            # Unknown outcome: the exchange may or may not have the order.
            # Leave it flagged for the reconciliation worker rather than
            # reporting a failure that might actually be a live position.
            order.status = "UNKNOWN_NEEDS_RECONCILIATION"
            order.rejection_reason = str(exc)[:500]
            await self._session.commit()
            logger.error(
                "live_order_submit_indeterminate",
                symbol=symbol,
                client_order_id=client_order_id,
                error=str(exc),
            )
            TRADES_EXECUTED_TOTAL.labels(symbol=symbol, side=req.side, status="UNKNOWN").inc()
            raise

        # 7. Persist the exchange's own answer.
        self._apply_exchange_result(order, result)
        await self._ledger.log_event(
            source="LIVE_TRADING_SERVICE",
            event_type="LIVE_ORDER_PLACED",
            payload={
                "client_order_id": client_order_id,
                "exchange_order_id": order.exchange_order_id,
                "symbol": symbol,
                "side": req.side,
                "quantity": req.quantity,
                "status": order.status,
                "testnet": self._client.testnet,
            },
            user_id=user_id,
            symbol=symbol,
            commit=False,
        )
        await self._session.commit()

        TRADES_EXECUTED_TOTAL.labels(symbol=symbol, side=req.side, status=order.status).inc()
        return LiveOrderResponse(
            order_id=str(order.exchange_order_id or client_order_id),
            symbol=symbol,
            side=req.side,
            order_type=req.order_type,
            status=order.status,
            price=float(order.filled_price or order.price or reference_price),
            quantity=req.quantity,
            transact_time=int(result.get("transactTime", 0)),
        )

    async def _enforce_buy_risk(
        self,
        user_id: uuid.UUID,
        config: RiskConfig,
        symbol: str,
        req: LiveOrderRequest,
        reference_price: float,
        quote_balance: float,
    ) -> None:
        """Check a live BUY against the risk engine with the account's real book.

        The book is rebuilt from QuantX's own filled orders on this venue
        (testnet and mainnet are separate books), valued at current prices, so
        exposure, open-position, daily-loss and cooldown limits measure what
        is actually held. Holdings bought outside QuantX are not visible here.

        Raises:
            RiskLimitExceededError: If any rule rejects the order.
        """
        book = await self._book(user_id)
        exposure = 0.0
        for held_symbol, holding in book.holdings.items():
            try:
                price = await self._client.get_price(held_symbol)
            except Exception as exc:
                logger.warning("live_mark_price_failed", symbol=held_symbol, error=str(exc))
                price = holding.avg_cost
            exposure += price * holding.quantity

        last_loss = book.last_loss_at.get(symbol)
        request = TradeRiskRequest(
            symbol=symbol,
            action="BUY",
            account_balance=quote_balance + exposure,
            order_amount_usd=req.quantity * reference_price,
            leverage=req.leverage,
            entry_price=reference_price,
            stop_loss_price=req.stop_price,
            current_daily_loss_usd=max(0.0, -book.realized_since_day_start),
            active_positions_count=len(book.holdings) - (1 if symbol in book.holdings else 0),
            current_exposure_usd=exposure,
            minutes_since_loss_on_symbol=(
                (datetime.now(UTC) - last_loss).total_seconds() / 60 if last_loss is not None else None
            ),
        )
        risk_result = RiskManager(config).validate_trade(request)
        reason = risk_result.rejection_reason if not risk_result.is_approved else oversize_reason(request, risk_result)
        if reason is None:
            return

        # A triggered breaker must be persisted, or the next request in a
        # different worker would sail straight through.
        if risk_result.circuit_breaker_triggered and not config.circuit_breaker_active:
            await self._risk_state.set_circuit_breaker(user_id, True, reason)
            await self._session.commit()
        TRADES_EXECUTED_TOTAL.labels(symbol=symbol, side=req.side, status="RISK_REJECTED").inc()
        raise RiskLimitExceededError(rule="risk_engine", message=f"Trade rejected by Risk Engine: {reason}")

    async def _book(self, user_id: uuid.UUID) -> Book:
        """The user's live position book on the current venue, from recorded fills."""
        stmt = select(LiveOrder).where(
            LiveOrder.user_id == user_id,
            LiveOrder.is_testnet == self._client.testnet,
            LiveOrder.filled_quantity > 0,
            LiveOrder.filled_price.is_not(None),
        )
        orders = (await self._session.execute(stmt)).scalars().all()
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return build_book(
            (
                Fill(
                    symbol=o.symbol,
                    side=o.side,
                    quantity=o.filled_quantity,
                    price=float(o.filled_price or 0.0),
                    at=o.transact_time or o.created_at,
                )
                for o in orders
            ),
            day_start=midnight,
        )

    async def list_orders(self, user_id: uuid.UUID, limit: int = 100) -> list[LiveOrder]:
        """List this user's live orders, newest first."""
        stmt = (
            select(LiveOrder)
            .where(LiveOrder.user_id == user_id)
            .order_by(LiveOrder.created_at.desc())
            .limit(min(max(1, limit), 500))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def cancel_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> LiveOrder:
        """Cancel one of this user's live orders on the exchange."""
        stmt = select(LiveOrder).where(
            LiveOrder.id == order_id,
            LiveOrder.user_id == user_id,
        )
        order = (await self._session.execute(stmt)).scalar_one_or_none()
        if order is None:
            raise NotFoundError("Live order", str(order_id))

        if order.exchange_order_id:
            result = await self._client.cancel_order(order.symbol, order.exchange_order_id)
            order.status = result.get("status", "CANCELED")
        else:
            order.status = "CANCELED"

        await self._session.commit()
        return order

    # ── Internals ────────────────────────────────────────────────────

    async def _resolve_quote_balance(self, symbol: str) -> float:
        """Read the free balance of the symbol's quote asset from Binance."""
        filters_source = await self._client.get_exchange_info()
        quote_asset = "USDT"
        for entry in filters_source.get("symbols", []):
            if entry.get("symbol") == symbol:
                quote_asset = entry.get("quoteAsset", "USDT")
                break
        balances = await self._client.get_balances()
        return float(balances.get(quote_asset, 0.0))

    @staticmethod
    def _apply_exchange_result(order: LiveOrder, result: dict[str, Any]) -> None:
        """Copy Binance's response onto the local order record."""
        order.exchange_order_id = str(result.get("orderId")) if result.get("orderId") else None
        order.status = result.get("status", "NEW")
        order.raw_response = result

        executed_qty = float(result.get("executedQty", 0) or 0)
        order.filled_quantity = executed_qty

        fills = result.get("fills") or []
        if fills:
            notional = sum(float(f["price"]) * float(f["qty"]) for f in fills)
            filled_qty = sum(float(f["qty"]) for f in fills)
            order.filled_price = notional / filled_qty if filled_qty else None
            order.commission = sum(float(f.get("commission", 0) or 0) for f in fills)
            order.commission_asset = fills[0].get("commissionAsset")
        elif executed_qty and result.get("cummulativeQuoteQty"):
            order.filled_price = float(result["cummulativeQuoteQty"]) / executed_qty

        if result.get("transactTime"):
            order.transact_time = datetime.fromtimestamp(
                int(result["transactTime"]) / 1000, tz=UTC
            )


async def notify_order_outcome(order: LiveOrder) -> None:
    """Send an alert describing a completed order (best effort)."""
    await NotificationService.send_alert(
        title=f"Order {order.status}: {order.symbol}",
        message=(
            f"{order.side} {order.quantity} {order.symbol} — status {order.status} "
            f"(testnet={order.is_testnet})"
        ),
        level="INFO" if order.status in {"FILLED", "NEW"} else "WARNING",
    )
