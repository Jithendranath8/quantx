"""
QuantX - Unit tests for order-book microstructure analytics.
"""

import pytest

from app.engines.microstructure.analytics import analyze_order_book

BIDS = [[100.0, 2.0], [99.0, 3.0], [98.0, 5.0]]
ASKS = [[101.0, 1.0], [102.0, 4.0], [103.0, 2.0]]


@pytest.mark.unit
class TestMicrostructure:
    def test_basic_metrics(self) -> None:
        m = analyze_order_book(BIDS, ASKS, levels=10, depth_bps=1000.0)
        assert m is not None
        assert m.best_bid == 100.0
        assert m.best_ask == 101.0
        assert m.mid == pytest.approx(100.5)
        assert m.spread == pytest.approx(1.0)
        assert m.spread_bps == pytest.approx(1.0 / 100.5 * 10_000.0)
        # microprice = (bid*askQty + ask*bidQty)/(bidQty+askQty) = (100*1 + 101*2)/3
        assert m.microprice == pytest.approx(302.0 / 3.0)
        # imbalance = (10 - 7) / 17 over all three levels
        assert m.imbalance == pytest.approx(3.0 / 17.0)
        assert m.bid_depth == pytest.approx(10.0)
        assert m.ask_depth == pytest.approx(7.0)
        assert m.bid_levels == 3
        assert m.ask_levels == 3

    def test_microprice_leans_toward_the_heavier_side(self) -> None:
        # A heavy bid queue pushes fair value up toward the ask.
        m = analyze_order_book([[100.0, 10.0]], [[101.0, 1.0]])
        assert m is not None
        assert m.microprice > m.mid

    def test_imbalance_sign_follows_the_book(self) -> None:
        more_bids = analyze_order_book([[100.0, 9.0]], [[101.0, 1.0]])
        more_asks = analyze_order_book([[100.0, 1.0]], [[101.0, 9.0]])
        assert more_bids is not None and more_bids.imbalance > 0
        assert more_asks is not None and more_asks.imbalance < 0

    def test_depth_window_counts_only_levels_within_the_band(self) -> None:
        # 50 bps of a ~100.5 mid is ~0.50, so only the top level each side counts.
        m = analyze_order_book(BIDS, ASKS, levels=10, depth_bps=50.0)
        assert m is not None
        assert m.bid_depth == pytest.approx(2.0)
        assert m.ask_depth == pytest.approx(1.0)

    def test_empty_book_returns_none(self) -> None:
        assert analyze_order_book([], ASKS) is None
        assert analyze_order_book(BIDS, []) is None
