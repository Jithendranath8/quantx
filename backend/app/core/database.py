"""
QuantX — Async Database Engine & Session Management.

Provides the async SQLAlchemy engine, session factory, and a base model
class for all ORM models. Uses asyncpg as the PostgreSQL driver.

The engine is created lazily rather than at import time. Engines and their
pooled asyncpg connections are bound to the event loop that created them, so a
module-level engine shared across several short-lived loops (the classic Celery
``asyncio.run()`` pattern) raises "Event loop is closed" on the second task.
Lazy creation lets each process build its engine inside the loop that will use
it, and ``dispose_engine`` tears it down cleanly.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)

from app.core.config import get_settings

# ── Naming convention for constraints (Alembic-friendly) ─────────────
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

# ── Lazily-created engine & session factory ──────────────────────────
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(url: str | None = None) -> AsyncEngine:
    """Build a new async engine using the configured pool settings.

    Args:
        url: Optional database URL override (used by tests).

    Returns:
        A fresh AsyncEngine. The caller owns its lifecycle.
    """
    settings = get_settings()
    return create_async_engine(
        url or settings.database_url,
        echo=settings.debug and not settings.is_production,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args={
            "command_timeout": settings.db_command_timeout_seconds,
            "server_settings": {"application_name": settings.app_name},
        },
    )


def get_engine() -> AsyncEngine:
    """Get the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the process-wide async session factory, creating it on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    """Dispose the engine and drop every pooled connection.

    Must be called before the owning event loop closes, otherwise asyncpg
    connections are left dangling against a dead loop.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Provides:
    - Standardized metadata with naming conventions
    - Common timestamp columns (created_at, updated_at)
    - Consistent __repr__ for debugging
    """

    metadata = metadata

    # DateTime(timezone=True) is required, not cosmetic. Without it SQLAlchemy
    # maps these to TIMESTAMP WITHOUT TIME ZONE while the Python defaults below
    # produce timezone-aware values, and asyncpg then refuses every INSERT with
    # "can't subtract offset-naive and offset-aware datetimes" -- which made
    # every table inheriting Base unwritable against PostgreSQL.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Generate a developer-friendly representation."""
        pk_cols = [col.name for col in self.__table__.primary_key.columns]  # type: ignore[attr-defined]  # SQLAlchemy typing gap
        pk_vals = ", ".join(f"{col}={getattr(self, col, '?')}" for col in pk_cols)
        return f"<{self.__class__.__name__}({pk_vals})>"


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields an async database session.

    The session is closed when the request completes. Commits must be
    performed explicitly in the service layer.

    Usage in a route:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
