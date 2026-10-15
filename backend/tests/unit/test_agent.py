"""
QuantX — Unit Tests for the AI Trading Agent, prompt builder, and validator.
"""

import pytest

from app.agents.llm.pricing import estimate_cost_usd, is_free_endpoint
from app.agents.prompt_builder import PromptBuilder
from app.agents.single_shot import SingleShotAnalyst
from app.agents.validator import AIDecisionValidator
from app.schemas.agent import AgentDecision, AgentMarketContext


@pytest.fixture
def market_context() -> AgentMarketContext:
    """A representative market context payload."""
    return AgentMarketContext(
        symbol="BTCUSDT",
        timestamp="2026-08-01T20:00:00Z",
        ohlcv=[{"open": 50000.0, "high": 51000.0, "low": 49500.0, "close": 50800.0, "volume": 120.5}],
        indicators={"rsi_14": 28.5, "ema_9": 50200.0, "ema_21": 49800.0},
        multi_timeframe_trend={"15m": {"rsi_14": 30.0}, "1h": {"rsi_14": 28.5}},
    )


@pytest.mark.unit
class TestSingleShotAnalyst:
    """Prompt construction and failure handling of the single-shot analyst."""

    def test_prompt_builder(self, market_context: AgentMarketContext) -> None:
        """The prompt carries the structured context through to the model."""
        prompt = PromptBuilder.build_user_prompt(market_context)
        assert "BTCUSDT" in prompt
        assert "rsi_14" in prompt

        # Values survive compaction; a trailing .0 is dropped so an integral
        # price is transmitted as an int rather than a float.
        payload = PromptBuilder.build_payload(market_context)
        assert payload["recent_candles"][-1]["c"] == 50800
        assert payload["indicators"]["rsi_14"] == pytest.approx(28.5)

    @pytest.mark.asyncio
    async def test_no_provider_degrades_to_wait(
        self, market_context: AgentMarketContext
    ) -> None:
        """With no provider the analyst yields a safe WAIT, not an exception."""
        analysis = await SingleShotAnalyst(None).analyze(market_context)
        assert analysis.succeeded is False
        assert analysis.decision.action == "WAIT"
        assert analysis.decision.confidence == 0.0
        assert "Default to WAIT" in analysis.decision.reasoning

    @pytest.mark.asyncio
    async def test_analysis_reports_latency(self, market_context: AgentMarketContext) -> None:
        """Every analysis carries real operational metadata."""
        analysis = await SingleShotAnalyst(None).analyze(market_context)
        assert analysis.latency_ms >= 0
        assert analysis.model
        assert analysis.estimated_cost_usd == 0.0  # no tokens were consumed

    @pytest.mark.asyncio
    async def test_unconfigured_explains_how_to_fix(
        self, market_context: AgentMarketContext
    ) -> None:
        """The WAIT reason names the env vars to set."""
        analysis = await SingleShotAnalyst(None).analyze(market_context)
        assert analysis.succeeded is False
        assert "OPENAI_BASE_URL" in analysis.decision.reasoning
        assert "ANTHROPIC_API_KEY" in analysis.decision.reasoning


@pytest.mark.unit
class TestCostEstimation:
    """Token-cost estimation is honest: unknown price and free endpoints -> 0."""

    def test_cost_from_token_counts(self) -> None:
        """Cost is derived from tokens and model price, not a constant."""
        cost = estimate_cost_usd("gpt-4o", {"prompt_tokens": 1_000_000, "completion_tokens": 0})
        assert cost == pytest.approx(2.50)

    @pytest.mark.parametrize(
        "base_url",
        [
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://host.docker.internal:11434/v1",
        ],
    )
    def test_local_endpoints_report_zero_cost(self, base_url: str) -> None:
        """A model on your own machine costs nothing per token."""
        assert is_free_endpoint(base_url) is True
        assert estimate_cost_usd("llama3.2:1b", {"prompt_tokens": 100_000, "completion_tokens": 50_000}, base_url) == 0.0

    def test_unknown_third_party_model_reports_zero_not_a_guess(self) -> None:
        """An unpriced model reports 0.0 rather than the gpt-4o rate."""
        base_url = "https://api.groq.com/openai/v1"
        assert is_free_endpoint(base_url) is False
        assert estimate_cost_usd("llama-3.3-70b", {"prompt_tokens": 1_000_000, "completion_tokens": 0}, base_url) == 0.0

    def test_known_openai_model_still_prices_correctly(self) -> None:
        """Real OpenAI usage is still costed."""
        assert estimate_cost_usd("gpt-4o", {"prompt_tokens": 1_000_000, "completion_tokens": 0}) == pytest.approx(2.50)


@pytest.mark.unit
class TestAIDecisionValidator:
    """Deterministic verification of model output."""

    def test_wait_is_always_valid(self) -> None:
        """A WAIT needs no levels and is always accepted."""
        result = AIDecisionValidator.validate(
            AgentDecision(action="WAIT", confidence=0.0, reasoning="no setup"),
            current_price=50_000.0,
            account_balance=10_000.0,
        )
        assert result.is_valid is True

    def test_valid_buy_passes(self) -> None:
        """A coherent BUY with matching R:R is accepted."""
        result = AIDecisionValidator.validate(
            AgentDecision(
                action="BUY",
                confidence=0.8,
                reasoning="trend",
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=115.0,
                risk_reward_ratio=3.0,
            ),
            current_price=100.0,
            account_balance=10_000.0,
        )
        assert result.is_valid is True
        assert result.calculated_risk_reward == pytest.approx(3.0)

    def test_missing_levels_rejected_without_crashing(self) -> None:
        """A directional call with no stop is rejected, not a TypeError.

        The validator previously read stop_loss_price / take_profit_price,
        fields that do not exist on AgentDecision, so every BUY or SELL raised
        AttributeError instead of being checked.
        """
        result = AIDecisionValidator.validate(
            AgentDecision(action="BUY", confidence=0.9, reasoning="vibes", entry_price=100.0),
            current_price=100.0,
            account_balance=10_000.0,
        )
        assert result.is_valid is False
        assert any("stop_loss" in r for r in result.rejection_reasons)

    def test_inverted_stop_is_rejected(self) -> None:
        """A BUY whose stop sits above entry is impossible."""
        result = AIDecisionValidator.validate(
            AgentDecision(
                action="BUY",
                confidence=0.9,
                reasoning="x",
                entry_price=100.0,
                stop_loss=105.0,
                take_profit=115.0,
                risk_reward_ratio=3.0,
            ),
            current_price=100.0,
            account_balance=10_000.0,
        )
        assert result.is_valid is False
        assert any("Impossible SL direction" in r for r in result.rejection_reasons)

    def test_misreported_risk_reward_is_rejected(self) -> None:
        """A model-stated R:R that we cannot reproduce disqualifies the signal."""
        result = AIDecisionValidator.validate(
            AgentDecision(
                action="BUY",
                confidence=0.9,
                reasoning="x",
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=105.0,   # real R:R is 1.0
                risk_reward_ratio=5.0,  # model claims 5.0
            ),
            current_price=100.0,
            account_balance=10_000.0,
        )
        assert result.is_valid is False
        assert any("does not match" in r for r in result.rejection_reasons)

    def test_oversized_position_is_rejected(self) -> None:
        """A request beyond the position cap is rejected."""
        result = AIDecisionValidator.validate(
            AgentDecision(
                action="BUY",
                confidence=0.9,
                reasoning="x",
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=115.0,
                risk_reward_ratio=3.0,
            ),
            current_price=100.0,
            account_balance=10_000.0,
            requested_position_size_usd=9_000.0,  # cap is 20% = 2000
        )
        assert result.is_valid is False
        assert any("Excessive position size" in r for r in result.rejection_reasons)


@pytest.mark.unit
class TestPromptCompactness:
    """The prompt must stay small.

    The original builder shipped full float repr (77474.1437278050) for every
    indicator across every timeframe plus fifty candles: ~13,000 characters.
    That overflowed a small model's context window outright, and on a paid
    provider it billed sixteen digits of precision nobody reads on every call.
    """

    def test_floats_are_rounded(self, market_context: AgentMarketContext) -> None:
        """No sixteen-digit floats reach the wire."""
        import re

        prompt = PromptBuilder.build_user_prompt(market_context)
        long_floats = re.findall(r"\d+\.\d{6,}", prompt)
        assert not long_floats, f"unrounded floats in prompt: {long_floats[:3]}"

    def test_candle_window_is_bounded(self) -> None:
        """Only the recent candles are sent; indicators summarize the rest."""
        from app.agents.prompt_builder import PROMPT_CANDLES

        context = AgentMarketContext(
            symbol="BTCUSDT",
            timestamp="2026-08-01T20:00:00Z",
            ohlcv=[
                {"timestamp": f"t{i}", "open": 1.0, "high": 2.0, "low": 0.5,
                 "close": 1.5, "volume": 10.0}
                for i in range(200)
            ],
            indicators={},
            multi_timeframe_trend={},
        )
        payload = PromptBuilder.build_payload(context)
        assert len(payload["recent_candles"]) == PROMPT_CANDLES

    def test_only_meaningful_indicators_are_included(self) -> None:
        """Unknown indicator columns are dropped rather than shipped."""
        context = AgentMarketContext(
            symbol="BTCUSDT",
            timestamp="2026-08-01T20:00:00Z",
            ohlcv=[],
            indicators={
                "rsi_14": 28.5123456789,
                "ichimoku_chikou": 12345.6789,
                "some_debug_column": "noise",
            },
            multi_timeframe_trend={},
        )
        indicators = PromptBuilder.build_payload(context)["indicators"]
        assert "rsi_14" in indicators
        assert "some_debug_column" not in indicators

    def test_absent_optional_context_is_omitted(self) -> None:
        """A wall of nulls teaches the model nothing and still costs tokens."""
        context = AgentMarketContext(
            symbol="BTCUSDT",
            timestamp="2026-08-01T20:00:00Z",
            ohlcv=[],
            indicators={},
            multi_timeframe_trend={},
            funding_rate=None,
            open_interest=None,
        )
        payload = PromptBuilder.build_payload(context)
        assert "funding_rate" not in payload
        assert "open_interest" not in payload
        assert "news_summary" not in payload

    def test_present_optional_context_is_included(self) -> None:
        """Real values do reach the model."""
        context = AgentMarketContext(
            symbol="BTCUSDT",
            timestamp="2026-08-01T20:00:00Z",
            ohlcv=[],
            indicators={},
            multi_timeframe_trend={},
            funding_rate=0.00012345,
            open_interest=98765.4321,
        )
        payload = PromptBuilder.build_payload(context)
        assert payload["funding_rate"] == pytest.approx(0.00012345)
        assert payload["open_interest"] == pytest.approx(98765.43)

    def test_system_prompt_specifies_the_output_shape(self) -> None:
        """The model is told the exact keys, not left to invent them."""
        for field in ("action", "confidence", "stop_loss", "take_profit", "risk_reward_ratio"):
            assert field in PromptBuilder.SYSTEM_PROMPT
        assert "Do NOT echo the input data" in PromptBuilder.SYSTEM_PROMPT

    def test_realistic_context_stays_well_under_a_small_context_window(self) -> None:
        """A full context must fit a modest local model."""
        context = AgentMarketContext(
            symbol="BTCUSDT",
            timestamp="2026-08-01T20:00:00Z",
            ohlcv=[
                {"timestamp": f"2026-08-01T{i:02d}:00:00Z", "open": 77651.061234,
                 "high": 77712.098765, "low": 77494.012345, "close": 77498.567891,
                 "volume": 16.617161234}
                for i in range(50)
            ],
            indicators={k: 77474.1437278050 for k in
                        ("close", "rsi_14", "ema_9", "ema_21", "ema_50", "ema_200",
                         "macd_line", "macd_signal", "macd_histogram", "bb_upper",
                         "bb_lower", "bb_percent_b", "atr_14", "adx_14")},
            multi_timeframe_trend={
                tf: {k: 77474.1437278050 for k in ("close", "rsi_14", "ema_9", "ema_21")}
                for tf in ("15m", "1h", "4h")
            },
        )
        prompt = PromptBuilder.build_user_prompt(context)
        # ~4 chars per token; 4000 chars leaves ample room in a 4k window.
        assert len(prompt) < 4000, f"prompt is {len(prompt)} chars"
