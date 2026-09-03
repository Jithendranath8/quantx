"""
QuantX — Unit Tests for market data coverage.

The UI advertises eight symbols and six timeframes. Only whatever had been
manually downloaded once had data, so 44 of 48 combinations rendered as an
empty table indistinguishable from a broken query.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.market_data import Candle
from app.services.market_coverage_service import (
    TIMEFRAME_LOOKBACK_DAYS,
    MarketCoverageService,
)


def candle(symbol: str, timeframe: str, when: datetime) -> Candle:
    """A stored candle at a specific time."""
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=when,
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=10.0,
        close_time=when + timedelta(minutes=1),
        quote_volume=1000.0,
        trades_count=5,
        is_closed=True,
    )


class RecordingDownloader:
    """Captures which pairs a sync asked for."""

    def __init__(self, fail_for: set[tuple[str, str]] | None = None) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self._fail_for = fail_for or set()

    async def download_history(self, symbol: str, timeframe: str, days: int = 30) -> int:
        if (symbol, timeframe) in self._fail_for:
            raise RuntimeError(f"upstream refused {symbol} {timeframe}")
        self.calls.append((symbol, timeframe, days))
        return 100


@pytest.fixture
def limited_market(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the configured universe so assertions stay readable."""
    settings = get_settings()
    monkeypatch.setattr(settings, "market_symbols", "BTCUSDT,ETHUSDT")
    monkeypatch.setattr(settings, "market_timeframes", "1h,1d")


@pytest.mark.unit
class TestCoverageReporting:
    """Coverage must name what is missing, not just what exists."""

    @pytest.mark.asyncio
    async def test_missing_pairs_are_reported_not_omitted(
        self, db_session: AsyncSession, limited_market: None
    ) -> None:
        """A pair with no data appears with a zero count.

        Omitting it would make "nothing ingested" indistinguishable from
        "not covered".
        """
        rows = await MarketCoverageService(db_session).get_coverage()
        assert len(rows) == 4  # 2 symbols x 2 timeframes
        assert all(r.candle_count == 0 for r in rows)
        assert all(not r.has_data for r in rows)

    @pytest.mark.asyncio
    async def test_stored_data_is_counted(
        self, db_session: AsyncSession, limited_market: None
    ) -> None:
        """Counts and time ranges come from the table."""
        now = datetime.now(UTC)
        db_session.add_all(
            [candle("BTCUSDT", "1h", now - timedelta(hours=i)) for i in range(5)]
        )
        await db_session.commit()

        rows = {(r.symbol, r.timeframe): r for r in
                await MarketCoverageService(db_session).get_coverage()}
        btc = rows[("BTCUSDT", "1h")]
        assert btc.candle_count == 5
        assert btc.has_data is True
        assert btc.oldest < btc.newest

    @pytest.mark.asyncio
    async def test_fresh_data_is_not_stale(
        self, db_session: AsyncSession, limited_market: None
    ) -> None:
        """A series updated this minute is current."""
        db_session.add(candle("BTCUSDT", "1h", datetime.now(UTC)))
        await db_session.commit()

        rows = {(r.symbol, r.timeframe): r for r in
                await MarketCoverageService(db_session).get_coverage()}
        assert rows[("BTCUSDT", "1h")].is_stale is False

    @pytest.mark.asyncio
    async def test_old_data_is_flagged_stale(
        self, db_session: AsyncSession, limited_market: None
    ) -> None:
        """A series many bars behind is flagged rather than silently served."""
        db_session.add(candle("BTCUSDT", "1h", datetime.now(UTC) - timedelta(days=2)))
        await db_session.commit()

        rows = {(r.symbol, r.timeframe): r for r in
                await MarketCoverageService(db_session).get_coverage()}
        assert rows[("BTCUSDT", "1h")].is_stale is True

    @pytest.mark.asyncio
    async def test_summary_counts_completeness(
        self, db_session: AsyncSession, limited_market: None
    ) -> None:
        """The summary is a one-glance completeness view."""
        db_session.add(candle("BTCUSDT", "1h", datetime.now(UTC)))
        await db_session.commit()

        summary = await MarketCoverageService(db_session).summary()
        assert summary["pairs_total"] == 4
        assert summary["pairs_with_data"] == 1
        assert summary["pairs_missing"] == 3
        assert summary["total_candles"] == 1


@pytest.mark.unit
class TestLookbackPolicy:
    """History depth is per timeframe, not one blanket figure."""

    def test_fine_timeframes_get_shallow_history(self) -> None:
        """A year of 1m candles is half a million rows nobody charts."""
        assert MarketCoverageService.lookback_days("1m") < MarketCoverageService.lookback_days("1h")
        assert MarketCoverageService.lookback_days("1h") < MarketCoverageService.lookback_days("1d")

    def test_every_advertised_timeframe_has_a_policy(self) -> None:
        """Each configured timeframe has a deliberate lookback."""
        for tf in get_settings().market_timeframe_list:
            assert tf in TIMEFRAME_LOOKBACK_DAYS, f"{tf} has no lookback policy"

    def test_unknown_timeframe_falls_back(self) -> None:
        """An unconfigured timeframe still gets a sane default."""
        assert MarketCoverageService.lookback_days("99y") > 0


@pytest.mark.unit
class TestSync:
    """Backfilling the gaps."""

    @pytest.mark.asyncio
    async def test_sync_covers_every_missing_pair(
        self, db_session: AsyncSession, limited_market: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cold start fetches all of them."""
        downloader = RecordingDownloader()
        monkeypatch.setattr(
            "app.services.market_coverage_service.HistoricalDownloaderService",
            lambda *a, **kw: downloader,
        )

        result = await MarketCoverageService(db_session).sync()
        assert result["pairs_synced"] == 4
        assert {(s, t) for s, t, _ in downloader.calls} == {
            ("BTCUSDT", "1h"), ("BTCUSDT", "1d"), ("ETHUSDT", "1h"), ("ETHUSDT", "1d"),
        }

    @pytest.mark.asyncio
    async def test_cold_start_uses_the_full_lookback(
        self, db_session: AsyncSession, limited_market: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty pair is backfilled deeply; a current one is only topped up."""
        db_session.add(candle("BTCUSDT", "1h", datetime.now(UTC) - timedelta(days=5)))
        await db_session.commit()

        downloader = RecordingDownloader()
        monkeypatch.setattr(
            "app.services.market_coverage_service.HistoricalDownloaderService",
            lambda *a, **kw: downloader,
        )
        await MarketCoverageService(db_session).sync()

        by_pair = {(s, t): d for s, t, d in downloader.calls}
        # Has (stale) data -> short top-up.
        assert by_pair[("BTCUSDT", "1h")] == 2
        # No data at all -> full lookback.
        assert by_pair[("ETHUSDT", "1d")] == TIMEFRAME_LOOKBACK_DAYS["1d"]

    @pytest.mark.asyncio
    async def test_current_pairs_are_skipped(
        self, db_session: AsyncSession, limited_market: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Steady state does no unnecessary work."""
        now = datetime.now(UTC)
        for sym in ("BTCUSDT", "ETHUSDT"):
            for tf in ("1h", "1d"):
                db_session.add(candle(sym, tf, now))
        await db_session.commit()

        downloader = RecordingDownloader()
        monkeypatch.setattr(
            "app.services.market_coverage_service.HistoricalDownloaderService",
            lambda *a, **kw: downloader,
        )
        result = await MarketCoverageService(db_session).sync()
        assert result["pairs_synced"] == 0
        assert downloader.calls == []

    @pytest.mark.asyncio
    async def test_one_failing_pair_does_not_abandon_the_rest(
        self, db_session: AsyncSession, limited_market: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A delisted or unavailable symbol must not stop the other 47."""
        downloader = RecordingDownloader(fail_for={("ETHUSDT", "1h")})
        monkeypatch.setattr(
            "app.services.market_coverage_service.HistoricalDownloaderService",
            lambda *a, **kw: downloader,
        )

        result = await MarketCoverageService(db_session).sync()
        assert result["pairs_failed"] == 1
        assert result["candles_ingested"] == 300  # the other three still ran
        assert any("error" in d for d in result["details"])

    @pytest.mark.asyncio
    async def test_full_sync_refetches_deeply_not_just_the_tail(
        self, db_session: AsyncSession, limited_market: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """full=True must fetch the whole lookback, not a 2-day top-up.

        Re-checking every pair and still requesting two days is not a resync;
        it silently leaves shallow history in place.
        """
        now = datetime.now(UTC)
        for sym in ("BTCUSDT", "ETHUSDT"):
            for tf in ("1h", "1d"):
                db_session.add(candle(sym, tf, now))
        await db_session.commit()

        downloader = RecordingDownloader()
        monkeypatch.setattr(
            "app.services.market_coverage_service.HistoricalDownloaderService",
            lambda *a, **kw: downloader,
        )
        result = await MarketCoverageService(db_session).sync(only_missing_or_stale=False)

        assert result["pairs_synced"] == 4
        by_pair = {(s, t): d for s, t, d in downloader.calls}
        assert by_pair[("BTCUSDT", "1h")] == TIMEFRAME_LOOKBACK_DAYS["1h"]
        assert by_pair[("ETHUSDT", "1d")] == TIMEFRAME_LOOKBACK_DAYS["1d"]
        assert all(mode["mode"] == "backfill" for mode in result["details"])


@pytest.mark.unit
class TestConfigDrivesEverything:
    """One config governs the API list, the stream and ingestion."""

    def test_stream_follows_market_symbols_when_blank(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A blank stream list means "cover everything we store".

        Previously the stream had its own hardcoded pair of symbols, so live
        prices existed for two markets while the UI offered eight.
        """
        settings = get_settings()
        monkeypatch.setattr(settings, "market_symbols", "BTCUSDT,SOLUSDT,DOGEUSDT")
        monkeypatch.setattr(settings, "market_stream_symbols", "")
        assert settings.market_stream_symbol_list == ["BTCUSDT", "SOLUSDT", "DOGEUSDT"]

    def test_stream_can_still_be_narrowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit list wins, for deployments that stream a subset."""
        settings = get_settings()
        monkeypatch.setattr(settings, "market_symbols", "BTCUSDT,SOLUSDT,DOGEUSDT")
        monkeypatch.setattr(settings, "market_stream_symbols", "BTCUSDT")
        assert settings.market_stream_symbol_list == ["BTCUSDT"]


@pytest.mark.unit
class TestStalenessThreshold:
    """Staleness must respect how often the sync actually runs.

    A 1m series topped up every ten minutes is legitimately several bars
    behind between runs. Flagging that as stale is noise, and noise trains
    people to ignore the flag that matters.
    """

    @pytest.mark.asyncio
    async def test_fast_timeframe_is_not_stale_within_the_sync_window(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1m data a few minutes old is fine when the sync runs every 10."""
        settings = get_settings()
        monkeypatch.setattr(settings, "market_symbols", "BTCUSDT")
        monkeypatch.setattr(settings, "market_timeframes", "1m")

        # Five minutes behind: three bars stale by the naive rule, but well
        # inside a ten-minute sync cadence.
        db_session.add(candle("BTCUSDT", "1m", datetime.now(UTC) - timedelta(minutes=5)))
        await db_session.commit()

        rows = await MarketCoverageService(db_session).get_coverage()
        assert rows[0].is_stale is False

    @pytest.mark.asyncio
    async def test_fast_timeframe_is_stale_when_genuinely_behind(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Data older than the sync could explain is still flagged."""
        settings = get_settings()
        monkeypatch.setattr(settings, "market_symbols", "BTCUSDT")
        monkeypatch.setattr(settings, "market_timeframes", "1m")

        db_session.add(candle("BTCUSDT", "1m", datetime.now(UTC) - timedelta(hours=3)))
        await db_session.commit()

        rows = await MarketCoverageService(db_session).get_coverage()
        assert rows[0].is_stale is True

    @pytest.mark.asyncio
    async def test_slow_timeframe_still_uses_the_bar_rule(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """For daily candles the bar multiple dominates, not the cadence."""
        settings = get_settings()
        monkeypatch.setattr(settings, "market_symbols", "BTCUSDT")
        monkeypatch.setattr(settings, "market_timeframes", "1d")

        db_session.add(candle("BTCUSDT", "1d", datetime.now(UTC) - timedelta(days=5)))
        await db_session.commit()

        rows = await MarketCoverageService(db_session).get_coverage()
        assert rows[0].is_stale is True

    def test_threshold_is_derived_from_the_beat_schedule(self) -> None:
        """The cadence is read from the schedule, not hardcoded.

        A hardcoded value would silently drift out of step with the job that
        is supposed to keep the data fresh.
        """
        from app.core.celery_app import celery_app
        from app.services.market_coverage_service import _scheduled_sync_interval_minutes

        entry = celery_app.conf.beat_schedule["sync-market-data-every-10-min"]
        assert _scheduled_sync_interval_minutes() == entry["schedule"] / 60.0
