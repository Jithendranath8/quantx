"""
QuantX — Research Suite REST API Endpoints.

Walk-forward testing, parameter optimization, Monte Carlo simulation,
look-ahead bias auditing, the experiment registry, and AI observability.

Every route runs against the caller's real stored candles. These previously ran
on synthetic frames (a constant-price series, a single row) and several engines
ignored their inputs entirely, so the numbers described nothing.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.core.exceptions import ValidationError
from app.engines.research.bias_detector import BiasCheckReport, LookAheadBiasDetector
from app.engines.research.monte_carlo import MonteCarloEngine, MonteCarloSummary
from app.engines.research.optimization import (
    OptimizationResult,
    ParameterOptimizationEngine,
)
from app.engines.research.walk_forward import WalkForwardEngine, WalkForwardResult
from app.schemas.backtest import BacktestRequest
from app.services.ai_observability_service import AIObservabilityService
from app.services.backtest_service import BacktestService
from app.services.experiment_service import ExperimentRegistryService

router = APIRouter(prefix="/research", tags=["Research Suite & Observability"])

# Recorded on registered experiments so a result carries the cost assumptions
# it was produced under.
DEFAULT_FEE_RATE = 0.00075
DEFAULT_SLIPPAGE = 0.0005

# These are all CPU-bound multi-backtest runs; they get a tight budget.
_research_limit = Depends(RateLimiter("research", max_requests=5))


@router.post(
    "/walk-forward",
    response_model=WalkForwardResult,
    summary="Run walk-forward train/test splits",
    dependencies=[_research_limit],
)
async def run_walk_forward(
    user: CurrentUser,
    db: DBSession,
    strategy_name: str = Query("ema_crossover"),
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1h"),
    num_windows: int = Query(4, ge=1, le=20),
    register: bool = Query(True, description="Record the run in the experiment registry"),
) -> WalkForwardResult:
    """Backtest each rolling train and test window independently."""
    df = await BacktestService(db).load_candles(symbol, timeframe)
    result = await run_in_threadpool(
        WalkForwardEngine.run_walk_forward,
        strategy_name,
        df,
        num_windows,
        symbol,
        timeframe,
    )

    if register and result.total_windows > 0:
        await ExperimentRegistryService(db).register_from_dataset(
            strategy_name=strategy_name,
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            parameters={"num_windows": num_windows, "study": "walk_forward"},
            metrics={
                "avg_in_sample_sharpe": result.avg_in_sample_sharpe,
                "avg_out_of_sample_sharpe": result.avg_out_of_sample_sharpe,
                "efficiency_ratio": result.efficiency_ratio,
                "overfitting_warning": result.overfitting_warning,
                "total_windows": result.total_windows,
            },
            fees=DEFAULT_FEE_RATE,
            slippage=DEFAULT_SLIPPAGE,
        )

    return result


@router.post(
    "/optimize",
    response_model=OptimizationResult,
    summary="Run a parameter search scored by real backtests",
    dependencies=[_research_limit],
)
async def run_optimization(
    user: CurrentUser,
    db: DBSession,
    strategy_name: str = Query("ema_crossover"),
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1h"),
    method: str = Query("GRID_SEARCH", pattern="^(GRID_SEARCH|RANDOM_SEARCH|TPE)$"),
    max_evaluations: int = Query(50, ge=1, le=200),
    register: bool = Query(True, description="Record the run in the experiment registry"),
) -> OptimizationResult:
    """Search the strategy's parameter space, backtesting every candidate.

    TPE is sequential model-based optimization: it concentrates the evaluation
    budget on promising regions instead of sweeping the whole grid.
    """
    df = await BacktestService(db).load_candles(symbol, timeframe)

    def _run() -> OptimizationResult:
        return ParameterOptimizationEngine.run_optimization(
            strategy_name=strategy_name,
            df_candles=df,
            method=method,  # type: ignore[arg-type]
            symbol=symbol,
            timeframe=timeframe,
            max_evaluations=max_evaluations,
        )

    result = await run_in_threadpool(_run)

    if register and result.best_candidate is not None:
        # Recording the dataset fingerprint alongside the winning parameters is
        # what makes the result reproducible later.
        await ExperimentRegistryService(db).register_from_dataset(
            strategy_name=strategy_name,
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            parameters=result.best_candidate.params,
            metrics={
                "method": result.method,
                "evaluations": result.total_evaluations,
                "sharpe_ratio": result.best_candidate.sharpe_ratio,
                "sortino_ratio": result.best_candidate.sortino_ratio,
                "total_return_pct": result.best_candidate.total_return_pct,
                "max_drawdown_pct": result.best_candidate.max_drawdown_pct,
                "total_trades": result.best_candidate.total_trades,
                "overfitting_warning": result.overfitting_warning,
                "probabilistic_sharpe": result.probabilistic_sharpe,
                "deflated_sharpe": result.deflated_sharpe,
                "probability_of_backtest_overfitting": result.probability_of_backtest_overfitting,
            },
            fees=DEFAULT_FEE_RATE,
            slippage=DEFAULT_SLIPPAGE,
        )

    return result


@router.post(
    "/monte-carlo",
    response_model=MonteCarloSummary,
    summary="Run Monte Carlo resampling over a strategy's trades",
    dependencies=[_research_limit],
)
async def run_monte_carlo(
    user: CurrentUser,
    db: DBSession,
    strategy_name: str = Query("ema_crossover"),
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1h"),
    num_simulations: int = Query(1000, ge=100, le=50_000),
    initial_capital: float = Query(10_000.0, gt=0),
) -> MonteCarloSummary:
    """Backtest the strategy, then bootstrap-resample its realized trade PnLs.

    Raises:
        ValidationError: If the backtest produced no trades to resample.
    """
    service = BacktestService(db)
    result = await service.run_backtest(
        BacktestRequest(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            initial_capital=initial_capital,
        )
    )
    pnls = [float(t["pnl"]) for t in result.trades]
    if not pnls:
        raise ValidationError(
            f"Strategy '{strategy_name}' produced no trades on {symbol} {timeframe}; "
            "there is nothing to resample."
        )

    return await run_in_threadpool(
        MonteCarloEngine.run_simulation, pnls, initial_capital, num_simulations
    )


@router.post(
    "/bias-check",
    response_model=BiasCheckReport,
    summary="Audit a strategy for look-ahead bias",
    dependencies=[_research_limit],
)
async def audit_bias(
    user: CurrentUser,
    db: DBSession,
    strategy_name: str = Query("ema_crossover"),
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1h"),
) -> BiasCheckReport:
    """Compare signals computed with and without future data visible."""
    df = await BacktestService(db).load_candles(symbol, timeframe, limit=2000)
    return await run_in_threadpool(LookAheadBiasDetector.audit_strategy, strategy_name, df)


@router.get(
    "/experiments",
    summary="List registered research experiments",
)
async def list_experiments(
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """Fetch a page of registered experiments."""
    records = await ExperimentRegistryService(db).list_experiments(limit=limit, offset=offset)
    return [
        {
            "experiment_id": r.experiment_id,
            "strategy_name": r.strategy_name,
            "strategy_version": r.strategy_version,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "metrics": r.metrics,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@router.get(
    "/ai-observability",
    summary="Get AI model observability analytics",
)
async def get_ai_observability(
    user: CurrentUser,
    db: DBSession,
    window_days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Aggregate AI decision metrics over a bounded window.

    Win rate and expectancy are null until decisions have settled PnL attached.
    """
    return await AIObservabilityService(db).get_analytics(
        user_id=user.id, window_days=window_days
    )
