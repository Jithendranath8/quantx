"""
QuantX — Deployment config tests.

Cover the DATABASE_URL / REDIS_URL overrides that make the app deployable on
managed free tiers (Neon/Supabase/Upstash), including scheme normalization for
asyncpg and TLS passthrough for Redis.
"""

import pytest

from app.core.config import (
    DEFAULT_JWT_SECRET_KEY,
    DEFAULT_POSTGRES_PASSWORD,
    DEFAULT_SECRET_KEY,
    Settings,
    _to_async_dsn,
    _to_sync_dsn,
)


def _prod_settings(**overrides: object) -> Settings:
    """A production Settings with the always-required secrets already set, so a
    test can isolate the datastore-credential checks."""
    base: dict[str, object] = {
        "app_env": "production",
        "secret_key": "x" * 48,
        "jwt_secret_key": "y" * 48,
        "debug": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


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


def test_production_safety_passes_with_managed_urls() -> None:
    # Neon/Upstash carry the credential inside the override string, so the unused
    # component-password defaults must not block a correctly-configured deploy.
    s = _prod_settings(
        DATABASE_URL="postgresql://u:p@ep.neon.tech/db?sslmode=require",
        REDIS_URL="rediss://default:tok@up.upstash.io:6379",
    )
    s.validate_production_safety()  # must not raise


def test_production_safety_rejects_default_postgres_without_override() -> None:
    # No DATABASE_URL: the component password is live, so its default is unsafe.
    # Values are forced explicitly so the test does not depend on the container's
    # own POSTGRES_* / DATABASE_URL env (init kwargs outrank the environment).
    s = _prod_settings(
        DATABASE_URL="",
        postgres_password=DEFAULT_POSTGRES_PASSWORD,
        REDIS_URL="rediss://default:tok@up.upstash.io:6379",
    )
    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        s.validate_production_safety()


def test_production_safety_rejects_empty_redis_without_override() -> None:
    # No REDIS_URL and no component password: Redis would be unauthenticated.
    s = _prod_settings(
        DATABASE_URL="postgresql://u:p@ep.neon.tech/db",
        REDIS_URL="",
        redis_password="",
    )
    with pytest.raises(RuntimeError, match="REDIS_PASSWORD"):
        s.validate_production_safety()


def test_default_signing_secret_rejected_outside_development() -> None:
    # A deployment that forgets APP_ENV=production (lands on "staging") must
    # still never sign JWTs with the repo-default key.
    s = Settings(  # type: ignore[call-arg]
        app_env="staging",
        secret_key="x" * 48,
        jwt_secret_key=DEFAULT_JWT_SECRET_KEY,
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is still the default"):
        s.validate_production_safety()


def test_jwt_secret_must_differ_from_secret_key() -> None:
    same = "s" * 48
    s = Settings(app_env="production", secret_key=same, jwt_secret_key=same)  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match="must differ"):
        s.validate_production_safety()


def test_development_allows_the_shipped_defaults() -> None:
    # Local dev may run on defaults; the guard must not fire there.
    s = Settings(  # type: ignore[call-arg]
        app_env="development",
        secret_key=DEFAULT_SECRET_KEY,
        jwt_secret_key=DEFAULT_JWT_SECRET_KEY,
    )
    s.validate_production_safety()  # must not raise
