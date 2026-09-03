"""
QuantX — AI Agent Prompt Builder.

Builds a compact, strictly-specified prompt from the structured market context.

Compactness is not cosmetic. The raw context carries full float repr
(``77474.1437278050``) for every indicator across every timeframe plus fifty
candles, which came to roughly 13,000 characters. That overflowed a small
model's context window outright, and on a paid provider it is tokens billed on
every single call to transmit sixteen digits of precision nobody uses.
"""

import json
from typing import Any

from app.schemas.agent import AgentMarketContext

# Candles the model actually reasons over. Indicators already summarize the
# longer history, so a deep raw window mostly adds tokens.
PROMPT_CANDLES = 20

# Indicators worth showing, in the order a human would read them. Anything
# else in the summary is dropped rather than shipped at full precision.
PROMPT_INDICATORS = (
    "close",
    "rsi_14",
    "ema_9",
    "ema_21",
    "ema_50",
    "ema_200",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_lower",
    "bb_percent_b",
    "atr_14",
    "adx_14",
    "stoch_k",
    "stoch_d",
)

PRICE_DECIMALS = 2
RATIO_DECIMALS = 4


def _round(value: Any, decimals: int = PRICE_DECIMALS) -> Any:
    """Round floats for transmission; pass anything else through untouched."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        rounded = round(float(value), decimals)
        # Drop a pointless trailing .0 so ints stay ints in the JSON.
        return int(rounded) if rounded.is_integer() and abs(rounded) < 1e15 else rounded
    return value


def _compact_indicators(values: dict[str, Any]) -> dict[str, Any]:
    """Keep the indicators that inform a decision, at readable precision."""
    out: dict[str, Any] = {}
    for key in PROMPT_INDICATORS:
        if key not in values:
            continue
        value = values[key]
        if value is None:
            continue
        # Oscillators and ratios need more decimals than a price does.
        decimals = RATIO_DECIMALS if key in {"bb_percent_b", "macd_histogram"} else PRICE_DECIMALS
        out[key] = _round(value, decimals)
    return out


class PromptBuilder:
    """Prompt Builder for the AI Quantitative Analyst."""

    SYSTEM_PROMPT = """You are QuantX-AI, an institutional-grade Quantitative Trading Analyst.
Analyze structured quantitative market data and issue one precise trading decision.

STRICT RULES:
1. Output ONLY a single JSON object. No prose, no markdown, no code fences.
2. Do NOT echo the input data back. Return only the decision object below.
3. "action" MUST be exactly one of: "BUY", "SELL", "WAIT".
4. Base decisions solely on the supplied JSON. You never see chart images.
5. If indicators conflict, the trend is unclear, or data is insufficient, output "WAIT".
6. For "BUY" or "SELL" you MUST supply entry_price, stop_loss, take_profit,
   invalidation_level and risk_reward_ratio, with confidence above 0.65 and a
   risk_reward_ratio of at least 1.5. A stop must sit on the losing side of
   entry and a target on the winning side.

Respond with exactly this shape:
{
  "action": "BUY" | "SELL" | "WAIT",
  "confidence": 0.0-1.0,
  "reasoning": "one or two sentences",
  "entry_price": number | null,
  "stop_loss": number | null,
  "take_profit": number | null,
  "invalidation_level": number | null,
  "risk_reward_ratio": number | null
}"""

    @classmethod
    def build_user_prompt(cls, context: AgentMarketContext) -> str:
        """Render the market context as compact JSON for the model."""
        return f"""Analyze this market context and return your decision JSON:

```json
{json.dumps(cls.build_payload(context), separators=(",", ":"))}
```"""

    @classmethod
    def build_payload(cls, context: AgentMarketContext) -> dict[str, Any]:
        """Build the trimmed, rounded payload sent to the model."""
        candles = [
            {
                "t": c.get("timestamp"),
                "o": _round(c.get("open")),
                "h": _round(c.get("high")),
                "l": _round(c.get("low")),
                "c": _round(c.get("close")),
                "v": _round(c.get("volume"), RATIO_DECIMALS),
            }
            for c in context.ohlcv[-PROMPT_CANDLES:]
        ]

        payload: dict[str, Any] = {
            "symbol": context.symbol,
            "timestamp": context.timestamp,
            "recent_candles": candles,
            "indicators": _compact_indicators(context.indicators),
            "multi_timeframe": {
                tf: _compact_indicators(values)
                for tf, values in context.multi_timeframe_trend.items()
                if values
            },
        }

        # Only include optional context that actually has a value; a wall of
        # nulls teaches the model nothing and still costs tokens.
        if context.funding_rate is not None:
            payload["funding_rate"] = _round(context.funding_rate, 8)
        if context.open_interest is not None:
            payload["open_interest"] = _round(context.open_interest)
        if context.existing_positions:
            payload["existing_positions"] = context.existing_positions
        if context.portfolio_exposure:
            payload["portfolio_exposure"] = context.portfolio_exposure
        if context.news_summary:
            payload["news_summary"] = context.news_summary

        return payload
