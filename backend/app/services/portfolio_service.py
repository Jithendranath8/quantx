"""
QuantX — Analytics & Portfolio Service.

Aggregates account balances, open position values, realized/unrealized PnL,
asset allocation breakdowns, and exports trade logs to CSV.

Every query is scoped to the requesting user. An unscoped ``select(PaperOrder)``
returns every user's orders, which is a cross-tenant data leak in an export
endpoint that presents itself as "your trade history".
"""

import csv
import io
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.paper_trading import PaperAccount, PaperOrder, PaperPosition
from app.schemas.analytics import AssetAllocation, PortfolioSummary

CSV_HEADER = [
    "order_id",
    "account_id",
    "symbol",
    "side",
    "order_type",
    "quantity",
    "price",
    "filled_price",
    "filled_quantity",
    "status",
    "created_at",
]


class PortfolioService:
    """Service calculating portfolio metrics and exporting trade logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_portfolio_summary(self, user_id: uuid.UUID) -> PortfolioSummary:
        """Calculate the aggregate portfolio summary across the user's accounts.

        A user with no accounts gets a genuinely empty portfolio, not an
        invented six-figure balance.
        """
        accounts = list(
            (
                await self._session.execute(
                    select(PaperAccount).where(
                        PaperAccount.user_id == user_id,
                        PaperAccount.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

        if not accounts:
            return PortfolioSummary(
                total_equity_usd=0.0,
                cash_balance_usd=0.0,
                realized_pnl_usd=0.0,
                unrealized_pnl_usd=0.0,
                win_rate_pct=None,
                total_trades_count=0,
                closed_trades_count=0,
                open_positions_count=0,
                allocations=[],
            )

        account_ids = [a.id for a in accounts]
        total_cash = sum(a.current_balance for a in accounts)
        realized_pnl = sum(a.realized_pnl for a in accounts)

        positions = list(
            (
                await self._session.execute(
                    select(PaperPosition).where(
                        PaperPosition.account_id.in_(account_ids),
                        PaperPosition.status == "OPEN",
                    )
                )
            )
            .scalars()
            .all()
        )

        unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        positions_value = sum(p.current_price * p.quantity for p in positions)
        total_equity = total_cash + positions_value

        total_orders = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(PaperOrder)
                    .where(PaperOrder.account_id.in_(account_ids))
                )
            ).scalar_one()
        )

        closed_count, wins = await self._closed_position_stats(account_ids)

        allocations = [
            AssetAllocation(
                symbol="USDT (Cash)",
                allocation_pct=round(total_cash / total_equity * 100, 2) if total_equity > 0 else 100.0,
                value_usd=round(total_cash, 2),
            )
        ]
        for position in positions:
            value = position.current_price * position.quantity
            allocations.append(
                AssetAllocation(
                    symbol=position.symbol,
                    allocation_pct=round(value / total_equity * 100, 2) if total_equity > 0 else 0.0,
                    value_usd=round(value, 2),
                )
            )

        return PortfolioSummary(
            total_equity_usd=round(total_equity, 2),
            cash_balance_usd=round(total_cash, 2),
            realized_pnl_usd=round(realized_pnl, 2),
            unrealized_pnl_usd=round(unrealized_pnl, 2),
            win_rate_pct=round(wins / closed_count * 100, 2) if closed_count else None,
            total_trades_count=total_orders,
            closed_trades_count=closed_count,
            open_positions_count=len(positions),
            allocations=allocations,
        )

    async def stream_trades_csv(self, user_id: uuid.UUID) -> AsyncIterator[str]:
        """Stream the user's order history as CSV rows.

        Yielding in batches keeps peak memory flat regardless of history size,
        unlike building one string for the entire table.
        """
        settings = get_settings()
        account_ids = select(PaperAccount.id).where(PaperAccount.user_id == user_id)

        yield self._csv_row(CSV_HEADER)

        batch_size = 1000
        offset = 0
        emitted = 0
        while emitted < settings.export_max_rows:
            rows = list(
                (
                    await self._session.execute(
                        select(PaperOrder)
                        .where(PaperOrder.account_id.in_(account_ids))
                        .order_by(PaperOrder.created_at.desc())
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break

            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for order in rows:
                writer.writerow(
                    [
                        str(order.id),
                        str(order.account_id),
                        order.symbol,
                        order.side,
                        order.order_type,
                        order.quantity,
                        order.price,
                        order.filled_price,
                        order.filled_quantity,
                        order.status,
                        order.created_at.isoformat() if order.created_at else "",
                    ]
                )
            yield buffer.getvalue()

            emitted += len(rows)
            offset += batch_size
            if len(rows) < batch_size:
                break

    # ── Internals ────────────────────────────────────────────────────

    async def _closed_position_stats(self, account_ids: list[uuid.UUID]) -> tuple[int, int]:
        """Count closed positions and how many of them were profitable."""
        result = (
            await self._session.execute(
                select(
                    func.count().label("closed"),
                    func.sum(
                        case((PaperPosition.realized_pnl > 0, 1), else_=0)
                    ).label("wins"),
                ).where(
                    PaperPosition.account_id.in_(account_ids),
                    PaperPosition.status == "CLOSED",
                )
            )
        ).one()
        return int(result.closed or 0), int(result.wins or 0)

    @staticmethod
    def _csv_row(values: list[str]) -> str:
        """Render one CSV row as a string."""
        buffer = io.StringIO()
        csv.writer(buffer).writerow(values)
        return buffer.getvalue()
