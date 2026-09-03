"""
QuantX — Realistic Paper Trading Service & Fill Simulator.

Simulates order execution with a slippage model, virtual wallet balances,
fees, and position PnL tracking for both BUY and SELL.

MARKET orders fill immediately. LIMIT, STOP_LOSS and TAKE_PROFIT orders rest as
PENDING until the market reaches their level; ``process_pending_orders`` is what
moves them, and it is driven by a periodic worker.

Every account-scoped operation verifies ``account.user_id == user_id``. Without
that check any authenticated user can read or trade another user's account
simply by supplying its UUID.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.paper_trading import PaperAccount, PaperOrder, PaperPosition
from app.schemas.paper_trading import (
    CreatePaperAccountRequest,
    SubmitPaperOrderRequest,
)

logger = get_logger(__name__)

SLIPPAGE_PCT = 0.0005  # 0.05%
FEE_RATE = 0.00075  # 0.075% taker


class PaperTradingService:
    """Service handling paper trading accounts, order fills, and positions."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()

    async def create_account(self, user_id: uuid.UUID, req: CreatePaperAccountRequest) -> PaperAccount:
        """Create a new virtual paper account."""
        account = PaperAccount(
            user_id=user_id,
            name=req.name,
            initial_balance=req.initial_balance,
            current_balance=req.initial_balance,
        )
        self._session.add(account)
        await self._session.commit()
        await self._session.refresh(account)
        return account

    async def list_accounts(self, user_id: uuid.UUID) -> list[PaperAccount]:
        """List the caller's paper accounts."""
        stmt = select(PaperAccount).where(PaperAccount.user_id == user_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_account(self, user_id: uuid.UUID, account_id: uuid.UUID) -> PaperAccount:
        """Fetch a paper account, enforcing ownership.

        Raises:
            NotFoundError: If no such account exists.
            AuthorizationError: If the account belongs to a different user.
        """
        stmt = select(PaperAccount).where(PaperAccount.id == account_id)
        account = (await self._session.execute(stmt)).scalar_one_or_none()
        if account is None:
            raise NotFoundError("Paper account", str(account_id))
        if account.user_id != user_id:
            logger.warning(
                "paper_account_access_denied",
                account_id=str(account_id),
                requesting_user=str(user_id),
            )
            raise AuthorizationError("You do not have access to this paper account")
        return account

    async def submit_order(
        self,
        user_id: uuid.UUID,
        req: SubmitPaperOrderRequest,
        market_price: float | None = None,
    ) -> PaperOrder:
        """Submit and immediately simulate the fill of a paper order.

        Args:
            market_price: Override for the reference price. When omitted the
                live price is fetched from Binance rather than assumed.
        """
        account = await self.get_account(user_id, req.account_id)
        symbol = req.symbol.upper()
        side = req.side.upper()
        order_type = req.order_type.upper()

        if market_price is None:
            market_price = await self._client.get_price(symbol)

        # A resting order does not touch balance or position until it triggers.
        if order_type != "MARKET":
            return await self._place_resting_order(account, req, symbol, side, market_price)

        # Slippage always works against the taker.
        fill_price = market_price * (1 + SLIPPAGE_PCT) if side == "BUY" else market_price * (1 - SLIPPAGE_PCT)
        notional = fill_price * req.quantity
        fee = notional * FEE_RATE

        position = await self._get_open_position(account.id, symbol)

        if side == "BUY":
            total_cost = notional + fee
            if account.current_balance < total_cost:
                raise ValidationError(
                    f"Insufficient virtual balance: ${account.current_balance:.2f} < ${total_cost:.2f}"
                )
            account.current_balance -= total_cost
            self._apply_buy(account, position, symbol, req, fill_price)
        else:
            if position is None or position.quantity <= 0:
                raise ValidationError(f"No open position in {symbol} to sell")
            if req.quantity > position.quantity + 1e-12:
                raise ValidationError(
                    f"Cannot sell {req.quantity} {symbol}: position holds only {position.quantity}"
                )
            account.current_balance += notional - fee
            self._apply_sell(account, position, req.quantity, fill_price, fee)

        order = PaperOrder(
            account_id=account.id,
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=req.quantity,
            price=market_price,
            filled_price=fill_price,
            filled_quantity=req.quantity,
            status="FILLED",
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
        self._session.add(order)

        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def _place_resting_order(
        self,
        account: PaperAccount,
        req: SubmitPaperOrderRequest,
        symbol: str,
        side: str,
        market_price: float,
    ) -> PaperOrder:
        """Record a LIMIT / STOP_LOSS / TAKE_PROFIT order as PENDING.

        Balance is not debited here. Reserving funds would need a margin ledger
        the platform does not have, so the check happens again at trigger time
        and the order is rejected then if the account can no longer afford it.
        """
        trigger = req.price if req.order_type.upper() == "LIMIT" else req.stop_price
        if trigger is None or trigger <= 0:
            raise ValidationError(f"{req.order_type} orders require a positive trigger price")

        if side == "SELL":
            position = await self._get_open_position(account.id, symbol)
            if position is None or position.quantity + 1e-12 < req.quantity:
                raise ValidationError(
                    f"Cannot rest a SELL for {req.quantity} {symbol}: "
                    f"position holds {position.quantity if position else 0}"
                )

        order = PaperOrder(
            account_id=account.id,
            symbol=symbol,
            side=side,
            order_type=req.order_type.upper(),
            quantity=req.quantity,
            price=req.price if req.price is not None else market_price,
            stop_price=req.stop_price,
            filled_quantity=0.0,
            status="PENDING",
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
        self._session.add(order)
        await self._session.commit()
        await self._session.refresh(order)
        logger.info(
            "paper_order_resting",
            order_id=str(order.id),
            symbol=symbol,
            side=side,
            order_type=order.order_type,
            trigger=trigger,
        )
        return order

    async def process_pending_orders(self, account_id: uuid.UUID | None = None) -> dict[str, int]:
        """Trigger any resting orders the market has reached.

        Args:
            account_id: Restrict to one account, or None to sweep all of them.

        Returns:
            Counts of triggered, rejected and still-pending orders.
        """
        stmt = select(PaperOrder).where(PaperOrder.status == "PENDING")
        if account_id is not None:
            stmt = stmt.where(PaperOrder.account_id == account_id)
        pending = list((await self._session.execute(stmt)).scalars().all())

        if not pending:
            return {"triggered": 0, "rejected": 0, "still_pending": 0}

        # One price lookup per symbol, not per order.
        prices: dict[str, float] = {}
        for symbol in {o.symbol for o in pending}:
            try:
                prices[symbol] = await self._client.get_price(symbol)
            except Exception as exc:
                logger.warning("pending_order_price_failed", symbol=symbol, error=str(exc))

        triggered = rejected = still_pending = 0
        for order in pending:
            price = prices.get(order.symbol)
            if price is None:
                still_pending += 1
                continue
            if not self._is_triggered(order, price):
                still_pending += 1
                continue

            try:
                await self._fill_resting_order(order, price)
                triggered += 1
            except ValidationError as exc:
                order.status = "REJECTED"
                rejected += 1
                logger.warning(
                    "pending_order_rejected", order_id=str(order.id), reason=exc.message
                )

        await self._session.commit()
        return {"triggered": triggered, "rejected": rejected, "still_pending": still_pending}

    @staticmethod
    def _is_triggered(order: PaperOrder, price: float) -> bool:
        """Whether the market has reached this order's level."""
        if order.order_type == "LIMIT":
            # Buy limits rest below the market, sell limits above.
            return price <= order.price if order.side == "BUY" else price >= order.price

        trigger = order.stop_price
        if trigger is None:
            return False
        if order.order_type == "STOP_LOSS":
            # Protective stop: sell when price falls to it, buy when it rises.
            return price <= trigger if order.side == "SELL" else price >= trigger
        if order.order_type == "TAKE_PROFIT":
            return price >= trigger if order.side == "SELL" else price <= trigger
        return False

    async def _fill_resting_order(self, order: PaperOrder, market_price: float) -> None:
        """Execute a triggered order against the account and its position.

        Raises:
            ValidationError: If the account can no longer afford the fill, or
                the position it would close no longer exists.
        """
        account = await self._session.get(PaperAccount, order.account_id)
        if account is None:
            raise ValidationError("Paper account no longer exists")

        # A stop fills at the market it triggered into, not at its trigger
        # price; a limit fills at its resting price or better.
        reference = order.price if order.order_type == "LIMIT" else market_price
        fill_price = (
            reference * (1 + SLIPPAGE_PCT) if order.side == "BUY" else reference * (1 - SLIPPAGE_PCT)
        )
        notional = fill_price * order.quantity
        fee = notional * FEE_RATE

        position = await self._get_open_position(account.id, order.symbol)

        if order.side == "BUY":
            if account.current_balance < notional + fee:
                raise ValidationError(
                    f"Insufficient virtual balance at trigger: "
                    f"${account.current_balance:.2f} < ${notional + fee:.2f}"
                )
            account.current_balance -= notional + fee
            self._apply_buy_to_position(account, position, order.symbol, order.quantity, fill_price)
        else:
            if position is None or position.quantity + 1e-12 < order.quantity:
                raise ValidationError(
                    f"Position in {order.symbol} no longer covers this order"
                )
            account.current_balance += notional - fee
            self._apply_sell(account, position, order.quantity, fill_price, fee)

        order.status = "FILLED"
        order.filled_price = fill_price
        order.filled_quantity = order.quantity
        logger.info(
            "paper_order_triggered",
            order_id=str(order.id),
            order_type=order.order_type,
            fill_price=fill_price,
        )

    async def cancel_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> PaperOrder:
        """Cancel a resting order the caller owns.

        Raises:
            NotFoundError: If no such order exists.
            AuthorizationError: If it belongs to another user.
            ValidationError: If it has already filled or been cancelled.
        """
        order = (
            await self._session.execute(select(PaperOrder).where(PaperOrder.id == order_id))
        ).scalar_one_or_none()
        if order is None:
            raise NotFoundError("Paper order", str(order_id))

        # Ownership is checked through the account, which is where it lives.
        await self.get_account(user_id, order.account_id)

        if order.status != "PENDING":
            raise ValidationError(f"Order is {order.status} and cannot be cancelled")

        order.status = "CANCELLED"
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def get_pending_orders(
        self, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> list[PaperOrder]:
        """List resting orders for an account the caller owns."""
        await self.get_account(user_id, account_id)
        stmt = (
            select(PaperOrder)
            .where(PaperOrder.account_id == account_id, PaperOrder.status == "PENDING")
            .order_by(PaperOrder.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_positions(self, user_id: uuid.UUID, account_id: uuid.UUID) -> list[PaperPosition]:
        """Fetch open positions for an account the caller owns."""
        await self.get_account(user_id, account_id)
        stmt = select(PaperPosition).where(
            PaperPosition.account_id == account_id,
            PaperPosition.status == "OPEN",
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_orders(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        limit: int = 100,
    ) -> list[PaperOrder]:
        """Fetch recent orders for an account the caller owns."""
        await self.get_account(user_id, account_id)
        stmt = (
            select(PaperOrder)
            .where(PaperOrder.account_id == account_id)
            .order_by(PaperOrder.created_at.desc())
            .limit(min(max(1, limit), 500))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def mark_to_market(self, user_id: uuid.UUID, account_id: uuid.UUID) -> list[PaperPosition]:
        """Refresh current prices and unrealized PnL for all open positions."""
        positions = await self.get_positions(user_id, account_id)
        for position in positions:
            try:
                price = await self._client.get_price(position.symbol)
            except Exception as exc:
                logger.warning("mark_to_market_price_failed", symbol=position.symbol, error=str(exc))
                continue
            position.current_price = price
            position.unrealized_pnl = (price - position.entry_price) * position.quantity
        await self._session.commit()
        return positions

    # ── Internals ────────────────────────────────────────────────────

    async def _get_open_position(self, account_id: uuid.UUID, symbol: str) -> PaperPosition | None:
        """Find the open position for a symbol on an account, if any."""
        stmt = select(PaperPosition).where(
            PaperPosition.account_id == account_id,
            PaperPosition.symbol == symbol,
            PaperPosition.status == "OPEN",
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def _apply_buy(
        self,
        account: PaperAccount,
        position: PaperPosition | None,
        symbol: str,
        req: SubmitPaperOrderRequest,
        fill_price: float,
    ) -> None:
        """Open a new long or average up into the existing one."""
        self._apply_buy_to_position(
            account,
            position,
            symbol,
            req.quantity,
            fill_price,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )

    def _apply_buy_to_position(
        self,
        account: PaperAccount,
        position: PaperPosition | None,
        symbol: str,
        quantity: float,
        fill_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        """Open or average into a long position. Shared by both fill paths."""
        if position is not None:
            total_qty = position.quantity + quantity
            position.entry_price = (
                (position.entry_price * position.quantity) + (fill_price * quantity)
            ) / total_qty
            position.quantity = total_qty
            position.current_price = fill_price
            position.unrealized_pnl = (fill_price - position.entry_price) * total_qty
            if stop_loss is not None:
                position.stop_loss = stop_loss
            if take_profit is not None:
                position.take_profit = take_profit
            return

        self._session.add(
            PaperPosition(
                account_id=account.id,
                symbol=symbol,
                side="LONG",
                quantity=quantity,
                entry_price=fill_price,
                current_price=fill_price,
                unrealized_pnl=0.0,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status="OPEN",
            )
        )

    @staticmethod
    def _apply_sell(
        account: PaperAccount,
        position: PaperPosition,
        quantity: float,
        fill_price: float,
        fee: float,
    ) -> None:
        """Reduce or close a long, realizing PnL onto the account."""
        realized = (fill_price - position.entry_price) * quantity - fee
        position.quantity -= quantity
        position.current_price = fill_price
        position.realized_pnl += realized
        account.realized_pnl += realized

        if position.quantity <= 1e-12:
            position.quantity = 0.0
            position.unrealized_pnl = 0.0
            position.status = "CLOSED"
        else:
            position.unrealized_pnl = (fill_price - position.entry_price) * position.quantity
