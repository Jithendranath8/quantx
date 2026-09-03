"""
QuantX — Analytics & Portfolio API Endpoints.

Portfolio summaries and trade-log export. The export streams and is scoped to
the requesting user; it previously returned every user's orders in one string.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.analytics import PortfolioSummary
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/analytics", tags=["Analytics & Portfolio"])


@router.get(
    "/portfolio",
    response_model=PortfolioSummary,
    summary="Get overall portfolio performance summary",
)
async def get_portfolio(user: CurrentUser, db: DBSession) -> PortfolioSummary:
    """Aggregate equity, cash, PnL and allocation across your accounts."""
    return await PortfolioService(db).get_portfolio_summary(user.id)


@router.get(
    "/export/csv",
    summary="Export your trade history as CSV",
)
async def export_trades_csv(user: CurrentUser, db: DBSession) -> StreamingResponse:
    """Stream your own order history as a downloadable CSV."""
    return StreamingResponse(
        PortfolioService(db).stream_trades_csv(user.id),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quantx_trade_history.csv"},
    )
