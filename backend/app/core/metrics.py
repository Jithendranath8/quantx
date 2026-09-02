"""
QuantX — Custom Prometheus Metrics.

Defines counters, gauges, and histograms for monitoring system performance and trades.
"""

from prometheus_client import Counter, Gauge, Histogram

# HTTP Request Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "quantx_http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "quantx_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)

# Trading Metrics
TRADES_EXECUTED_TOTAL = Counter(
    "quantx_trades_executed_total",
    "Total trades executed",
    ["symbol", "side", "status"],
)

CIRCUIT_BREAKER_EVENTS_TOTAL = Counter(
    "quantx_circuit_breaker_events_total",
    "Total circuit breaker trigger events",
)

ACTIVE_POSITIONS_GAUGE = Gauge(
    "quantx_active_positions_total",
    "Current active positions count",
    ["symbol"],
)

SYSTEM_HEALTH_GAUGE = Gauge(
    "quantx_system_health_status",
    "System health status (1 = Healthy, 0 = Unhealthy)",
)
