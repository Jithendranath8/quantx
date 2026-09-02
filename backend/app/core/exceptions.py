"""
QuantX — Custom Exception Hierarchy.

Defines domain-specific exceptions for clean error handling
across all modules. Each exception maps to appropriate HTTP status codes.
"""

from typing import Any


class QuantXError(Exception):
    """Base exception for all QuantX errors."""

    def __init__(self, message: str = "An unexpected error occurred", details: Any = None) -> None:
        self.message = message
        self.details = details
        super().__init__(self.message)


# ── Authentication Errors ────────────────────────────────────────────


class AuthenticationError(QuantXError):
    """Raised when authentication fails (invalid credentials, expired token)."""

    def __init__(self, message: str = "Authentication failed", details: Any = None) -> None:
        super().__init__(message, details)


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are incorrect."""

    def __init__(self, message: str = "Invalid email or password") -> None:
        super().__init__(message)


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT token has expired."""

    def __init__(self, message: str = "Token has expired") -> None:
        super().__init__(message)


class TokenInvalidError(AuthenticationError):
    """Raised when a JWT token is malformed or invalid."""

    def __init__(self, message: str = "Invalid token") -> None:
        super().__init__(message)


# ── Authorization Errors ─────────────────────────────────────────────


class AuthorizationError(QuantXError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions", details: Any = None) -> None:
        super().__init__(message, details)


# ── Resource Errors ──────────────────────────────────────────────────


class NotFoundError(QuantXError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = "Resource", identifier: Any = None) -> None:
        message = f"{resource} not found"
        if identifier is not None:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(message, {"resource": resource, "identifier": identifier})


class ConflictError(QuantXError):
    """Raised when a resource already exists (duplicate)."""

    def __init__(self, resource: str = "Resource", field: str = "", value: Any = None) -> None:
        message = f"{resource} already exists"
        if field and value:
            message = f"{resource} with {field} '{value}' already exists"
        super().__init__(message, {"resource": resource, "field": field, "value": value})


class ValidationError(QuantXError):
    """Raised when input validation fails at the domain level."""

    def __init__(self, message: str = "Validation failed", details: Any = None) -> None:
        super().__init__(message, details)


# ── Trading Errors ───────────────────────────────────────────────────


class TradingError(QuantXError):
    """Base error for all trading operations."""

    def __init__(self, message: str = "Trading operation failed", details: Any = None) -> None:
        super().__init__(message, details)


class RiskLimitExceededError(TradingError):
    """Raised when a trade violates risk engine rules."""

    def __init__(self, rule: str, message: str = "Risk limit exceeded") -> None:
        super().__init__(message, {"rule": rule})


class InsufficientBalanceError(TradingError):
    """Raised when account balance is insufficient for a trade."""

    def __init__(self, required: float, available: float) -> None:
        message = f"Insufficient balance: required {required}, available {available}"
        super().__init__(message, {"required": required, "available": available})


class OrderRejectedError(TradingError):
    """Raised when an order is rejected by the exchange."""

    def __init__(self, reason: str, order_id: str | None = None) -> None:
        message = f"Order rejected: {reason}"
        super().__init__(message, {"reason": reason, "order_id": order_id})


class CircuitBreakerTriggeredError(TradingError):
    """Raised when the circuit breaker halts trading."""

    def __init__(self, reason: str = "Circuit breaker activated") -> None:
        super().__init__(reason)


# ── External Service Errors ──────────────────────────────────────────


class ExternalServiceError(QuantXError):
    """Raised when an external service (Binance, OpenAI) fails."""

    def __init__(self, service: str, message: str = "External service error", details: Any = None) -> None:
        super().__init__(f"{service}: {message}", details)


class BinanceError(ExternalServiceError):
    """Raised for Binance API errors."""

    def __init__(self, message: str = "Binance API error", details: Any = None) -> None:
        super().__init__("Binance", message, details)


class OpenAIError(ExternalServiceError):
    """Raised for OpenAI API errors."""

    def __init__(self, message: str = "OpenAI API error", details: Any = None) -> None:
        super().__init__("OpenAI", message, details)


# ── Request Throttling ───────────────────────────────────────────────


class RateLimitError(QuantXError):
    """Raised when a client exceeds a configured rate limit."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: int = 60,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, {"retry_after_seconds": retry_after_seconds})


# ── Configuration & Capability Errors ────────────────────────────────


class ConfigurationError(QuantXError):
    """Raised when the running configuration forbids the requested operation."""

    def __init__(self, message: str = "Operation not permitted by configuration", details: Any = None) -> None:
        super().__init__(message, details)


class FeatureNotImplementedError(QuantXError):
    """Raised by endpoints whose backing capability genuinely does not exist yet.

    Returning this is always preferable to returning fabricated data: a caller
    can handle a 501, but cannot detect an invented number.
    """

    def __init__(self, feature: str, message: str | None = None) -> None:
        super().__init__(
            message or f"{feature} is not implemented",
            {"feature": feature},
        )
