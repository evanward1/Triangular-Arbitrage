"""
Exception hierarchy for the triangular arbitrage system.

Provides specific exception types for different error categories to enable
better error handling and debugging.
"""

from typing import Optional, Dict, Any


class TriangularArbitrageError(Exception):
    """Base exception for all triangular arbitrage related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class ConfigurationError(TriangularArbitrageError):
    """Raised when there are configuration-related issues."""

    pass


class ValidationError(TriangularArbitrageError):
    """Raised when validation of data or configuration fails."""

    pass


class ExchangeError(TriangularArbitrageError):
    """Raised when exchange operations fail."""

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.exchange = exchange
        self.symbol = symbol


class ExecutionError(TriangularArbitrageError):
    """Raised when trade execution fails."""

    def __init__(
        self,
        message: str,
        strategy: Optional[str] = None,
        cycle_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.strategy = strategy
        self.cycle_id = cycle_id


class ReconciliationError(TriangularArbitrageError):
    """Raised when reconciliation of trades or positions fails."""

    def __init__(
        self,
        message: str,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.expected = expected
        self.actual = actual


class RiskControlError(TriangularArbitrageError):
    """Raised when risk control violations occur."""

    def __init__(
        self,
        message: str,
        risk_type: Optional[str] = None,
        limit: Optional[float] = None,
        current: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.risk_type = risk_type
        self.limit = limit
        self.current = current


class DataError(TriangularArbitrageError):
    """Raised when data processing or market data issues occur."""

    def __init__(
        self,
        message: str,
        source: Optional[str] = None,
        symbol: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.source = source
        self.symbol = symbol


class NetworkError(TriangularArbitrageError):
    """Raised when network or connectivity issues occur."""

    def __init__(
        self,
        message: str,
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.endpoint = endpoint
        self.status_code = status_code
