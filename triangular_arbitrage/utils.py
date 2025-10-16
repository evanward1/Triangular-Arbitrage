"""
Common utilities and helper functions for triangular arbitrage system.

This module provides centralized helper functions for common operations like
timestamp handling, JSON serialization, path validation, and mathematical calculations.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union


# Timestamp utilities
def get_current_timestamp() -> float:
    """Get current Unix timestamp as float."""
    return time.time()


def timestamp_to_iso(timestamp: float) -> str:
    """Convert Unix timestamp to ISO 8601 string."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def iso_to_timestamp(iso_string: str) -> float:
    """Convert ISO 8601 string to Unix timestamp."""
    return datetime.fromisoformat(iso_string.replace("Z", "+00:00")).timestamp()


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


# JSON utilities
def safe_json_dump(data: Any, **kwargs) -> str:
    """
    Safely serialize data to JSON with sensible defaults.

    Args:
        data: Data to serialize
        **kwargs: Additional arguments to json.dumps

    Returns:
        JSON string
    """
    defaults = {"ensure_ascii": False, "indent": 2, "default": _json_default_handler}
    defaults.update(kwargs)
    return json.dumps(data, **defaults)


def safe_json_load(json_str: str) -> Any:
    """
    Safely load JSON string with error handling.

    Args:
        json_str: JSON string to parse

    Returns:
        Parsed data or None if parsing fails
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logging.warning(f"Failed to parse JSON: {e}")
        return None


def _json_default_handler(obj: Any) -> Any:
    """Default JSON serialization handler for custom types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, "__dict__"):
        return obj.__dict__
    else:
        return str(obj)


# Path utilities
def ensure_path_exists(path: Union[str, Path], is_file: bool = False) -> Path:
    """
    Ensure a path exists, creating directories if necessary.

    Args:
        path: Path to ensure exists
        is_file: If True, create parent directories for file path

    Returns:
        Path object
    """
    path_obj = Path(path)

    if is_file:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    else:
        path_obj.mkdir(parents=True, exist_ok=True)

    return path_obj


def is_file_readable(path: Union[str, Path]) -> bool:
    """Check if file exists and is readable."""
    path_obj = Path(path)
    return path_obj.exists() and path_obj.is_file() and path_obj.stat().st_size > 0


def get_file_size_mb(path: Union[str, Path]) -> float:
    """Get file size in megabytes."""
    path_obj = Path(path)
    if not path_obj.exists():
        return 0.0
    return path_obj.stat().st_size / (1024 * 1024)


# Math utilities
def round_to_precision(value: float, precision: int = 8) -> float:
    """Round value to specified decimal places."""
    return round(value, precision)


def calculate_percentage(value: float, total: float) -> float:
    """Calculate percentage with zero-division protection."""
    if total == 0:
        return 0.0
    return (value / total) * 100


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max bounds."""
    return max(min_val, min(value, max_val))


def basis_points_to_decimal(bps: float) -> float:
    """Convert basis points to decimal (100 bps = 0.01)."""
    return bps / 10000.0


def decimal_to_basis_points(decimal: float) -> float:
    """Convert decimal to basis points (0.01 = 100 bps)."""
    return decimal * 10000.0


# Logging utilities
def get_logger(
    name: str,
    level: Union[str, int] = logging.INFO,
    extra: Optional[Dict[str, Any]] = None,
    minimal: bool = False,
) -> logging.Logger:
    """
    Get a structured logger with consistent formatting and extra context.

    Args:
        name: Logger name (typically __name__)
        level: Logging level
        extra: Additional context fields to include in all log messages
        minimal: If True, use simplified format (time + message only)

    Returns:
        Configured logger with structured output
    """
    logger = logging.getLogger(name)

    # Set level if not already set
    if logger.level == logging.NOTSET:
        logger.setLevel(level)

    # Add structured formatter if no handlers exist
    if not logger.handlers:
        handler = logging.StreamHandler()

        if minimal:
            # Minimal format: just time and message
            format_str = "%(asctime)s | %(message)s"
        else:
            # Structured format with timestamp, level, module, and message
            format_str = (
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | " "%(message)s"
            )

        if extra:
            # Add extra fields to format
            extra_fields = " | ".join([f"{k}=%(extra_{k})s" for k in extra.keys()])
            format_str = format_str.replace(
                " | %(message)s", f" | {extra_fields} | %(message)s"
            )

        # Use shorter timestamp format
        formatter = logging.Formatter(format_str, datefmt="%H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Store extra context in logger
        if extra:
            logger = logging.LoggerAdapter(
                logger, {"extra_" + k: v for k, v in extra.items()}
            )

    return logger


def setup_logger(
    name: str, level: Union[str, int] = logging.INFO, format_str: Optional[str] = None
) -> logging.Logger:
    """
    Legacy setup_logger function for backward compatibility.

    DEPRECATED: Use get_logger() for new code.
    """
    return get_logger(name, level)


# Dictionary utilities
def deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary
        update: Dictionary to merge into base

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def get_nested_value(data: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get nested dictionary value using dot notation.

    Args:
        data: Dictionary to search
        key_path: Dot-separated key path (e.g., 'config.execution.mode')
        default: Default value if key not found

    Returns:
        Value at key path or default
    """
    keys = key_path.split(".")
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


# Validation utilities
def is_valid_currency_code(code: str) -> bool:
    """Check if string is a valid currency code format."""
    return (
        isinstance(code, str)
        and len(code.strip()) >= 2
        and code.isalpha()
        and code.isupper()
    )


def is_positive_number(value: Any) -> bool:
    """Check if value is a positive number."""
    try:
        return float(value) > 0
    except (ValueError, TypeError):
        return False


def is_valid_percentage(value: Any, allow_zero: bool = True) -> bool:
    """Check if value is a valid percentage (0-100)."""
    try:
        num = float(value)
        return (0 <= num <= 100) if allow_zero else (0 < num <= 100)
    except (ValueError, TypeError):
        return False


def is_valid_basis_points(value: Any) -> bool:
    """Check if value is valid basis points (0-10000)."""
    try:
        return 0 <= float(value) <= 10000
    except (ValueError, TypeError):
        return False


# Performance utilities
def timing_decorator(func):
    """Decorator to measure function execution time."""

    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()

        logger = logging.getLogger(func.__module__)
        logger.debug(f"{func.__name__} executed in {end_time - start_time:.4f}s")
        return result

    return wrapper


def format_profit(decimal_profit):
    """Format a decimal profit value as a percentage string.

    Converts a decimal profit value (e.g., 0.0123) to a formatted
    percentage string with a sign prefix (e.g., "+1.23%").

    Args:
        decimal_profit (float): The profit as a decimal value.
                               Positive values indicate profit,
                               negative values indicate loss.

    Returns:
        str: Formatted percentage string with sign prefix.
             Positive values get '+' prefix, negative values get '-'.

    Examples:
        >>> format_profit(0.0123)
        '+1.23%'
        >>> format_profit(-0.0456)
        '-4.56%'
        >>> format_profit(0.0)
        '+0.00%'
        >>> format_profit(0.10567)
        '+10.57%'
    """
    # Convert decimal to percentage
    percentage = decimal_profit * 100

    # Format with sign prefix
    if percentage >= 0:
        return f"+{percentage:.2f}%"
    else:
        return f"{percentage:.2f}%"
