"""
Unit tests for triangular_arbitrage.utils module.

Tests common utility functions and ensures no circular imports.
"""

import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from triangular_arbitrage.utils import (
    get_current_timestamp,
    timestamp_to_iso,
    iso_to_timestamp,
    format_duration,
    safe_json_dump,
    safe_json_load,
    ensure_path_exists,
    is_file_readable,
    get_file_size_mb,
    round_to_precision,
    calculate_percentage,
    clamp,
    basis_points_to_decimal,
    decimal_to_basis_points,
    setup_logger,
    deep_merge,
    get_nested_value,
    is_valid_currency_code,
    is_positive_number,
    is_valid_percentage,
    is_valid_basis_points,
)


class TestTimestampUtils:
    """Test timestamp utilities."""

    def test_get_current_timestamp(self):
        """Test getting current timestamp."""
        timestamp = get_current_timestamp()
        assert isinstance(timestamp, float)
        assert timestamp > 0

    def test_timestamp_iso_conversion(self):
        """Test timestamp to ISO conversion and back."""
        original_timestamp = 1700000000.0
        iso_string = timestamp_to_iso(original_timestamp)
        converted_back = iso_to_timestamp(iso_string)

        assert isinstance(iso_string, str)
        assert "T" in iso_string  # ISO format
        assert (
            abs(converted_back - original_timestamp) < 1.0
        )  # Allow small precision loss

    def test_format_duration(self):
        """Test duration formatting."""
        assert format_duration(30) == "30.00s"
        assert format_duration(120) == "2.0m"
        assert format_duration(3600) == "1.0h"


class TestJsonUtils:
    """Test JSON utilities."""

    def test_safe_json_dump(self):
        """Test safe JSON serialization."""
        data = {"test": "value", "number": 42}
        json_str = safe_json_dump(data)

        assert isinstance(json_str, str)
        assert "test" in json_str
        assert "42" in json_str

    def test_safe_json_dump_datetime(self):
        """Test JSON serialization with datetime."""
        dt = datetime.now(timezone.utc)
        data = {"timestamp": dt}
        json_str = safe_json_dump(data)

        assert isinstance(json_str, str)
        assert "T" in json_str  # ISO format

    def test_safe_json_load_valid(self):
        """Test loading valid JSON."""
        json_str = '{"test": "value"}'
        data = safe_json_load(json_str)

        assert data == {"test": "value"}

    def test_safe_json_load_invalid(self):
        """Test loading invalid JSON."""
        invalid_json = "{invalid json}"
        data = safe_json_load(invalid_json)

        assert data is None


class TestPathUtils:
    """Test path utilities."""

    def test_ensure_path_exists(self):
        """Test ensuring directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test_subdir"
            result_path = ensure_path_exists(test_dir)

            assert result_path.exists()
            assert result_path.is_dir()

    def test_ensure_path_exists_file(self):
        """Test ensuring parent directory exists for file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "subdir" / "test.txt"
            ensure_path_exists(test_file, is_file=True)

            assert test_file.parent.exists()
            assert test_file.parent.is_dir()

    def test_is_file_readable(self):
        """Test file readability check."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            assert is_file_readable(temp_path) is True
            assert is_file_readable("/nonexistent/file") is False
        finally:
            Path(temp_path).unlink()

    def test_get_file_size_mb(self):
        """Test getting file size in MB."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("x" * 1000)  # 1KB
            temp_path = f.name

        try:
            size_mb = get_file_size_mb(temp_path)
            assert isinstance(size_mb, float)
            assert size_mb > 0
            assert size_mb < 1  # Less than 1MB
        finally:
            Path(temp_path).unlink()


class TestMathUtils:
    """Test mathematical utilities."""

    def test_round_to_precision(self):
        """Test precision rounding."""
        assert round_to_precision(3.14159, 2) == 3.14
        assert round_to_precision(3.14159, 4) == 3.1416

    def test_calculate_percentage(self):
        """Test percentage calculation."""
        assert calculate_percentage(25, 100) == 25.0
        assert calculate_percentage(1, 3) == pytest.approx(33.333, rel=1e-3)
        assert calculate_percentage(10, 0) == 0.0  # Zero division

    def test_clamp(self):
        """Test value clamping."""
        assert clamp(5, 0, 10) == 5
        assert clamp(-5, 0, 10) == 0
        assert clamp(15, 0, 10) == 10

    def test_basis_points_conversion(self):
        """Test basis points conversion."""
        assert basis_points_to_decimal(100) == 0.01
        assert decimal_to_basis_points(0.01) == 100.0

        # Round trip
        original = 0.0525
        converted = decimal_to_basis_points(basis_points_to_decimal(original))
        assert converted == pytest.approx(original, rel=1e-10)


class TestDictUtils:
    """Test dictionary utilities."""

    def test_deep_merge(self):
        """Test deep dictionary merging."""
        base = {"a": 1, "b": {"x": 10, "y": 20}}
        update = {"b": {"x": 15, "z": 30}, "c": 3}
        result = deep_merge(base, update)

        expected = {"a": 1, "b": {"x": 15, "y": 20, "z": 30}, "c": 3}
        assert result == expected

    def test_get_nested_value(self):
        """Test getting nested dictionary values."""
        data = {"level1": {"level2": {"value": 42}}}

        assert get_nested_value(data, "level1.level2.value") == 42
        assert get_nested_value(data, "level1.nonexistent", "default") == "default"
        assert get_nested_value(data, "nonexistent", "default") == "default"


class TestValidationUtils:
    """Test validation utilities."""

    def test_is_valid_currency_code(self):
        """Test currency code validation."""
        assert is_valid_currency_code("BTC") is True
        assert is_valid_currency_code("USD") is True
        assert is_valid_currency_code("USDT") is True
        assert is_valid_currency_code("btc") is False  # Must be uppercase
        assert is_valid_currency_code("B") is False  # Too short
        assert is_valid_currency_code("123") is False  # Not alpha

    def test_is_positive_number(self):
        """Test positive number validation."""
        assert is_positive_number(1) is True
        assert is_positive_number(1.5) is True
        assert is_positive_number("2.5") is True
        assert is_positive_number(0) is False
        assert is_positive_number(-1) is False
        assert is_positive_number("invalid") is False

    def test_is_valid_percentage(self):
        """Test percentage validation."""
        assert is_valid_percentage(50) is True
        assert is_valid_percentage(0, allow_zero=True) is True
        assert is_valid_percentage(0, allow_zero=False) is False
        assert is_valid_percentage(100) is True
        assert is_valid_percentage(101) is False
        assert is_valid_percentage(-1) is False

    def test_is_valid_basis_points(self):
        """Test basis points validation."""
        assert is_valid_basis_points(100) is True
        assert is_valid_basis_points(0) is True
        assert is_valid_basis_points(10000) is True
        assert is_valid_basis_points(10001) is False
        assert is_valid_basis_points(-1) is False


class TestLoggingUtils:
    """Test logging utilities."""

    def test_setup_logger(self):
        """Test logger setup."""
        logger = setup_logger("test_logger")

        assert logger.name == "test_logger"
        assert len(logger.handlers) > 0


def test_no_circular_imports():
    """Test that importing utils doesn't cause circular imports."""
    # This test passes if the import at the top doesn't raise ImportError
    import triangular_arbitrage.utils

    assert hasattr(triangular_arbitrage.utils, "get_current_timestamp")
