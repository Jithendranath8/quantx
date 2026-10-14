"""
QuantX — Event-Driven Backtesting Engine.

Iterates through historical candles, computes indicators once up front,
evaluates strategy signals, simulates fills with fees and slippage, honours
stop-loss / take-profit, and tracks the equity curve.

Performance note
----------------
The strategy is handed only the trailing rows it declares it needs
(``strategy.lookback``) rather than the whole history-to-date. Slicing
``df.iloc[:i+1]`` every bar copies a linearly growing frame, making the run
O(n^2): ~1000 candles meant ~500,000 row-copies per backtest, all of it on
whichever thread called ``run``.
"""

from typing import Any

import pandas as pd

from app.engines.backtest.metrics import PerformanceMetricsCalculator
from app.engines.indicators.registry import IndicatorRegistry
from app.engines.strategy.base import BaseStrategy
from app.engines.strategy.registry import StrategyRegistry
from app.schemas.backtest import BacktestRequest, BacktestResult, EquityPoint

# Bars consumed before trading starts, so slow indicators (EMA200, Ichimoku)
# have warmed up and are not emitting NaN-driven signals.
WARMUP_BARS = 25


class BacktestEngine:
    """Event-driven simulator for historical quantitative backtesting."""

    def __init__(
        self,
        request: BacktestRequest,
        strategy: BaseStrategy | None = None,
    ) -> None:
        self.request = request
        self._strategy_registry = StrategyRegistry()
        self._indicator_registry = IndicatorRegistry()
        # Explicit override lets the optimizer score a specific
        # parameterization instead of the registry's default instance.
        self._strategy_override = strategy

    def run(self, df_candles: pd.DataFrame) -> BacktestResult:
        """Run the backtest simulation over a candle DataFrame.

        Args:
            df_candles: DataFrame with 'timestamp', 'open', 'high', 'low',
                'close', 'volume', ordered oldest-first.

        Returns:
            BacktestResult with performance metrics, equity curve, and trades.

        Raises:
            ValueError: If the requested strategy is not registered.
        """
        if df_candles.empty or len(df_candles) < WARMUP_BARS + 5:
            return self._empty_result()

        strategy = self._strategy_override or self._strategy_registry.get(
            self.request.strategy_name
        )
        if strategy is None:
            raise ValueError(f"Strategy '{self.request.strategy_name}' not found")

        df = self._indicator_registry.compute_all(df_candles).reset_index(drop=True)
        lookback = max(2, getattr(strategy, "lookback", 2))

        fee_rate = self.request.fee_rate
        slippage = self.request.slippage

        capital = self.request.initial_capital
        position: dict[str, float | str] | None = None
        trades: list[dict[str, Any]] = []
        equity_curve: list[EquityPoint] = []
        equity_values: list[float] = []
        rolling_max = capital

        # Column access via numpy is materially faster than repeated .iloc
        # scalar lookups inside the bar loop.
        closes = df["close"].to_numpy(dtype=float)
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        timestamps = df["timestamp"].astype(str).to_numpy()

        for i in range(WARMUP_BARS, len(df)):
            price = closes[i]
            timestamp = str(timestamps[i])

            # 1. Resolve stops/targets on the OPEN position first, using this
            #    bar's range. Doing this before the new signal prevents a bar
            #    from both stopping out and re-entering on the same close.
            if position is not None:
                exit_price, exit_reason = self._check_exit_levels(position, highs[i], lows[i])
                if exit_price is not None:
                    capital, trade = self._close_position(
                        position, exit_price, timestamp, capital, fee_rate, exit_reason
                    )
                    trades.append(trade)
                    position = None

            # 2. Evaluate the strategy on a bounded trailing window.
            window = df.iloc[max(0, i - lookback + 1) : i + 1]
            signal = strategy.generate_signal(
                symbol=self.request.symbol,
                timeframe=self.request.timeframe,
                df=window,
            )

            # 3. Signal-driven exit.
            if position is not None and self._is_exit_signal(position, signal.action):
                fill = price * (1 - slippage) if position["side"] == "LONG" else price * (1 + slippage)
                capital, trade = self._close_position(
                    position, fill, timestamp, capital, fee_rate, "Signal Exit"
                )
                trades.append(trade)
                position = None

            # 4. Entry.
            if position is None and signal.action in {"BUY", "SELL"}:
                position = self._open_position(
                    signal.action, price, timestamp, capital, fee_rate, slippage, signal
                )
                capital -= float(position["entry_fee"])

            # 5. Mark to market.
            equity = capital + self._unrealized(position, price)
            equity_values.append(equity)
            rolling_max = max(rolling_max, equity)
            drawdown_pct = ((rolling_max - equity) / rolling_max * 100) if rolling_max > 0 else 0.0

            equity_curve.append(
                EquityPoint(
                    timestamp=timestamp,
                    equity=round(equity, 2),
                    drawdown_pct=round(drawdown_pct, 2),
                )
            )

        # Close any position still open at the end of the data so the final
        # equity reflects a realizable number rather than a paper position.
        if position is not None:
            final_price = closes[-1]
            fill = (
                final_price * (1 - self.request.slippage)
                if position["side"] == "LONG"
                else final_price * (1 + self.request.slippage)
            )
            capital, trade = self._close_position(
                position, fill, str(timestamps[-1]), capital, fee_rate, "End of Data"
            )
            trades.append(trade)
            if equity_values:
                equity_values[-1] = capital
                equity_curve[-1] = EquityPoint(
                    timestamp=equity_curve[-1].timestamp,
                    equity=round(capital, 2),
                    drawdown_pct=equity_curve[-1].drawdown_pct,
                )

        equity_series = pd.Series(equity_values, dtype=float)
        metrics = PerformanceMetricsCalculator.calculate(
            initial_capital=self.request.initial_capital,
            trades=trades,
            equity_series=equity_series,
            timeframe=self.request.timeframe,
        )

        return BacktestResult(
            symbol=self.request.symbol,
            timeframe=self.request.timeframe,
            strategy_name=self.request.strategy_name,
            initial_capital=self.request.initial_capital,
            final_equity=round(
                float(equity_series.iloc[-1]) if not equity_series.empty else capital, 2
            ),
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
        )

    # ── Position mechanics ───────────────────────────────────────────

    @staticmethod
    def _is_exit_signal(position: dict[str, Any], action: str) -> bool:
        """Whether the signal closes the open position's direction."""
        return (position["side"] == "LONG" and action == "SELL") or (
            position["side"] == "SHORT" and action == "BUY"
        )

    @staticmethod
    def _check_exit_levels(
        position: dict[str, Any],
        high: float,
        low: float,
    ) -> tuple[float | None, str]:
        """Test this bar's range against the position's stop and target.

        When both levels fall inside a single bar we cannot know which was hit
        first from OHLC alone, so the stop is assumed to trigger. Assuming the
        target instead would inflate every backtest.
        """
        stop_loss = position.get("stop_loss")
        take_profit = position.get("take_profit")

        if position["side"] == "LONG":
            if stop_loss and low <= float(stop_loss):
                return float(stop_loss), "Stop Loss"
            if take_profit and high >= float(take_profit):
                return float(take_profit), "Take Profit"
        else:
            if stop_loss and high >= float(stop_loss):
                return float(stop_loss), "Stop Loss"
            if take_profit and low <= float(take_profit):
                return float(take_profit), "Take Profit"
        return None, ""

    @staticmethod
    def _open_position(
        action: str,
        price: float,
        timestamp: str,
        capital: float,
        fee_rate: float,
        slippage: float,
        signal: object,
    ) -> dict[str, Any]:
        """Size and open a new position, allocating 95% of free capital."""
        side = "LONG" if action == "BUY" else "SHORT"
        fill_price = price * (1 + slippage) if side == "LONG" else price * (1 - slippage)
        order_usd = capital * 0.95
        qty = order_usd / fill_price if fill_price > 0 else 0.0

        return {
            "side": side,
            "entry_price": fill_price,
            "qty": qty,
            "entry_time": timestamp,
            "entry_fee": order_usd * fee_rate,
            "stop_loss": getattr(signal, "stop_loss", None),
            "take_profit": getattr(signal, "take_profit", None),
        }

    @staticmethod
    def _close_position(
        position: dict[str, Any],
        exit_price: float,
        timestamp: str,
        capital: float,
        fee_rate: float,
        reason: str,
    ) -> tuple[float, dict[str, Any]]:
        """Realize a position and return the new capital plus the trade record."""
        qty = float(position["qty"])
        entry_price = float(position["entry_price"])
        direction = 1.0 if position["side"] == "LONG" else -1.0

        gross_pnl = (exit_price - entry_price) * qty * direction
        exit_fee = exit_price * qty * fee_rate
        net_pnl = gross_pnl - exit_fee
        total_fees = float(position["entry_fee"]) + exit_fee

        return capital + net_pnl, {
            "entry_time": position["entry_time"],
            "exit_time": timestamp,
            "side": position["side"],
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "qty": round(qty, 8),
            "pnl": round(net_pnl, 4),
            "fee": round(total_fees, 4),
            "reason": reason,
        }

    @staticmethod
    def _unrealized(position: dict[str, Any] | None, price: float) -> float:
        """Mark-to-market value of the open position, or zero when flat."""
        if position is None:
            return 0.0
        direction = 1.0 if position["side"] == "LONG" else -1.0
        return (price - float(position["entry_price"])) * float(position["qty"]) * direction

    def _empty_result(self) -> BacktestResult:
        """Return an empty backtest result for insufficient data."""
        return BacktestResult(
            symbol=self.request.symbol,
            timeframe=self.request.timeframe,
            strategy_name=self.request.strategy_name,
            initial_capital=self.request.initial_capital,
            final_equity=self.request.initial_capital,
            metrics=PerformanceMetricsCalculator.calculate(
                self.request.initial_capital, [], pd.Series(dtype=float), self.request.timeframe
            ),
            equity_curve=[],
            trades=[],
        )
