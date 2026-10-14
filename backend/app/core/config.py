"""
QuantX — Application Settings.

All configuration is loaded from environment variables via pydantic-settings.
Never hardcode secrets. Use .env file for local development.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-to-a-random-64-char-string"
DEFAULT_JWT_SECRET_KEY = "change-me-to-a-random-64-char-jwt-secret"
DEFAULT_POSTGRES_PASSWORD = "quantx_secure_password"


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Construct async database URL from individual components."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Construct sync database URL for Alembic migrations."""
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        """Construct Redis URL from individual components."""
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

    # ── Celery ───────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

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

    market_stream_enabled: bool = False
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
        """Fail fast when production is running with development defaults.

        Raises:
            RuntimeError: If any insecure default is still in place.
        """
        if not self.is_production:
            return

        problems: list[str] = []
        if self.secret_key == DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY is still the default value")
        if self.jwt_secret_key == DEFAULT_JWT_SECRET_KEY:
            problems.append("JWT_SECRET_KEY is still the default value")
        if self.postgres_password == DEFAULT_POSTGRES_PASSWORD:
            problems.append("POSTGRES_PASSWORD is still the default value")
        if self.debug:
            problems.append("DEBUG is enabled")
        if not self.redis_password:
            problems.append("REDIS_PASSWORD is empty")

        if problems:
            raise RuntimeError(
                "Refusing to start in production with insecure configuration: "
                + "; ".join(problems)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings singleton.

    Uses lru_cache to ensure settings are only loaded once from
    environment variables during the application lifecycle.
    """
    return Settings()
