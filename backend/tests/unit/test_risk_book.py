"""
QuantX — Unit Tests for the fill-replay position book used by live risk checks.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.engines.risk.book import Fill, build_book

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
MIDNIGHT = NOW.replace(hour=0)


@pytest.mark.unit
class TestBuildBook:
    def test_average_cost_and_partial_exit(self) -> None:
        book = build_book(
            [
                Fill("BTCUSDT", "BUY", 1.0, 100.0, NOW - timedelta(hours=3)),
                Fill("BTCUSDT", "BUY", 1.0, 200.0, NOW - timedelta(hours=2)),
                Fill("BTCUSDT", "SELL", 0.5, 120.0, NOW - timedelta(hours=1)),
            ],
            day_start=MIDNIGHT,
        )
        held = book.holdings["BTCUSDT"]
        assert held.quantity == pytest.approx(1.5)
        assert held.avg_cost == pytest.approx(150.0)
        assert book.realized_since_day_start == pytest.approx(-15.0)
        assert book.last_loss_at["BTCUSDT"] == NOW - timedelta(hours=1)

    def test_only_today_counts_toward_daily_pnl_and_closed_positions_disappear(self) -> None:
        book = build_book(
            [
                Fill("ETHUSDT", "BUY", 2.0, 10.0, MIDNIGHT - timedelta(days=1)),
                Fill("ETHUSDT", "SELL", 1.0, 5.0, MIDNIGHT - timedelta(hours=1)),  # yesterday: -5
                Fill("ETHUSDT", "SELL", 1.0, 30.0, NOW),  # today: +20
            ],
            day_start=MIDNIGHT,
        )
        assert "ETHUSDT" not in book.holdings
        assert book.realized_since_day_start == pytest.approx(20.0)

    def test_selling_untracked_holdings_realises_nothing(self) -> None:
        book = build_book([Fill("SOLUSDT", "SELL", 3.0, 150.0, NOW)], day_start=MIDNIGHT)
        assert book.holdings == {}
        assert book.realized_since_day_start == 0.0
