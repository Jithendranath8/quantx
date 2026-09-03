"""
QuantX — AI Decision Validator.

Independent deterministic validator that verifies model-generated trade
decisions against authoritative backend calculations before any risk check or
order execution.

Never trust model-generated numbers blindly: the model's own reported
risk:reward is recomputed here from its own prices, and a mismatch is a
rejection, not a rounding note.
"""

from pydantic import BaseModel

from app.schemas.agent import AgentDecision

# The model's stated R:R may differ from ours by rounding; anything larger
# means it did arithmetic we cannot reproduce, which disqualifies the signal.
RR_TOLERANCE = 0.15
MIN_ACCEPTABLE_RR = 1.0


class ValidationResult(BaseModel):
    """Outcome of deterministic validation of an AI decision."""

    is_valid: bool
    rejection_reasons: list[str]
    calculated_risk_reward: float
    calculated_position_size_usd: float


class AIDecisionValidator:
    """Independent deterministic validator verifying AI Agent recommendations."""

    @staticmethod
    def validate(
        decision: AgentDecision,
        current_price: float,
        account_balance: float,
        max_position_size_pct: float = 0.20,
        requested_position_size_usd: float | None = None,
    ) -> ValidationResult:
        """Check an AI decision against backend-computed truth.

        Args:
            decision: The model's structured output.
            current_price: Authoritative market price from the exchange.
            account_balance: Balance used for position sizing.
            max_position_size_pct: Hard cap as a fraction of balance.
            requested_position_size_usd: Size the caller intends to trade;
                defaults to the maximum allowed.

        Returns:
            ValidationResult carrying every reason the decision was rejected.
        """
        if decision.action in {"WAIT", "HOLD"}:
            return ValidationResult(
                is_valid=True,
                rejection_reasons=[],
                calculated_risk_reward=0.0,
                calculated_position_size_usd=0.0,
            )

        rejections: list[str] = []

        entry = decision.entry_price or current_price
        stop_loss = decision.stop_loss
        take_profit = decision.take_profit

        # 1. Structural completeness. A directional call without levels cannot
        #    be sized or risk-managed, so it is rejected before any arithmetic.
        if entry is None or entry <= 0:
            rejections.append(f"Invalid entry price: {entry}")
        if stop_loss is None:
            rejections.append("Missing stop_loss for a directional decision")
        if take_profit is None:
            rejections.append("Missing take_profit for a directional decision")

        max_size_allowed = account_balance * max_position_size_pct
        calculated_size = (
            requested_position_size_usd if requested_position_size_usd is not None else max_size_allowed
        )

        if rejections:
            return ValidationResult(
                is_valid=False,
                rejection_reasons=rejections,
                calculated_risk_reward=0.0,
                calculated_position_size_usd=round(max(0.0, calculated_size), 2),
            )

        # 2. Price sanity: the stop must be on the losing side of entry and the
        #    target on the winning side, for the stated direction.
        if decision.action == "BUY":
            if stop_loss >= entry:
                rejections.append(f"Impossible SL direction for BUY: SL ({stop_loss}) >= Entry ({entry})")
            if take_profit <= entry:
                rejections.append(f"Impossible TP direction for BUY: TP ({take_profit}) <= Entry ({entry})")
        elif decision.action == "SELL":
            if stop_loss <= entry:
                rejections.append(f"Impossible SL direction for SELL: SL ({stop_loss}) <= Entry ({entry})")
            if take_profit >= entry:
                rejections.append(f"Impossible TP direction for SELL: TP ({take_profit}) >= Entry ({entry})")

        # 3. Authoritative risk:reward, recomputed from the model's own prices.
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        calculated_rr = (reward / risk) if risk > 0 else 0.0

        if (
            decision.risk_reward_ratio is not None
            and abs(calculated_rr - decision.risk_reward_ratio) > RR_TOLERANCE
        ):
            rejections.append(
                f"AI reported R:R ({decision.risk_reward_ratio:.2f}) does not match "
                f"backend calculation ({calculated_rr:.2f})"
            )

        if calculated_rr < MIN_ACCEPTABLE_RR:
            rejections.append(f"Unfavorable Risk:Reward ratio ({calculated_rr:.2f} < {MIN_ACCEPTABLE_RR})")

        # 4. Sizing and margin.
        if calculated_size > max_size_allowed:
            rejections.append(
                f"Excessive position size requested (${calculated_size:.2f} > max allowed ${max_size_allowed:.2f})"
            )
        if calculated_size > account_balance:
            rejections.append(
                f"Insufficient margin balance (${account_balance:.2f} < ${calculated_size:.2f})"
            )

        return ValidationResult(
            is_valid=not rejections,
            rejection_reasons=rejections,
            calculated_risk_reward=round(calculated_rr, 2),
            calculated_position_size_usd=round(calculated_size, 2),
        )
