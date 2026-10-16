"""
QuantX — Unit tests for the Avellaneda-Stoikov market-making engine.

Covers the pure quoting model (skew + spread behaviour) and the simulation
(fills, inventory cap, and the P&L decomposition identity).
"""

import numpy as np
import pandas as pd
import pytest

from app.engines.market_making.engine import MarketMakingEngine
from app.engines.market_making.model import avellaneda_stoikov_quote
from app.schemas.market_making import MarketMakingRequest


@pytest.mark.unit
class TestQuotingModel:
    """Avellaneda-Stoikov reservation price and spread."""

    def test_flat_inventory_quotes_are_symmetric_around_mid(self) -> None:
        q = avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=0.3, k=1.5)
        assert q.reservation == pytest.approx(100.0)
        assert q.bid == pytest.approx(100.0 - q.half_spread)
        assert q.ask == pytest.approx(100.0 + q.half_spread)

    def test_long_inventory_skews_quotes_down(self) -> None:
        """Holding a long position lowers the reservation price (quote to sell)."""
        flat = avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=0.3, k=1.5)
        long = avellaneda_stoikov_quote(100.0, 5.0, 1.0, gamma=0.3, k=1.5)
        assert long.reservation < flat.reservation
        # The whole quote band shifts down, encouraging sells over buys.
        assert long.ask < flat.ask
        assert long.bid < flat.bid

    def test_short_inventory_skews_quotes_up(self) -> None:
        short = avellaneda_stoikov_quote(100.0, -5.0, 1.0, gamma=0.3, k=1.5)
        assert short.reservation > 100.0

    def test_higher_risk_aversion_widens_the_spread(self) -> None:
        low = avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=0.1, k=1.5)
        high = avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=1.0, k=1.5)
        assert high.half_spread > low.half_spread

    def test_deeper_liquidity_tightens_the_spread(self) -> None:
        thin = avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=0.3, k=0.5)
        deep = avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=0.3, k=5.0)
        assert deep.half_spread < thin.half_spread

    @pytest.mark.parametrize(("gamma", "k"), [(0.0, 1.5), (-1.0, 1.5), (0.3, 0.0)])
    def test_non_positive_parameters_are_rejected(self, gamma: float, k: float) -> None:
        with pytest.raises(ValueError, match="positive"):
            avellaneda_stoikov_quote(100.0, 0.0, 1.0, gamma=gamma, k=k)


def _oscillating(bars: int = 80, mid: float = 100.0, amp: float = 2.0, wick: float = 3.0) -> pd.DataFrame:
    """A mean-reverting price with wicks wide enough to fill both quotes."""
    t = np.arange(bars)
    close = mid + amp * np.sin(t / 3.0)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=bars, freq="1min"),
            "open": close,
            "high": close + wick,
            "low": close - wick,
            "close": close,
            "volume": np.full(bars, 10.0),
        }
    )


@pytest.mark.unit
class TestMarketMakingEngine:
    """Simulation mechanics: fills, inventory control, and P&L attribution."""

    def test_insufficient_data_returns_empty_result(self) -> None:
        req = MarketMakingRequest(symbol="BTCUSDT", timeframe="1m", vol_window=30)
        result = MarketMakingEngine(req).run(_oscillating(bars=10))
        assert result.metrics.num_fills == 0
        assert result.series == []

    def test_oscillating_market_captures_spread_on_both_sides(self) -> None:
        req = MarketMakingRequest(
            symbol="BTCUSDT", timeframe="1m", gamma=0.3, k=1.5,
            order_size=1.0, max_inventory=5.0, vol_window=5,
        )
        result = MarketMakingEngine(req).run(_oscillating())
        m = result.metrics
        assert m.num_buys > 0
        assert m.num_sells > 0
        assert m.spread_pnl > 0  # making edge is captured vs the mid
        assert 0.0 <= m.fill_ratio <= 1.0
        assert result.series  # a time series was produced

    def test_inventory_never_exceeds_the_cap(self) -> None:
        # A steady down-trend keeps hitting the bid; inventory must stop at cap.
        bars = 80
        close = np.linspace(100.0, 80.0, bars)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=bars, freq="1min"),
                "open": close, "high": close + 0.5, "low": close - 0.5,
                "close": close, "volume": np.full(bars, 10.0),
            }
        )
        req = MarketMakingRequest(
            symbol="BTCUSDT", timeframe="1m", order_size=1.0, max_inventory=2.0, vol_window=5,
        )
        result = MarketMakingEngine(req).run(df)
        assert result.metrics.max_inventory <= 2.0 + 1e-9
        assert abs(result.metrics.final_inventory) <= 2.0 + 1e-9

    def test_pnl_decomposition_identity_holds(self) -> None:
        req = MarketMakingRequest(
            symbol="BTCUSDT", timeframe="1m", order_size=1.0, max_inventory=5.0,
            fee_rate=0.0002, vol_window=5,
        )
        m = MarketMakingEngine(req).run(_oscillating()).metrics
        # total P&L = spread capture + inventory P&L - fees, by construction.
        assert m.total_pnl == pytest.approx(m.spread_pnl + m.inventory_pnl - m.fees_paid, abs=1e-4)
        assert m.fees_paid > 0  # fees were charged on fills
