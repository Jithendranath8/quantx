"""
QuantX — Alembic Environment Configuration.

Supports both synchronous (offline) and asynchronous (online) migration modes.
Uses the application's SQLAlchemy metadata for autogeneration.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.database import Base

# Import every model module so the full schema is registered on
# Base.metadata. Importing only the user models made `alembic revision
# --autogenerate` treat every other table as removed and emit drop_table for
# all of them.
from app.models.live_trading import LiveOrder  # noqa: F401
from app.models.market_data import Candle, FundingRate, OpenInterest  # noqa: F401
from app.models.master_models import (  # noqa: F401
    AIDecisionLog,
    DatasetFingerprint,
    EventLedger,
    ExperimentRecord,
    FundingAndOIRecord,
    LiquidationEvent,
    NewsArticle,
    OrderFlowSnapshot,
    RiskState,
    TradeJournal,
)
from app.models.paper_trading import (  # noqa: F401
    PaperAccount,
    PaperOrder,
    PaperPosition,
)
from app.models.user import AuditLog, RefreshToken, User  # noqa: F401

config = context.config
settings = get_settings()

# Override sqlalchemy.url with our computed URL
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
