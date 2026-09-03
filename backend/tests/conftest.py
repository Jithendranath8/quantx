"""
QuantX — Test Configuration & Fixtures.

Shared fixtures for unit and integration tests: an async database session, an
HTTP test client, and user factories.

Schema handling
---------------
Tables are created once for the whole session and each test runs inside a
transaction that is rolled back afterwards. The previous fixture ran
``create_all`` + ``drop_all`` per test function, rebuilding and tearing down
the entire schema roughly 140 times per run.

Because that create/drop is session-scoped and destructive, only ONE pytest
session may run against a given test database at a time. Two concurrent runs
will tear down each other's schema and produce a flood of unrelated failures.
Set TEST_DATABASE_URL to give a parallel run its own database.
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set before app.core.config is imported so the app never points at a real DB.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-that-is-long-enough-123456")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-1234567890")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("MARKET_STREAM_ENABLED", "false")
os.environ.setdefault("PROMETHEUS_ENABLED", "false")

from datetime import UTC

from app.core.config import get_settings
from app.core.database import Base, get_async_session
from app.core.security import create_access_token, hash_password
from app.main import app

# Import every model module so create_all builds the complete schema.
from app.models import live_trading, market_data, master_models, paper_trading  # noqa: F401
from app.models.user import User

settings = get_settings()

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    settings.database_url.rsplit("/", 1)[0] + "/quantx_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_size=5, max_overflow=5)
test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ── Schema lifecycle ─────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema() -> AsyncGenerator[None]:
    """Build the schema once per session and drop it at the end."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Provide a session whose writes are rolled back after the test.

    The session joins an outer transaction on a dedicated connection, so even
    code that calls ``session.commit()`` is undone when the test finishes.
    """
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Async HTTP client whose DB dependency uses the test session."""

    async def _override_get_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = _override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Data factories ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create an active, non-privileged user."""
    user = User(
        id=uuid.uuid4(),
        email="testuser@quantx.io",
        username="testuser",
        hashed_password=hash_password("TestP@ss123"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_user(db_session: AsyncSession) -> User:
    """A second user, for cross-tenant isolation tests."""
    user = User(
        id=uuid.uuid4(),
        email="other@quantx.io",
        username="otheruser",
        hashed_password=hash_password("OtherP@ss123"),
        full_name="Other User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def superuser(db_session: AsyncSession) -> User:
    """Create an active superuser."""
    user = User(
        id=uuid.uuid4(),
        email="admin@quantx.io",
        username="admin",
        hashed_password=hash_password("AdminP@ss123"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Bearer headers for the test user."""
    return {"Authorization": f"Bearer {create_access_token(subject=str(test_user.id))}"}


@pytest.fixture
def second_user_headers(second_user: User) -> dict[str, str]:
    """Bearer headers for the second user."""
    return {"Authorization": f"Bearer {create_access_token(subject=str(second_user.id))}"}


@pytest.fixture
def admin_headers(superuser: User) -> dict[str, str]:
    """Bearer headers for the superuser."""
    return {"Authorization": f"Bearer {create_access_token(subject=str(superuser.id))}"}


# ── Market data fixtures ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_candles(db_session: AsyncSession) -> int:
    """Insert a deterministic trending candle series for BTCUSDT 1h.

    Research and backtest endpoints operate on stored candles, so they need
    real rows rather than a synthetic frame built inside the route.
    """
    import math
    from datetime import datetime, timedelta

    from app.models.market_data import Candle

    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(400):
        # Trend plus a cycle, so strategies actually produce crossings.
        close = 50_000 + i * 25 + 900 * math.sin(i / 9)
        rows.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1h",
                timestamp=start + timedelta(hours=i),
                open=close - 15,
                high=close + 60,
                low=close - 60,
                close=close,
                volume=100 + (i % 20),
                close_time=start + timedelta(hours=i, minutes=59),
                quote_volume=close * 100,
                trades_count=500 + i,
                is_closed=True,
            )
        )
    db_session.add_all(rows)
    await db_session.commit()
    return len(rows)


class FakeBinanceClient:
    """Offline stand-in for the exchange connector used by API tests.

    ``price`` is mutable so a test can move the market and observe a resting
    order trigger.
    """

    testnet = True

    def __init__(self, price: float = 50_000.0) -> None:
        self.price = price

    async def get_price(self, symbol: str) -> float:
        return self.price

    async def get_ticker_24h(self, symbol: str | None = None) -> dict:
        return {
            "symbol": (symbol or "BTCUSDT").upper(),
            "lastPrice": f"{self.price:.2f}",
            "priceChangePercent": "1.5",
        }

    async def get_orderbook(self, symbol: str, limit: int = 100) -> dict:
        return {"lastUpdateId": 1, "bids": [["49999.0", "1.0"]], "asks": [["50001.0", "1.0"]]}

    async def ping(self) -> bool:
        return True

    async def get_exchange_info(self) -> dict:
        return {"symbols": [{"symbol": "BTCUSDT", "quoteAsset": "USDT", "filters": []}]}

    async def get_open_orders(self, symbol: str | None = None) -> list:
        return []

    async def get_balances(self) -> dict:
        return {"USDT": 100_000.0}

    async def place_order(self, **kwargs: object) -> dict:
        # No credentials configured in tests: the connector must refuse rather
        # than invent a fill.
        from app.core.exceptions import ConfigurationError

        raise ConfigurationError("Binance API credentials are not configured.")

    async def cancel_order(self, symbol: str, order_id: object) -> dict:
        return {"status": "CANCELED"}

    async def get_order(self, symbol: str, order_id: object) -> dict:
        return {"status": "CANCELED"}


@pytest.fixture
def stub_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinanceClient:
    """Replace the shared Binance client so tests never touch the network."""
    fake = FakeBinanceClient()
    for module in (
        "app.api.v1.endpoints.market_data",
        "app.api.v1.endpoints.health",
        "app.services.paper_trading_service",
        "app.services.live_trading_service",
        "app.services.kill_switch",
    ):
        monkeypatch.setattr(f"{module}.get_binance_client", lambda: fake, raising=False)
    return fake
