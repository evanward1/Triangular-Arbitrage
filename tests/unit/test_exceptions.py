"""Tests for the exceptions module."""

import pytest
from triangular_arbitrage.exceptions import (
    TriangularArbitrageError,
    ConfigurationError,
    ValidationError,
    ExchangeError,
    ExecutionError,
    ReconciliationError,
    RiskControlError,
    DataError,
    NetworkError,
)


def test_base_exception():
    """Test the base exception class."""
    error = TriangularArbitrageError("Test error")
    assert str(error) == "Test error"
    assert error.details == {}

    error_with_details = TriangularArbitrageError("Test error", {"key": "value"})
    assert error_with_details.details == {"key": "value"}


def test_configuration_error():
    """Test configuration error."""
    error = ConfigurationError("Config error", {"config_file": "test.yaml"})
    assert str(error) == "Config error"
    assert error.details["config_file"] == "test.yaml"
    assert isinstance(error, TriangularArbitrageError)


def test_validation_error():
    """Test validation error."""
    error = ValidationError("Validation failed")
    assert str(error) == "Validation failed"
    assert isinstance(error, TriangularArbitrageError)


def test_exchange_error():
    """Test exchange error."""
    error = ExchangeError("Exchange failed", exchange="binance", symbol="BTC/USDT")
    assert str(error) == "Exchange failed"
    assert error.exchange == "binance"
    assert error.symbol == "BTC/USDT"
    assert isinstance(error, TriangularArbitrageError)


def test_execution_error():
    """Test execution error."""
    error = ExecutionError("Execution failed", strategy="test_strategy", cycle_id="cycle_123")
    assert str(error) == "Execution failed"
    assert error.strategy == "test_strategy"
    assert error.cycle_id == "cycle_123"
    assert isinstance(error, TriangularArbitrageError)


def test_reconciliation_error():
    """Test reconciliation error."""
    error = ReconciliationError("Reconciliation failed", expected=100.0, actual=99.5)
    assert str(error) == "Reconciliation failed"
    assert error.expected == 100.0
    assert error.actual == 99.5
    assert isinstance(error, TriangularArbitrageError)


def test_risk_control_error():
    """Test risk control error."""
    error = RiskControlError(
        "Risk limit exceeded",
        risk_type="position_size",
        limit=0.1,
        current=0.15
    )
    assert str(error) == "Risk limit exceeded"
    assert error.risk_type == "position_size"
    assert error.limit == 0.1
    assert error.current == 0.15
    assert isinstance(error, TriangularArbitrageError)


def test_data_error():
    """Test data error."""
    error = DataError("Data error", source="market_data", symbol="BTC/USDT")
    assert str(error) == "Data error"
    assert error.source == "market_data"
    assert error.symbol == "BTC/USDT"
    assert isinstance(error, TriangularArbitrageError)


def test_network_error():
    """Test network error."""
    error = NetworkError("Network error", endpoint="api.binance.com", status_code=429)
    assert str(error) == "Network error"
    assert error.endpoint == "api.binance.com"
    assert error.status_code == 429
    assert isinstance(error, TriangularArbitrageError)


def test_exception_inheritance():
    """Test that all custom exceptions inherit from base exception."""
    exceptions = [
        ConfigurationError,
        ValidationError,
        ExchangeError,
        ExecutionError,
        ReconciliationError,
        RiskControlError,
        DataError,
        NetworkError,
    ]

    for exc_class in exceptions:
        instance = exc_class("test message")
        assert isinstance(instance, TriangularArbitrageError)
        assert isinstance(instance, Exception)