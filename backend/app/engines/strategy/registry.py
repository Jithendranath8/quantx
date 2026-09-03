"""
QuantX — Strategy Registry.

Registers quantitative strategies and constructs parameterized instances.

``build`` exists so the optimization engine can actually vary a strategy's
parameters. Without it the registry only ever hands back one fixed instance,
which is why parameter search had nothing real to search over.
"""

import inspect
from typing import Any

from app.engines.strategy.base import BaseStrategy
from app.engines.strategy.strategies import (
    BollingerBreakoutStrategy,
    EMACrossoverStrategy,
    MACDMomentumStrategy,
    MultiTimeframeTrendStrategy,
    RSIMeanReversionStrategy,
)

STRATEGY_CLASSES: dict[str, type[BaseStrategy]] = {
    EMACrossoverStrategy.name: EMACrossoverStrategy,
    RSIMeanReversionStrategy.name: RSIMeanReversionStrategy,
    MACDMomentumStrategy.name: MACDMomentumStrategy,
    BollingerBreakoutStrategy.name: BollingerBreakoutStrategy,
    MultiTimeframeTrendStrategy.name: MultiTimeframeTrendStrategy,
}

# Search spaces used by the optimizer when the caller does not supply one.
# Values must correspond to constructor keyword arguments.
DEFAULT_PARAM_GRIDS: dict[str, dict[str, list[Any]]] = {
    "ema_crossover": {
        "fast_col": ["ema_9", "ema_21"],
        "slow_col": ["ema_21", "ema_50", "ema_200"],
    },
    "rsi_mean_reversion": {
        "oversold": [20.0, 25.0, 30.0, 35.0],
        "overbought": [65.0, 70.0, 75.0, 80.0],
    },
    "macd_momentum": {},
    "bollinger_breakout": {},
    "mtf_trend": {},
}


class StrategyRegistry:
    """Strategy Registry managing active quantitative strategies."""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Instantiate every known strategy with its default parameters."""
        for cls in STRATEGY_CLASSES.values():
            self.register(cls())

    def register(self, strategy: BaseStrategy) -> None:
        """Register a strategy instance under its name."""
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> BaseStrategy | None:
        """Retrieve the default instance of a strategy by name."""
        return self._strategies.get(name)

    @staticmethod
    def build(name: str, **params: Any) -> BaseStrategy:
        """Construct a strategy with specific parameters.

        Unknown keyword arguments are dropped rather than raising, so a shared
        parameter grid can be applied across strategies with different
        constructors.

        Raises:
            KeyError: If the strategy name is not registered.
        """
        cls = STRATEGY_CLASSES[name]
        signature = inspect.signature(cls.__init__)
        accepted = {
            key: value for key, value in params.items() if key in signature.parameters
        }
        return cls(**accepted)

    @staticmethod
    def default_param_grid(name: str) -> dict[str, list[Any]]:
        """Default search space for a strategy, empty when it has no parameters."""
        return DEFAULT_PARAM_GRIDS.get(name, {})

    def list_strategies(self) -> list[dict[str, str]]:
        """List metadata for all registered strategies."""
        return [
            {"name": strat.name, "description": strat.description}
            for strat in self._strategies.values()
        ]
