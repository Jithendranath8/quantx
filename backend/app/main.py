"""
QuantX — FastAPI Application Entry Point.

Configures the FastAPI app with lifespan events, CORS middleware,
global exception handlers, and Prometheus instrumentation.
"""

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_fastapi_instrumentator import Instrumentator

from app.connectors.binance_client import close_binance_client
from app.core.config import get_settings
from app.core.database import dispose_engine, get_engine
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    FeatureNotImplementedError,
    NotFoundError,
    QuantXError,
    RateLimitError,
    TradingError,
    ValidationError,
)
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, get_redis_client
from app.websockets.binance_stream import start_market_stream, stop_market_stream

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager.

    Handles startup and shutdown of shared resources: the database engine,
    the Redis pool, the Binance HTTP client, and market data ingestion.
    """
    # ── Startup ──────────────────────────────────────────────────────
    setup_logging()
    logger.info("application_starting", app_name=settings.app_name, env=settings.app_env)

    # Refuse to run production on development defaults.
    settings.validate_production_safety()

    if settings.mainnet_trading_enabled:
        logger.warning(
            "MAINNET_TRADING_ENABLED",
            detail="Orders placed through this instance will use real funds.",
        )

    try:
        redis = await get_redis_client()
        await redis.ping()
        logger.info("redis_connected", host=settings.redis_host)
    except Exception as exc:
        # Redis backs rate limiting and the WebSocket fan-out. In production a
        # missing cache is a misconfiguration worth failing on rather than
        # discovering later under load.
        logger.error("redis_connection_failed", error=str(exc))
        if settings.is_production:
            raise RuntimeError(f"Redis is unreachable at startup: {exc}") from exc

    await start_market_stream()
    logger.info("application_started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    await stop_market_stream()
    await close_binance_client()
    await close_redis()
    await dispose_engine()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    description="AI-powered quantitative trading research platform",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── CORS Middleware ──────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ── Prometheus Instrumentation ───────────────────────────────────────

_metrics_auth = HTTPBasic(auto_error=False)


def _verify_metrics_access(
    credentials: HTTPBasicCredentials | None = Depends(_metrics_auth),  # noqa: B008 - FastAPI dependency idiom
) -> None:
    """Gate /metrics behind HTTP basic auth.

    Metrics expose endpoint names, traffic volumes and error rates. Left open
    they are free reconnaissance, so scrapers authenticate with the app's
    secret key unless METRICS_REQUIRE_AUTH is explicitly disabled.
    """
    if not settings.metrics_require_auth:
        return
    if credentials is None or not secrets.compare_digest(
        credentials.password, settings.secret_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid metrics credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


if settings.prometheus_enabled:
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        dependencies=[Depends(_verify_metrics_access)],
    )


# ── Global Exception Handlers ───────────────────────────────────────


# FastAPI serializes responses directly now, so no custom response class is
# configured; error handlers still return a JSONResponse explicitly.
def _error_response(
    status_code: int,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Create a standardized error response."""
    body: dict[str, Any] = {"error": True, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body, headers=headers)


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Handle authentication failures → 401."""
    logger.warning("authentication_failed", path=request.url.path, detail=exc.message)
    return _error_response(401, exc.message, headers={"WWW-Authenticate": "Bearer"})


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    """Handle authorization failures → 403."""
    logger.warning("authorization_failed", path=request.url.path, detail=exc.message)
    return _error_response(403, exc.message)


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Handle resource not found → 404."""
    return _error_response(404, exc.message, exc.details)


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """Handle duplicate resource → 409."""
    return _error_response(409, exc.message, exc.details)


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle domain validation errors → 422."""
    return _error_response(422, exc.message, exc.details)


@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    """Handle throttled requests → 429."""
    return _error_response(
        429,
        exc.message,
        exc.details,
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
    """Handle operations the running configuration forbids → 403."""
    logger.warning("configuration_error", path=request.url.path, detail=exc.message)
    return _error_response(403, exc.message, exc.details)


@app.exception_handler(FeatureNotImplementedError)
async def not_implemented_handler(request: Request, exc: FeatureNotImplementedError) -> JSONResponse:
    """Handle unimplemented capabilities → 501."""
    return _error_response(501, exc.message, exc.details)


@app.exception_handler(TradingError)
async def trading_error_handler(request: Request, exc: TradingError) -> JSONResponse:
    """Handle trading operation errors → 400."""
    logger.error("trading_error", path=request.url.path, detail=exc.message, details=exc.details)
    return _error_response(400, exc.message, exc.details)


@app.exception_handler(QuantXError)
async def quantx_error_handler(request: Request, exc: QuantXError) -> JSONResponse:
    """Handle all other QuantX errors → 500."""
    logger.error("quantx_error", path=request.url.path, detail=exc.message)
    return _error_response(500, exc.message)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions → 500."""
    logger.exception("unhandled_exception", path=request.url.path, exc_info=exc)
    message = "Internal server error"
    if settings.debug and not settings.is_production:
        message = f"Internal server error: {exc!s}"
    return _error_response(500, message)


# ── Health Check ─────────────────────────────────────────────────────


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Liveness probe for load balancers.

    Deliberately shallow and dependency-free: a liveness check that touches the
    database takes the whole service out of rotation during a brief DB blip.
    Use /api/v1/health/system for the full readiness report.
    """
    return {"status": "healthy", "service": settings.app_name}


@app.get("/ready", tags=["System"])
async def readiness_check() -> JSONResponse:
    """Readiness probe verifying the datastores are actually reachable."""
    checks: dict[str, bool] = {}
    try:
        async with get_engine().connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    try:
        checks["redis"] = bool(await (await get_redis_client()).ping())
    except Exception:
        checks["redis"] = False

    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "checks": checks},
    )


# ── Include API Routers ─────────────────────────────────────────────

from app.api.v1.router import api_v1_router  # noqa: E402
from app.websockets.gateway import router as ws_router  # noqa: E402

app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(ws_router)
