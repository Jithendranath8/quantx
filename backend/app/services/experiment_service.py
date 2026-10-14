"""
QuantX — Experiment Registry & Dataset Versioning.

Records research runs so a result can be reproduced: which strategy, which
parameters, which code, and exactly which data.

The dataset fingerprint is a SHA-256 over the actual OHLCV values. The previous
implementation hashed only ``symbol_timeframe_rowcount``, so two completely
different price series with the same number of rows produced an identical
"fingerprint" — which is worse than having none, because it asserts sameness
that was never checked.
"""

import hashlib
import subprocess
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.master_models import DatasetFingerprint, ExperimentRecord

logger = get_logger(__name__)

FINGERPRINT_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


@lru_cache(maxsize=1)
def current_git_commit() -> str | None:
    """Resolve the HEAD commit so a result can be tied to the code that made it.

    Returns None outside a git checkout (a container built from a tarball, for
    example) rather than inventing a value.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


class ExperimentRegistryService:
    """Tracks research experiments and the datasets they ran against."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Dataset fingerprinting ───────────────────────────────────────

    @staticmethod
    def fingerprint_dataframe(df: pd.DataFrame) -> str:
        """SHA-256 over the candle values themselves.

        Two runs share a fingerprint only when they genuinely saw the same
        prices, in the same order.
        """
        if df.empty:
            return hashlib.sha256(b"empty").hexdigest()

        columns = [c for c in FINGERPRINT_COLUMNS if c in df.columns]
        subset = df[columns].copy()
        if "timestamp" in subset.columns:
            subset["timestamp"] = subset["timestamp"].astype(str)

        digest = hashlib.sha256()
        # to_csv is deterministic for a fixed column order and float repr.
        digest.update(subset.to_csv(index=False).encode("utf-8"))
        return digest.hexdigest()

    async def record_fingerprint(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> str:
        """Fingerprint a dataset and store its provenance. Returns the hash."""
        dataset_hash = self.fingerprint_dataframe(df)
        if df.empty:
            return dataset_hash

        timestamps = pd.to_datetime(df["timestamp"], utc=True)
        stmt = insert(DatasetFingerprint).values(
            dataset_hash=dataset_hash,
            symbol=symbol.upper(),
            timeframe=timeframe,
            row_count=len(df),
            start_timestamp=timestamps.min().to_pydatetime(),
            end_timestamp=timestamps.max().to_pydatetime(),
        )
        # The same dataset legitimately recurs across runs; recording it again
        # is a no-op rather than an error.
        await self._session.execute(
            stmt.on_conflict_do_nothing(index_elements=["dataset_hash"])
        )
        await self._session.flush()
        return dataset_hash

    async def get_fingerprint(self, dataset_hash: str) -> DatasetFingerprint | None:
        """Look up a recorded dataset by its hash."""
        stmt = select(DatasetFingerprint).where(DatasetFingerprint.dataset_hash == dataset_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ── Experiment registry ──────────────────────────────────────────

    async def register_experiment(
        self,
        strategy_name: str,
        parameters: dict[str, Any],
        dataset_version: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        fees: float,
        slippage: float,
        metrics: dict[str, Any],
        strategy_version: str = "v1.0",
        ai_model: str | None = None,
        dataset_row_count: int | None = None,
        commit: bool = True,
    ) -> ExperimentRecord:
        """Record a research experiment with full provenance."""
        experiment = ExperimentRecord(
            experiment_id=f"EXP-{uuid.uuid4().hex[:12].upper()}",
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            parameters=parameters,
            dataset_version=dataset_version,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            fees=fees,
            slippage=slippage,
            metrics=metrics,
            ai_model=ai_model,
            git_commit=current_git_commit(),
            dataset_row_count=dataset_row_count,
        )
        self._session.add(experiment)
        await self._session.flush()
        if commit:
            await self._session.commit()
            await self._session.refresh(experiment)
        return experiment

    async def register_from_dataset(
        self,
        strategy_name: str,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        parameters: dict[str, Any],
        metrics: dict[str, Any],
        fees: float,
        slippage: float,
        ai_model: str | None = None,
    ) -> ExperimentRecord:
        """Fingerprint the dataset and register the experiment against it."""
        dataset_hash = await self.record_fingerprint(df, symbol, timeframe)
        timestamps = pd.to_datetime(df["timestamp"], utc=True) if not df.empty else None

        experiment = await self.register_experiment(
            strategy_name=strategy_name,
            parameters=parameters,
            dataset_version=dataset_hash,
            symbol=symbol,
            timeframe=timeframe,
            start_date=str(timestamps.min()) if timestamps is not None else "",
            end_date=str(timestamps.max()) if timestamps is not None else "",
            fees=fees,
            slippage=slippage,
            metrics=metrics,
            ai_model=ai_model,
            dataset_row_count=len(df),
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(experiment)
        logger.info(
            "experiment_registered",
            experiment_id=experiment.experiment_id,
            strategy=strategy_name,
            dataset_hash=dataset_hash[:12],
            rows=len(df),
        )
        return experiment

    async def list_experiments(self, limit: int = 100, offset: int = 0) -> list[ExperimentRecord]:
        """Fetch registered experiments, newest first, always bounded."""
        stmt = (
            select(ExperimentRecord)
            .order_by(ExperimentRecord.created_at.desc())
            .offset(max(0, offset))
            .limit(min(max(1, limit), 500))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        """Look up a single experiment by its public id."""
        stmt = select(ExperimentRecord).where(ExperimentRecord.experiment_id == experiment_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
