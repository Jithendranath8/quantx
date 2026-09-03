"""
QuantX — Walk-Forward Testing Engine.

Rolling train/test splits that actually run the backtest engine on each window.

The in-sample and out-of-sample Sharpe ratios reported here are computed from
real simulated equity curves. Returning a formula like ``1.85 + i * 0.05``
produces a result that always looks healthy no matter what the strategy does,
which is the single most dangerous thing a research tool can do.
"""

import pandas as pd
from pydantic import BaseModel

from app.engines.backtest.engine import WARMUP_BARS, BacktestEngine
from app.schemas.backtest import BacktestRequest

MIN_ROWS_PER_WINDOW = WARMUP_BARS + 20
MIN_TOTAL_ROWS = 200


class WalkForwardWindow(BaseModel):
    """One train/test split and the performance measured on each side."""

    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_bars: int
    test_bars: int
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    in_sample_return_pct: float
    out_of_sample_return_pct: float
    out_of_sample_trades: int


class WalkForwardResult(BaseModel):
    """Aggregate walk-forward outcome across every window."""

    strategy_name: str
    symbol: str
    timeframe: str
    total_windows: int
    avg_in_sample_sharpe: float
    avg_out_of_sample_sharpe: float
    efficiency_ratio: float  # OOS Sharpe / IS Sharpe
    overfitting_warning: bool
    message: str
    windows: list[WalkForwardWindow]


class WalkForwardEngine:
    """Executes walk-forward evaluation over rolling historical windows."""

    @staticmethod
    def run_walk_forward(
        strategy_name: str,
        df_candles: pd.DataFrame,
        num_windows: int = 4,
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        initial_capital: float = 10_000.0,
    ) -> WalkForwardResult:
        """Run rolling train/test splits, backtesting each side independently.

        Args:
            strategy_name: Registered strategy to evaluate.
            df_candles: Chronological OHLCV frame.
            num_windows: Number of rolling splits.
            symbol: Symbol label passed through to the engine.
            timeframe: Bar size, used for correct Sharpe annualization.
            initial_capital: Starting capital for each window's simulation.
        """
        num_windows = max(1, min(num_windows, 20))

        if df_candles.empty or len(df_candles) < MIN_TOTAL_ROWS:
            return WalkForwardResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                total_windows=0,
                avg_in_sample_sharpe=0.0,
                avg_out_of_sample_sharpe=0.0,
                efficiency_ratio=0.0,
                overfitting_warning=False,
                message=(
                    f"Insufficient data: {len(df_candles)} bars available, "
                    f"{MIN_TOTAL_ROWS} required."
                ),
                windows=[],
            )

        chunk_size = len(df_candles) // (num_windows + 1)
        if chunk_size < MIN_ROWS_PER_WINDOW:
            return WalkForwardResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                total_windows=0,
                avg_in_sample_sharpe=0.0,
                avg_out_of_sample_sharpe=0.0,
                efficiency_ratio=0.0,
                overfitting_warning=False,
                message=(
                    f"{num_windows} windows would give {chunk_size} bars each; "
                    f"at least {MIN_ROWS_PER_WINDOW} are needed. Use fewer windows "
                    f"or more data."
                ),
                windows=[],
            )

        request = BacktestRequest(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            initial_capital=initial_capital,
        )
        engine = BacktestEngine(request)

        windows: list[WalkForwardWindow] = []
        for i in range(num_windows):
            train = df_candles.iloc[i * chunk_size : (i + 1) * chunk_size].reset_index(drop=True)
            test = df_candles.iloc[(i + 1) * chunk_size : (i + 2) * chunk_size].reset_index(drop=True)
            if train.empty or test.empty:
                break

            train_result = engine.run(train)
            test_result = engine.run(test)

            windows.append(
                WalkForwardWindow(
                    window_id=i + 1,
                    train_start=str(train.iloc[0]["timestamp"]),
                    train_end=str(train.iloc[-1]["timestamp"]),
                    test_start=str(test.iloc[0]["timestamp"]),
                    test_end=str(test.iloc[-1]["timestamp"]),
                    train_bars=len(train),
                    test_bars=len(test),
                    in_sample_sharpe=train_result.metrics.sharpe_ratio,
                    out_of_sample_sharpe=test_result.metrics.sharpe_ratio,
                    in_sample_return_pct=train_result.metrics.total_return_pct,
                    out_of_sample_return_pct=test_result.metrics.total_return_pct,
                    out_of_sample_trades=test_result.metrics.total_trades,
                )
            )

        if not windows:
            return WalkForwardResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                total_windows=0,
                avg_in_sample_sharpe=0.0,
                avg_out_of_sample_sharpe=0.0,
                efficiency_ratio=0.0,
                overfitting_warning=False,
                message="No usable windows could be constructed from the supplied data.",
                windows=[],
            )

        avg_is = sum(w.in_sample_sharpe for w in windows) / len(windows)
        avg_oos = sum(w.out_of_sample_sharpe for w in windows) / len(windows)
        # The efficiency ratio only means anything when the strategy was
        # profitable in training. Dividing two negative Sharpes yields a
        # flattering number for a strategy that lost money on both sides.
        efficiency = (avg_oos / avg_is) if avg_is > 0 else 0.0

        # Out-of-sample well below in-sample is the classic signature of a
        # strategy fitted to its training data.
        overfit = avg_is > 0 and efficiency < 0.5

        if avg_is <= 0:
            # Consistency is not good news when both sides lost money.
            message = (
                f"Strategy is unprofitable in-sample (Sharpe {avg_is:.2f}); "
                "there is no edge to generalize and the efficiency ratio is not "
                "meaningful here."
            )
        elif overfit:
            message = (
                "Out-of-sample Sharpe is less than half of in-sample; the strategy "
                "likely does not generalize."
            )
        elif avg_oos <= 0:
            message = (
                f"Positive in-sample (Sharpe {avg_is:.2f}) but non-positive "
                f"out-of-sample ({avg_oos:.2f}): the edge did not survive."
            )
        else:
            message = "Out-of-sample performance is broadly consistent with in-sample."

        return WalkForwardResult(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            total_windows=len(windows),
            avg_in_sample_sharpe=round(avg_is, 2),
            avg_out_of_sample_sharpe=round(avg_oos, 2),
            efficiency_ratio=round(efficiency, 2),
            overfitting_warning=overfit,
            message=message,
            windows=windows,
        )
