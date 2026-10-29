"""
QuantX — Application Settings.

All configuration is loaded from environment variables via pydantic-settings.
Never hardcode secrets. Use .env file for local development.
"""

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PG_SCHEME = re.compile(r"^postgres(?:ql)?(?:\+\w+)?://")


def _to_async_dsn(url: str) -> str:
    """Normalize a provider DATABASE_URL to an asyncpg DSN.

    Rewrites the scheme to ``postgresql+asyncpg`` and drops libpq-style query
    params (e.g. ``sslmode=require``) that asyncpg does not accept; asyncpg
    negotiates TLS automatically against providers that require it.
    """
    base = url.split("?", 1)[0]
    return _PG_SCHEME.sub("postgresql+asyncpg://", base)


def _to_sync_dsn(url: str) -> str:
    """Normalize a provider DATABASE_URL to a sync (psycopg) DSN for Alembic.

    Keeps the query string, so ``sslmode=require`` is preserved for migrations.
    """
    return _PG_SCHEME.sub("postgresql://", url)


DEFAULT_SECRET_KEY = "change-me-to-a-random-64-char-string"
DEFAULT_JWT_SECRET_KEY = "change-me-to-a-random-64-char-jwt-secret"
DEFAULT_POSTGRES_PASSWORD = "quantx_secure_password"

# Models a provider has shut down, mapped to the provider's named replacement.
# Groq retired the Llama 3.x chat models on 2026-08-16.
RETIRED_MODEL_REPLACEMENTS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
}


class Settings(BaseSettings):
    """Central configuration for the QuantX application.

    All values are loaded from environment variables or a .env file.
    Secrets must never be committed to version control.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "QuantX"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    secret_key: str = Field(default=DEFAULT_SECRET_KEY, min_length=16)

    # ── Backend Server ───────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_workers: int = 4
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Notifications ────────────────────────────────────────────────────
    alert_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # ── PostgreSQL ───────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "quantx"
    postgres_password: str = DEFAULT_POSTGRES_PASSWORD
    postgres_db: str = "quantx"

    # Pool sizing is per-process. Total connections to PostgreSQL are
    # (db_pool_size + db_max_overflow) * number_of_processes, so keep these
    # small enough that API workers + Celery workers stay under the server's
    # max_connections (default 100).
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
    db_command_timeout_seconds: int = 30

    # A single DATABASE_URL (as managed providers like Neon/Supabase/Render emit)
    # overrides the individual POSTGRES_* parts, so the app is deployable on any
    # PaaS without re-templating the connection components.
    database_url_override: str = Field(default="", validation_alias="DATABASE_URL")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async (asyncpg) database URL; honours a DATABASE_URL override."""
        if self.database_url_override:
            return _to_async_dsn(self.database_url_override)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Sync database URL for Alembic migrations; honours DATABASE_URL."""
        if self.database_url_override:
            return _to_sync_dsn(self.database_url_override)
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_max_connections: int = 50

    # A single REDIS_URL (as Upstash/Redis Cloud emit) overrides the parts and,
    # crucially, allows a TLS scheme (rediss://) that managed Redis requires.
    redis_url_override: str = Field(default="", validation_alias="REDIS_URL")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        """Redis URL; honours a REDIS_URL override (supports rediss:// TLS)."""
        if self.redis_url_override:
            return self.redis_url_override
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── JWT Authentication ───────────────────────────────────────────────
    jwt_secret_key: str = Field(default=DEFAULT_JWT_SECRET_KEY, min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # ── Binance ──────────────────────────────────────────────────────────
    binance_api_key: str = ""
    binance_secret: str = ""
    binance_testnet: bool = True

    # Host for *reading* public mainnet market data (klines, depth, tickers).
    # Defaults to Binance's public data mirror rather than api.binance.com
    # because the main REST API geo-blocks many datacenter regions (HTTP 451),
    # while data-api.binance.vision serves the same mainnet data unrestricted and
    # without auth. Override if you deploy somewhere api.binance.com is allowed.
    binance_market_data_url: str = "https://data-api.binance.vision"

    # WebSocket host for the live market-data feed. Like the REST host above, it
    # defaults to Binance's public mirror: it is geo-unrestricted (the plain
    # stream.binance.com is blocked from the same regions as the REST API) and
    # carries real mainnet ticks, whereas the testnet feed is thin and routinely
    # stalls — which looks like "a few candles, then nothing" in the UI. Live
    # data is read-only public information, so this is independent of
    # BINANCE_TESTNET (which still governs where orders go).
    binance_market_ws_url: str = "wss://data-stream.binance.vision/stream"

    # Hard safety interlock. Placing orders against Binance mainnet requires
    # BOTH binance_testnet=false AND allow_mainnet_trading=true. Defaulting
    # this to false means a misconfigured BINANCE_TESTNET cannot by itself
    # move real money.
    allow_mainnet_trading: bool = False

    @property
    def mainnet_trading_enabled(self) -> bool:
        """True only when live mainnet order placement is explicitly permitted."""
        return (not self.binance_testnet) and self.allow_mainnet_trading

    # ── AI Provider (OpenAI-compatible) ──────────────────────────────────
    # Any endpoint speaking the OpenAI chat-completions API works here, so the
    # agent is not tied to OpenAI billing. Examples:
    #   OpenAI    (unset)                                          gpt-4o
    #   Ollama    http://localhost:11434/v1                        llama3.2:1b
    #   Gemini    https://generativelanguage.googleapis.com/v1beta/openai/
    #   Groq      https://api.groq.com/openai/v1
    #   OpenRouter https://openrouter.ai/api/v1
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"

    @field_validator("openai_model", mode="before")
    @classmethod
    def _blank_model_means_default(cls, v: object) -> object:
        """A blank OPENAI_MODEL falls back to the default rather than disabling AI.

        An empty value would otherwise pass an empty model name to the provider
        and surface as "no provider configured", which points at the wrong
        setting entirely.
        """
        if isinstance(v, str) and not v.strip():
            return "gpt-4o"
        if isinstance(v, str):
            # A provider retiring a model turns every call into a 404, and the
            # agent silently degrades to WAIT. Map known shutdowns forward so a
            # stale env var keeps working until it is updated.
            return RETIRED_MODEL_REPLACEMENTS.get(v.strip(), v.strip())
        return v

    @field_validator("openai_base_url", mode="before")
    @classmethod
    def _blank_base_url_means_default(cls, v: object) -> object:
        """Treat a blank OPENAI_BASE_URL as unset.

        .env.example ships the key with an empty value so users can fill in a
        provider. Pydantic reads that as "" rather than None, and an empty
        string is truthy enough to reach the OpenAI client, which then points
        at nothing instead of falling back to api.openai.com.
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def ai_provider_configured(self) -> bool:
        """Whether an AI provider can be reached.

        A local endpoint needs no key at all, so key presence alone is not the
        right test.
        """
        return bool(self.openai_api_key or self.openai_base_url)

    # ── Agentic LLM runtime ──────────────────────────────────────────────
    # The tool-calling agent runtime is provider-agnostic. "auto" prefers
    # Anthropic when an anthropic_api_key is set, otherwise the OpenAI-
    # compatible backend above (which includes local Ollama / Groq / Gemini).
    llm_provider: str = "auto"  # auto | anthropic | openai
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    # Hard ceiling on tool-calling iterations per agent run, so a model that
    # keeps requesting tools can never loop forever or exhaust the budget.
    agent_max_tool_iterations: int = 8

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def _normalize_anthropic_key(cls, v: object) -> object:
        """Treat a blank ANTHROPIC_API_KEY as absent, like the OpenAI key."""
        if isinstance(v, str) and not v.strip():
            return ""
        return v

    @property
    def resolved_llm_provider(self) -> str:
        """The concrete provider the agent runtime should use.

        Resolves "auto" to a real backend so the rest of the system never has
        to re-implement the preference order.
        """
        choice = (self.llm_provider or "auto").strip().lower()
        if choice == "auto":
            return "anthropic" if self.anthropic_api_key else "openai"
        return choice

    @property
    def agent_runtime_configured(self) -> bool:
        """Whether at least one agent-runtime backend can be reached."""
        return bool(self.anthropic_api_key) or self.ai_provider_configured

    # ── Machine learning / MLOps ─────────────────────────────────────────
    # Where trained model artifacts and their metadata are written. Batch
    # training (bash scripts / Celery) writes here; the predict tool reads here.
    ml_model_dir: str = "./ml_artifacts"
    # MLflow tracking server URI; when unset, MLflow logs to a local ./mlruns
    # directory, so experiment tracking works with no server to stand up.
    mlflow_tracking_uri: str | None = None
    ml_sequence_length: int = 16
    ml_default_symbol: str = "BTCUSDT"
    ml_default_timeframe: str = "1h"

    @field_validator("mlflow_tracking_uri", mode="before")
    @classmethod
    def _blank_mlflow_uri_means_default(cls, v: object) -> object:
        """Treat a blank MLFLOW_TRACKING_URI as unset (local ./mlruns)."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # ── Scheduled jobs (serverless cron) ─────────────────────────────────
    # When set, POST /api/v1/internal/jobs/{name} with header X-Cron-Secret runs
    # a periodic maintenance job. This lets a free external scheduler (e.g. a
    # GitHub Actions cron) stand in for an always-on Celery worker on a free
    # deployment. Leave unset to disable the endpoint entirely.
    cron_secret: str = ""

    # ── Celery ───────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    # Whether an always-on Celery worker is part of this deployment. On the
    # free-tier / serverless deploy it is not — a scheduled cron drives the
    # periodic jobs instead — so the absence of a worker is the intended design,
    # not an outage, and the health check reports "cron mode" rather than a
    # failure. Set true for a full stack that runs a dedicated worker, so a
    # genuinely-down worker is surfaced.
    celery_worker_expected: bool = False

    # ── Rate Limiting ────────────────────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 10
    rate_limit_default_per_minute: int = 120
    rate_limit_expensive_per_minute: int = 10

    # ── Workload Guardrails ──────────────────────────────────────────────
    max_timeframes_per_request: int = 8
    backtest_max_candles: int = 20000
    export_max_rows: int = 100_000

    # ── Data Retention (days; 0 disables pruning for that table) ─────────
    retention_candles_days: int = 400
    retention_event_ledger_days: int = 365
    retention_audit_log_days: int = 365
    retention_ai_decision_log_days: int = 365

    # ── Monitoring ───────────────────────────────────────────────────────
    prometheus_enabled: bool = True
    metrics_require_auth: bool = True

    # ── Market Data ──────────────────────────────────────────────────────
    # Single source of truth for which markets the platform covers. This drives
    # the API's symbol list, the WebSocket stream, and the scheduled backfill,
    # so the UI cannot offer a symbol or timeframe that nothing ingests.
    market_symbols: str = (
        "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,DOGEUSDT"
    )
    market_timeframes: str = "1m,5m,15m,1h,4h,1d"

    # One-process deployment (a single uvicorn worker — the free-tier default,
    # and what BACKEND_WORKERS=1 gives). When true, the live-data path needs no
    # Redis: the ingestion stream runs directly (no Redis leader election) and
    # fans ticks out to WebSocket clients in-process, instead of PUBLISHing every
    # tick to Redis and renewing a Redis lock on a timer. That per-tick +
    # per-heartbeat traffic alone exhausts a managed free Redis (Upstash), which
    # both takes Redis down and stops live updates from reaching the browser.
    # Set false ONLY when running multiple workers/replicas, where Redis is
    # required to elect one ingestor and bridge ticks across processes.
    single_worker_mode: bool = True

    market_stream_enabled: bool = False
    # Run one market-data coverage sync in the background at startup. The live
    # stream only writes a bar when it closes, so after any downtime the stored
    # history has a hole until the next scheduled sync — on deployments without
    # an always-on worker or an external cron, that hole never heals. The sync
    # fetches only missing/stale pairs, so it is cheap when the DB is current.
    market_sync_on_startup: bool = True
    # Both default to the market_* lists when left blank, so the live stream,
    # the stored history and the UI all cover exactly the same ground. Streaming
    # every timeframe is what keeps each one current: a closed bar is written
    # the moment it closes, rather than waiting for the next REST sync.
    market_stream_symbols: str = ""
    market_stream_intervals: str = ""

    @property
    def market_symbol_list(self) -> list[str]:
        """Symbols the platform covers."""
        return [s.strip().upper() for s in self.market_symbols.split(",") if s.strip()]

    @property
    def market_timeframe_list(self) -> list[str]:
        """Timeframes the platform stores."""
        return [t.strip() for t in self.market_timeframes.split(",") if t.strip()]

    # Perpetual symbols whose funding rate and open interest are ingested.
    derivatives_symbols: str = "BTCUSDT,ETHUSDT"
    derivatives_backfill_days: int = 30

    @property
    def derivatives_symbol_list(self) -> list[str]:
        """Parse comma-separated derivatives symbols into an uppercase list."""
        return [s.strip().upper() for s in self.derivatives_symbols.split(",") if s.strip()]

    @property
    def market_stream_symbol_list(self) -> list[str]:
        """Symbols the live stream subscribes to; falls back to market_symbols."""
        explicit = [s.strip().upper() for s in self.market_stream_symbols.split(",") if s.strip()]
        return explicit or self.market_symbol_list

    @property
    def market_stream_interval_list(self) -> list[str]:
        """Intervals the live stream subscribes to; falls back to market_timeframes."""
        explicit = [s.strip() for s in self.market_stream_intervals.split(",") if s.strip()]
        return explicit or self.market_timeframe_list

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated origins into a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    def validate_production_safety(self) -> None:
        """Fail fast when a deployed service is running with insecure defaults.

        The token-signing secrets are checked on EVERY non-development
        environment, not only production: a deployment that forgets to set
        APP_ENV must still never sign JWTs (or guard /metrics) with the key
        published as the default in this repo. The remaining checks (debug,
        datastore passwords) are production-only.

        Raises:
            RuntimeError: If any insecure default is still in place.
        """
        # Local development may run on the shipped defaults; nothing reachable may.
        if self.app_env == "development":
            return

        problems: list[str] = []

        # A default or shared signing secret lets anyone forge a valid token for
        # any known user id — this is the highest-impact misconfiguration, so it
        # is enforced regardless of which non-dev env this is.
        if self.secret_key == DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY is still the default value")
        if self.jwt_secret_key == DEFAULT_JWT_SECRET_KEY:
            problems.append("JWT_SECRET_KEY is still the default value")
        if self.jwt_secret_key == self.secret_key:
            problems.append("JWT_SECRET_KEY must differ from SECRET_KEY")

        if self.is_production:
            # The component password is only used when there is no DATABASE_URL /
            # REDIS_URL override. Managed providers (Neon, Upstash, …) embed the
            # credential in that single connection string, so requiring the
            # component password there would reject a correctly-configured deploy.
            if not self.database_url_override and self.postgres_password == DEFAULT_POSTGRES_PASSWORD:
                problems.append("POSTGRES_PASSWORD is still the default value (or set DATABASE_URL)")
            if self.debug:
                problems.append("DEBUG is enabled")
            if not self.redis_url_override and not self.redis_password:
                problems.append("REDIS_PASSWORD is empty (or set REDIS_URL)")

        if problems:
            raise RuntimeError(
                "Refusing to start with insecure configuration: " + "; ".join(problems)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings singleton.

    Uses lru_cache to ensure settings are only loaded once from
    environment variables during the application lifecycle.
    """
    return Settings()
