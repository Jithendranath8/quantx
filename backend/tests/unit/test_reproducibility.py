"""
QuantX — Unit Tests for dataset fingerprinting and experiment registration.

The previous fingerprint hashed only ``symbol_timeframe_rowcount``, so two
completely different price series with the same row count produced an identical
hash — an assertion of sameness that was never actually checked.
"""

import math

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.experiment_service import ExperimentRegistryService, current_git_commit


def frame(n: int = 100, offset: float = 0.0) -> pd.DataFrame:
    """A deterministic OHLCV frame."""
    closes = [50_000 + i * 10 + offset + 500 * math.sin(i / 7) for i in range(n)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"),
            "open": [c - 5 for c in closes],
            "high": [c + 50 for c in closes],
            "low": [c - 50 for c in closes],
            "close": closes,
            "volume": [100.0] * n,
        }
    )


@pytest.mark.unit
class TestFingerprint:
    """Content-addressed dataset identity."""

    def test_identical_data_hashes_identically(self) -> None:
        """The same prices always produce the same fingerprint."""
        assert ExperimentRegistryService.fingerprint_dataframe(
            frame()
        ) == ExperimentRegistryService.fingerprint_dataframe(frame())

    def test_different_prices_hash_differently(self) -> None:
        """Same row count, different values, different hash.

        This is the case the old row-count fingerprint could not distinguish.
        """
        a = ExperimentRegistryService.fingerprint_dataframe(frame(100, offset=0))
        b = ExperimentRegistryService.fingerprint_dataframe(frame(100, offset=1))
        assert a != b

    def test_different_lengths_hash_differently(self) -> None:
        """More data is a different dataset."""
        a = ExperimentRegistryService.fingerprint_dataframe(frame(100))
        b = ExperimentRegistryService.fingerprint_dataframe(frame(150))
        assert a != b

    def test_empty_frame_is_stable(self) -> None:
        """An empty dataset hashes without raising."""
        digest = ExperimentRegistryService.fingerprint_dataframe(pd.DataFrame())
        assert len(digest) == 64

    @pytest.mark.asyncio
    async def test_fingerprint_is_recorded_with_provenance(
        self, db_session: AsyncSession
    ) -> None:
        """Recording stores the row count and the covered time range."""
        service = ExperimentRegistryService(db_session)
        digest = await service.record_fingerprint(frame(120), "BTCUSDT", "1h")
        await db_session.commit()

        stored = await service.get_fingerprint(digest)
        assert stored is not None
        assert stored.row_count == 120
        assert stored.symbol == "BTCUSDT"
        assert stored.start_timestamp < stored.end_timestamp

    @pytest.mark.asyncio
    async def test_recording_the_same_dataset_twice_is_a_noop(
        self, db_session: AsyncSession
    ) -> None:
        """A dataset legitimately recurs across runs; that is not an error."""
        service = ExperimentRegistryService(db_session)
        first = await service.record_fingerprint(frame(), "BTCUSDT", "1h")
        second = await service.record_fingerprint(frame(), "BTCUSDT", "1h")
        await db_session.commit()
        assert first == second


@pytest.mark.unit
class TestExperimentRegistry:
    """Recording a research run with enough context to reproduce it."""

    @pytest.mark.asyncio
    async def test_registration_captures_dataset_and_code(
        self, db_session: AsyncSession
    ) -> None:
        """An experiment records its dataset hash, row count and commit."""
        service = ExperimentRegistryService(db_session)
        df = frame(200)

        experiment = await service.register_from_dataset(
            strategy_name="ema_crossover",
            df=df,
            symbol="BTCUSDT",
            timeframe="1h",
            parameters={"fast_col": "ema_9", "slow_col": "ema_21"},
            metrics={"sharpe_ratio": 1.4},
            fees=0.00075,
            slippage=0.0005,
        )

        assert experiment.experiment_id.startswith("EXP-")
        assert experiment.dataset_row_count == 200
        assert experiment.dataset_version == ExperimentRegistryService.fingerprint_dataframe(df)
        assert experiment.parameters["fast_col"] == "ema_9"
        # git_commit is None outside a checkout rather than an invented value.
        assert experiment.git_commit == current_git_commit()

        fingerprint = await service.get_fingerprint(experiment.dataset_version)
        assert fingerprint is not None
        assert fingerprint.row_count == 200

    @pytest.mark.asyncio
    async def test_two_runs_on_the_same_data_share_a_dataset_version(
        self, db_session: AsyncSession
    ) -> None:
        """Reproducibility: same data means the same dataset_version."""
        service = ExperimentRegistryService(db_session)
        common = {
            "df": frame(150),
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "metrics": {},
            "fees": 0.001,
            "slippage": 0.001,
        }
        a = await service.register_from_dataset(
            strategy_name="ema_crossover", parameters={"run": 1}, **common
        )
        b = await service.register_from_dataset(
            strategy_name="rsi_mean_reversion", parameters={"run": 2}, **common
        )

        assert a.dataset_version == b.dataset_version
        assert a.experiment_id != b.experiment_id

    @pytest.mark.asyncio
    async def test_listing_is_bounded_and_newest_first(self, db_session: AsyncSession) -> None:
        """The registry listing is paginated."""
        service = ExperimentRegistryService(db_session)
        for i in range(5):
            await service.register_from_dataset(
                strategy_name="ema_crossover",
                df=frame(60 + i),
                symbol="BTCUSDT",
                timeframe="1h",
                parameters={"i": i},
                metrics={},
                fees=0.0,
                slippage=0.0,
            )

        assert len(await service.list_experiments(limit=3)) == 3
        assert len(await service.list_experiments(limit=100)) == 5
