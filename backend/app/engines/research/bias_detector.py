"""
QuantX — Look-Ahead Bias Detector.

Enforces the causality invariant: the signal produced at bar *t* must depend
only on data up to and including bar *t*.

This is tested empirically. The strategy is evaluated at each bar twice: once
with the series truncated at that bar, and once with the full series (which
contains the future). If any signal differs, the strategy consumed data that
would not have existed at decision time.

The previous implementation returned ``has_lookahead_bias=False`` and a
correlation of 0.98 unconditionally, without executing the strategy at all.
"""

import pandas as pd
from pydantic import BaseModel

from app.engines.indicators.registry import IndicatorRegistry
from app.engines.strategy.registry import StrategyRegistry

MIN_ROWS = 80
DEFAULT_SAMPLE_POINTS = 25


class BiasViolation(BaseModel):
    """One bar where truncated and full-history signals disagreed."""

    bar_index: int
    timestamp: str
    signal_with_history_only: str
    signal_with_future_visible: str


class BiasCheckReport(BaseModel):
    """Outcome of the causality audit."""

    strategy_name: str
    has_lookahead_bias: bool
    bars_tested: int
    violations_found: int
    violations: list[BiasViolation]
    message: str


class LookAheadBiasDetector:
    """Verifies that a strategy only reacts to data available at decision time."""

    @staticmethod
    def audit_strategy(
        strategy_class_name: str,
        df_candles: pd.DataFrame,
        sample_points: int = DEFAULT_SAMPLE_POINTS,
    ) -> BiasCheckReport:
        """Audit a strategy for temporal leakage.

        Args:
            strategy_class_name: Registered strategy name.
            df_candles: Chronological OHLCV frame.
            sample_points: How many bars to test across the series.
        """
        registry = StrategyRegistry()
        strategy = registry.get(strategy_class_name)
        if strategy is None:
            return BiasCheckReport(
                strategy_name=strategy_class_name,
                has_lookahead_bias=False,
                bars_tested=0,
                violations_found=0,
                violations=[],
                message=f"Strategy '{strategy_class_name}' is not registered; nothing was audited.",
            )

        if df_candles.empty or len(df_candles) < MIN_ROWS:
            return BiasCheckReport(
                strategy_name=strategy_class_name,
                has_lookahead_bias=False,
                bars_tested=0,
                violations_found=0,
                violations=[],
                message=(
                    f"Insufficient data: {len(df_candles)} bars supplied, "
                    f"{MIN_ROWS} required to audit."
                ),
            )

        indicators = IndicatorRegistry()
        full = indicators.compute_all(df_candles).reset_index(drop=True)

        start = MIN_ROWS // 2
        step = max(1, (len(full) - start) // max(1, sample_points))
        test_indices = list(range(start, len(full), step))[:sample_points]

        violations: list[BiasViolation] = []
        for index in test_indices:
            # Indicators recomputed on truncated data — the honest view.
            truncated = indicators.compute_all(
                df_candles.iloc[: index + 1].reset_index(drop=True)
            )
            causal = strategy.generate_signal(
                symbol="AUDIT", timeframe="audit", df=truncated
            )
            # Indicators computed over the whole series, then sliced — this
            # view can contain forward-looking values (e.g. a centred window
            # or a negative shift).
            leaky = strategy.generate_signal(
                symbol="AUDIT", timeframe="audit", df=full.iloc[: index + 1]
            )

            if causal.action != leaky.action:
                violations.append(
                    BiasViolation(
                        bar_index=index,
                        timestamp=str(full.iloc[index]["timestamp"]),
                        signal_with_history_only=causal.action,
                        signal_with_future_visible=leaky.action,
                    )
                )

        has_bias = bool(violations)
        return BiasCheckReport(
            strategy_name=strategy_class_name,
            has_lookahead_bias=has_bias,
            bars_tested=len(test_indices),
            violations_found=len(violations),
            violations=violations[:20],
            message=(
                f"Look-ahead bias detected: {len(violations)} of {len(test_indices)} "
                "sampled bars produced a different signal once future data was visible."
                if has_bias
                else f"No look-ahead bias detected across {len(test_indices)} sampled bars: "
                "signals were identical with and without future data."
            ),
        )
