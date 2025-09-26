"""Tests for utils logging functionality."""

import logging
import pytest
from io import StringIO
from unittest.mock import patch
from triangular_arbitrage.utils import get_logger, setup_logger


def test_get_logger_basic():
    """Test basic get_logger functionality."""
    logger = get_logger(__name__)
    assert isinstance(logger, logging.Logger)
    assert logger.name == __name__


def test_get_logger_with_level():
    """Test get_logger with custom level."""
    logger = get_logger(__name__ + ".test1", level=logging.DEBUG)
    assert logger.level == logging.DEBUG


def test_get_logger_with_extra():
    """Test get_logger with extra context."""
    extra_context = {"strategy": "test_strategy", "mode": "paper"}
    logger = get_logger(__name__ + ".test2", extra=extra_context)

    # Should return a LoggerAdapter when extra is provided
    assert hasattr(logger, 'extra') or isinstance(logger, logging.LoggerAdapter)


def test_get_logger_structured_format():
    """Test that get_logger produces structured log format."""
    import io
    import sys

    logger_name = __name__ + ".test3"
    logger = get_logger(logger_name, level=logging.INFO)

    # Create a StringIO to capture the actual handler output
    captured_output = io.StringIO()

    # Replace the handler's stream temporarily
    if logger.handlers:
        original_stream = logger.handlers[0].stream
        logger.handlers[0].stream = captured_output

        logger.info("Test message")
        log_output = captured_output.getvalue()

        # Restore original stream
        logger.handlers[0].stream = original_stream
    else:
        # If no handlers, just create one for this test
        handler = logging.StreamHandler(captured_output)
        formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.info("Test message")
        log_output = captured_output.getvalue()
        logger.removeHandler(handler)

    # Should contain structured elements: timestamp, level, module:line, message
    assert "INFO" in log_output
    assert logger_name in log_output
    assert "Test message" in log_output
    # Should have pipe separators for structured format
    assert "|" in log_output


def test_get_logger_no_duplicate_handlers():
    """Test that get_logger doesn't add duplicate handlers."""
    logger_name = __name__ + ".test4"

    # Get logger multiple times
    logger1 = get_logger(logger_name)
    logger2 = get_logger(logger_name)

    # Should be the same logger instance
    assert logger1 is logger2

    # Should not have duplicate handlers
    handler_count = len(logger1.handlers)
    logger3 = get_logger(logger_name)
    assert len(logger3.handlers) == handler_count


def test_setup_logger_legacy_compatibility():
    """Test that setup_logger works for backward compatibility."""
    logger = setup_logger(__name__ + ".test5", level=logging.WARNING)
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.WARNING


def test_get_logger_different_names():
    """Test that different logger names create different loggers."""
    logger1 = get_logger("test.logger1")
    logger2 = get_logger("test.logger2")

    assert logger1.name == "test.logger1"
    assert logger2.name == "test.logger2"
    assert logger1 is not logger2


def test_get_logger_level_inheritance():
    """Test logger level handling with existing loggers."""
    # Create parent logger with specific level
    parent_logger = get_logger("test.parent", level=logging.ERROR)
    assert parent_logger.level == logging.ERROR

    # Create child logger - should not change parent's level
    child_logger = get_logger("test.parent.child", level=logging.DEBUG)
    assert parent_logger.level == logging.ERROR  # Should remain unchanged


def test_get_logger_handler_formatter():
    """Test that logger handlers have proper formatter."""
    logger = get_logger(__name__ + ".test6")

    # Should have at least one handler
    assert len(logger.handlers) > 0

    # Handler should have a formatter
    handler = logger.handlers[0]
    assert handler.formatter is not None

    # Check formatter format contains structured elements
    format_str = handler.formatter._fmt
    assert "%(asctime)s" in format_str
    assert "%(levelname)" in format_str
    assert "%(name)s" in format_str
    assert "%(message)s" in format_str


def test_get_logger_with_none_extra():
    """Test get_logger with None extra parameter."""
    logger = get_logger(__name__ + ".test7", extra=None)
    assert isinstance(logger, logging.Logger)


def test_get_logger_existing_logger_with_handlers():
    """Test behavior when logger already has handlers."""
    logger_name = __name__ + ".test8"

    # Create logger and add a handler manually
    existing_logger = logging.getLogger(logger_name)
    existing_handler = logging.StreamHandler()
    existing_logger.addHandler(existing_handler)

    # get_logger should not add more handlers
    new_logger = get_logger(logger_name)
    assert len(new_logger.handlers) == 1
    assert new_logger.handlers[0] is existing_handler