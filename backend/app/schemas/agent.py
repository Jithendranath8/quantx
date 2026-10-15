"""
QuantX — AI Trading Agent Schemas.

Defines structured JSON inputs and outputs for OpenAI LLM quantitative evaluation.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentMarketContext(BaseModel):
    """Structured JSON input payload provided to the AI Agent."""

    symbol: str
    timestamp: str
    ohlcv: list[dict[str, Any]]
    indicators: dict[str, Any]
    multi_timeframe_trend: dict[str, Any]
    funding_rate: float | None = None
    open_interest: float | None = None
    existing_positions: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_exposure: dict[str, Any] = Field(default_factory=dict)
    news_summary: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    """Structured JSON output returned by the AI Agent."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["BUY", "SELL", "WAIT"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    reasoning: str = Field(..., description="Detailed quantitative reasoning")
    entry_price: float | None = Field(None, description="Recommended entry price")
    stop_loss: float | None = Field(None, description="Recommended stop loss level")
    take_profit: float | None = Field(None, description="Recommended take profit level")
    invalidation_level: float | None = Field(None, description="Price level invalidating signal")
    risk_reward_ratio: float | None = Field(None, description="Calculated Risk to Reward ratio")


class OrchestrationResponse(BaseModel):
    """Result of a multi-agent orchestration run for one symbol."""

    symbol: str
    decision: dict[str, Any] | None = Field(None, description="Final validated decision")
    reports: dict[str, str] = Field(default_factory=dict, description="Per-specialist summaries")
    halted: bool = False
    market_price: float | None = None
    executed_order: dict[str, Any] | None = Field(None, description="Paper order placed, if any")
    log: list[str] = Field(default_factory=list, description="Ordered run log")
