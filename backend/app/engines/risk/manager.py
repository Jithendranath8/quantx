"""
QuantX — Deterministic Risk Engine Manager.

Enforces strict, non-overrideable risk management rules.
AI signals CANNOT override hard risk limits.

This class is intentionally **pure**: ``validate_trade`` derives a decision
from its inputs and never mutates shared state. Persisting a triggered circuit
breaker is the caller's job (see :class:`~app.services.risk_state_service.RiskStateService`),
because in-process mutation is invisible to other workers and lost on restart.
"""

from app.schemas.risk import RiskCheckResult, RiskConfig, TradeRiskRequest


class RiskManager:
    """Institutional Risk Engine enforcing strict deterministic risk checks."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def validate_trade(self, request: TradeRiskRequest) -> RiskCheckResult:
        """Validate proposed trade against all active hard risk rules.

        Returns:
            RiskCheckResult with approval status, max allowed position size,
            and rejection reason if unapproved. When ``circuit_breaker_triggered``
            is True the caller MUST persist the halt before returning to the user.
        """
        # 1. Circuit Breaker Check
        if self.config.circuit_breaker_active:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason="Circuit breaker is ACTIVE. Trading is currently halted.",
                max_allowed_position_size_usd=0.0,
                recommended_position_size_usd=0.0,
                circuit_breaker_triggered=True,
            )

        # 2. Max Daily Loss Check
        max_daily_loss_usd = request.account_balance * self.config.max_daily_loss_pct
        if request.current_daily_loss_usd >= max_daily_loss_usd:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=(
                    f"Max daily loss exceeded (${request.current_daily_loss_usd:.2f} >= "
                    f"${max_daily_loss_usd:.2f}). Circuit breaker engaged."
                ),
                max_allowed_position_size_usd=0.0,
                recommended_position_size_usd=0.0,
                circuit_breaker_triggered=True,
            )

        # 2b. Cooldown after a losing exit in the same symbol: no revenge trades.
        if (
            request.minutes_since_loss_on_symbol is not None
            and request.minutes_since_loss_on_symbol < self.config.cooldown_period_minutes
        ):
            remaining = self.config.cooldown_period_minutes - request.minutes_since_loss_on_symbol
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=(
                    f"Cooldown: {request.symbol} closed at a loss {request.minutes_since_loss_on_symbol:.0f} min ago; "
                    f"buying it again is blocked for another {remaining:.0f} min."
                ),
                max_allowed_position_size_usd=0.0,
                recommended_position_size_usd=0.0,
            )

        # 3. Max Leverage Check
        if request.leverage > self.config.max_leverage:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=f"Leverage {request.leverage}x exceeds maximum allowed {self.config.max_leverage}x.",
                max_allowed_position_size_usd=0.0,
                recommended_position_size_usd=0.0,
            )

        # 4. Max Concurrent Trades Check
        if request.active_positions_count >= self.config.max_concurrent_trades:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=(
                    f"Active position limit reached ({request.active_positions_count} >= "
                    f"{self.config.max_concurrent_trades})."
                ),
                max_allowed_position_size_usd=0.0,
                recommended_position_size_usd=0.0,
            )

        # 5. Portfolio Exposure Check
        max_exposure_usd = request.account_balance * self.config.max_portfolio_exposure_pct
        new_exposure_usd = request.current_exposure_usd + request.order_amount_usd
        if new_exposure_usd > max_exposure_usd:
            allowed_additional = max(0.0, max_exposure_usd - request.current_exposure_usd)
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=f"New portfolio exposure (${new_exposure_usd:.2f}) exceeds limit (${max_exposure_usd:.2f}).",
                max_allowed_position_size_usd=allowed_additional,
                recommended_position_size_usd=allowed_additional,
            )

        # 6. Risk Per Trade Sizing
        max_risk_amount = request.account_balance * self.config.max_risk_per_trade_pct

        if request.stop_loss_price and request.entry_price > 0:
            sl_distance_pct = abs(request.entry_price - request.stop_loss_price) / request.entry_price
            recommended_position_usd = (
                max_risk_amount / sl_distance_pct
                if sl_distance_pct > 0
                else max_risk_amount * 5
            )
        else:
            recommended_position_usd = max_risk_amount * 5

        final_position_size = min(request.order_amount_usd, recommended_position_usd, max_exposure_usd)

        return RiskCheckResult(
            is_approved=True,
            rejection_reason=None,
            max_allowed_position_size_usd=max_exposure_usd,
            recommended_position_size_usd=final_position_size,
        )


def oversize_reason(request: TradeRiskRequest, result: RiskCheckResult) -> str | None:
    """Why an approved order is still too large for the per-trade risk budget, if it is.

    ``validate_trade`` approves an order and *recommends* a smaller size; an
    executing caller must refuse the excess rather than silently fill it.
    Half a cent of slack absorbs float rounding in the sizing arithmetic.
    """
    if not result.is_approved or request.order_amount_usd <= result.recommended_position_size_usd + 0.005:
        return None
    basis = "for this stop distance" if request.stop_loss_price else "without a stop loss"
    return (
        f"Order of ${request.order_amount_usd:,.2f} exceeds the risk-per-trade limit of "
        f"${result.recommended_position_size_usd:,.2f} {basis}."
    )
