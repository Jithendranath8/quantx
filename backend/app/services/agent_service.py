"""
QuantX — AI Agent Service.

Assembles real market context (klines, indicators, MTF trend, funding, OI,
open positions), invokes the AI agent, validates its output deterministically,
and records the decision for observability.

Context is built from stored data only. Feeding the model invented funding
rates or news lines produces confident output derived from fiction, which is
worse than a WAIT caused by missing data.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trading_agent import AgentAnalysis, AITradingAgent
from app.agents.validator import AIDecisionValidator, ValidationResult
from app.core.logging import get_logger
from app.engines.indicators.multi_timeframe import MultiTimeframeEngine
from app.models.market_data import Candle, FundingRate, OpenInterest
from app.models.paper_trading import PaperAccount, PaperPosition
from app.schemas.agent import AgentDecision, AgentMarketContext
from app.services.ai_observability_service import AIObservabilityService

logger = get_logger(__name__)

CONTEXT_CANDLES = 50
CONTEXT_TIMEFRAMES = ["15m", "1h", "4h"]


class AgentService:
    """Service orchestrating context assembly, AI evaluation, and validation."""

    def __init__(self, session: AsyncSession, agent: AITradingAgent | None = None) -> None:
        self._session = session
        self._agent = agent or AITradingAgent()
        self._mtf_engine = MultiTimeframeEngine(session)
        self._observability = AIObservabilityService(session)

    async def evaluate_symbol(
        self,
        symbol: str,
        user_id: uuid.UUID | None = None,
        account_balance: float = 100_000.0,
    ) -> AgentDecision:
        """Build market context for a symbol and evaluate it with the AI agent.

        The decision is validated against backend arithmetic before it is
        returned; a decision that fails validation is downgraded to WAIT.
        """
        symbol = symbol.upper()
        context = await self.build_context(symbol, user_id)
        analysis = await self._agent.analyze(context)

        current_price = self._latest_close(context)
        validation = AIDecisionValidator.validate(
            decision=analysis.decision,
            current_price=current_price,
            account_balance=account_balance,
        )

        decision = analysis.decision
        if not validation.is_valid:
            logger.warning(
                "ai_decision_rejected_by_validator",
                symbol=symbol,
                action=decision.action,
                reasons=validation.rejection_reasons,
            )
            decision = AgentDecision(
                action="WAIT",
                confidence=0.0,
                reasoning=(
                    "Decision rejected by deterministic validator: "
                    + "; ".join(validation.rejection_reasons)
                ),
            )

        await self._record(symbol, context, analysis, validation, user_id)
        return decision

    async def build_context(self, symbol: str, user_id: uuid.UUID | None = None) -> AgentMarketContext:
        """Assemble the structured market snapshot handed to the model."""
        symbol = symbol.upper()

        candles = await self._recent_candles(symbol)
        mtf_indicators = await self._mtf_engine.get_multi_timeframe_indicators(
            symbol=symbol,
            timeframes=CONTEXT_TIMEFRAMES,
        )
        funding_rate = await self._latest_funding_rate(symbol)
        open_interest = await self._latest_open_interest(symbol)
        positions, exposure = await self._open_positions(user_id, symbol)

        return AgentMarketContext(
            symbol=symbol,
            timestamp=datetime.now(UTC).isoformat(),
            ohlcv=candles,
            indicators=mtf_indicators.get("1h", {}),
            multi_timeframe_trend=mtf_indicators,
            funding_rate=funding_rate,
            open_interest=open_interest,
            existing_positions=positions,
            portfolio_exposure=exposure,
            # No news ingestion pipeline exists, so the model is told nothing
            # rather than being handed a fabricated headline.
            news_summary=[],
        )

    # ── Context builders ─────────────────────────────────────────────

    async def _recent_candles(self, symbol: str) -> list[dict]:
        """Load the most recent 1h candles in chronological order."""
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol, Candle.timeframe == "1h")
            .order_by(Candle.timestamp.desc())
            .limit(CONTEXT_CANDLES)
        )
        candles = list((await self._session.execute(stmt)).scalars().all())
        return [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in reversed(candles)
        ]

    async def _latest_funding_rate(self, symbol: str) -> float | None:
        """Most recently stored funding rate, or None when never ingested."""
        stmt = (
            select(FundingRate.rate)
            .where(FundingRate.symbol == symbol)
            .order_by(FundingRate.timestamp.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _latest_open_interest(self, symbol: str) -> float | None:
        """Most recently stored open interest, or None when never ingested."""
        stmt = (
            select(OpenInterest.open_interest)
            .where(OpenInterest.symbol == symbol)
            .order_by(OpenInterest.timestamp.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _open_positions(
        self,
        user_id: uuid.UUID | None,
        symbol: str,
    ) -> tuple[list[dict], dict]:
        """Load the caller's open positions and total exposure."""
        if user_id is None:
            return [], {"total_exposure_usd": 0.0, "symbol_exposure_usd": 0.0}

        stmt = (
            select(PaperPosition)
            .join(PaperAccount, PaperAccount.id == PaperPosition.account_id)
            .where(PaperAccount.user_id == user_id, PaperPosition.status == "OPEN")
        )
        positions = list((await self._session.execute(stmt)).scalars().all())

        total = sum(p.current_price * p.quantity for p in positions)
        symbol_total = sum(p.current_price * p.quantity for p in positions if p.symbol == symbol)

        return (
            [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in positions
            ],
            {
                "total_exposure_usd": round(total, 2),
                "symbol_exposure_usd": round(symbol_total, 2),
                "open_position_count": len(positions),
            },
        )

    @staticmethod
    def _latest_close(context: AgentMarketContext) -> float:
        """Latest close from the assembled context, or 0.0 when no data."""
        return float(context.ohlcv[-1]["close"]) if context.ohlcv else 0.0

    async def _record(
        self,
        symbol: str,
        context: AgentMarketContext,
        analysis: AgentAnalysis,
        validation: ValidationResult,
        user_id: uuid.UUID | None,
    ) -> None:
        """Persist the decision with its real latency, tokens, and cost."""
        try:
            await self._observability.log_decision(
                model=analysis.model,
                symbol=symbol,
                input_snapshot={
                    "symbol": symbol,
                    "candle_count": len(context.ohlcv),
                    "timeframes": CONTEXT_TIMEFRAMES,
                    "funding_rate": context.funding_rate,
                    "open_interest": context.open_interest,
                },
                output_decision=analysis.decision.model_dump(),
                confidence=analysis.decision.confidence,
                action=analysis.decision.action,
                latency_ms=analysis.latency_ms,
                token_usage=analysis.token_usage,
                estimated_cost_usd=analysis.estimated_cost_usd,
                was_validated=validation.is_valid,
                validation_rejection_reason=(
                    "; ".join(validation.rejection_reasons) if validation.rejection_reasons else None
                ),
                user_id=user_id,
            )
        except Exception as exc:
            logger.error("ai_decision_log_failed", symbol=symbol, error=str(exc))
