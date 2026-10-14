"""
QuantX — API v1 Router Aggregator.
"""

from fastapi import APIRouter

from app.api.v1.endpoints.agent import router as agent_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.backtest import router as backtest_router
from app.api.v1.endpoints.events import router as events_router
from app.api.v1.endpoints.health import router as health_center_router
from app.api.v1.endpoints.indicators import router as indicators_router
from app.api.v1.endpoints.journal import router as journal_router
from app.api.v1.endpoints.live_trading import router as live_trading_router
from app.api.v1.endpoints.market_data import router as market_data_router
from app.api.v1.endpoints.monitoring import router as monitoring_router
from app.api.v1.endpoints.orchestrator import router as orchestrator_router
from app.api.v1.endpoints.paper_trading import router as paper_trading_router
from app.api.v1.endpoints.research import router as research_router
from app.api.v1.endpoints.risk import router as risk_router
from app.api.v1.endpoints.strategies import router as strategies_router

api_v1_router = APIRouter()

# Authentication & Access Control
api_v1_router.include_router(auth_router)

# Market Data & Analysis
api_v1_router.include_router(market_data_router)
api_v1_router.include_router(indicators_router)

# Strategies & AI Agent
api_v1_router.include_router(strategies_router)
api_v1_router.include_router(agent_router)
api_v1_router.include_router(orchestrator_router)

# Risk Engine & Execution
api_v1_router.include_router(risk_router)
api_v1_router.include_router(paper_trading_router)
api_v1_router.include_router(live_trading_router)

# Backtesting & Research Suite
api_v1_router.include_router(backtest_router)
api_v1_router.include_router(research_router)

# Analytics, Ledger & Journal
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(journal_router)
api_v1_router.include_router(events_router)

# Monitoring & Health Center
api_v1_router.include_router(monitoring_router)
api_v1_router.include_router(health_center_router)
