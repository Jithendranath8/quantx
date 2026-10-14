"""
QuantX — Deployment config tests.

Cover the DATABASE_URL / REDIS_URL overrides that make the app deployable on
managed free tiers (Neon/Supabase/Upstash), including scheme normalization for
asyncpg and TLS passthrough for Redis.
"""

from app.core.config import Settings, _to_async_dsn, _to_sync_dsn


def test_async_dsn_rewrites_scheme_and_drops_query() -> None:
    url = "postgresql://user:pass@ep.neon.tech/db?sslmode=require&channel_binding=require"
    out = _to_async_dsn(url)
    assert out == "postgresql+asyncpg://user:pass@ep.neon.tech/db"
    assert "sslmode" not in out  # asyncpg rejects libpq-style params


def test_async_dsn_accepts_postgres_scheme() -> None:
    assert _to_async_dsn("postgres://u:p@host/db").startswith("postgresql+asyncpg://")


def test_sync_dsn_keeps_query_for_alembic() -> None:
    url = "postgresql://u:p@host/db?sslmode=require"
    out = _to_sync_dsn(url)
    assert out == "postgresql://u:p@host/db?sslmode=require"


def test_database_url_override_wins() -> None:
    s = Settings(DATABASE_URL="postgresql://u:p@host/db?sslmode=require")
    assert s.database_url == "postgresql+asyncpg://u:p@host/db"
    assert s.database_url_sync == "postgresql://u:p@host/db?sslmode=require"


def test_database_url_falls_back_to_components() -> None:
    s = Settings(postgres_host="pg", postgres_user="qx", postgres_password="secret", postgres_db="quantx")
    assert s.database_url == "postgresql+asyncpg://qx:secret@pg:5432/quantx"


def test_redis_url_override_supports_tls() -> None:
    s = Settings(REDIS_URL="rediss://default:tok@fly-upstash.upstash.io:6379")
    assert s.redis_url == "rediss://default:tok@fly-upstash.upstash.io:6379"


def test_redis_url_falls_back_to_components() -> None:
    s = Settings(redis_host="r", redis_port=6380, redis_password="pw", redis_db=2)
    assert s.redis_url == "redis://:pw@r:6380/2"
