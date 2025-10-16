"""
Logging configuration for cleaner output.

Usage:
    import logging_config
    logging_config.setup()
"""

import logging
import sys


def setup(level=logging.INFO):
    """
    Configure logging for cleaner, more readable output.

    - Suppresses verbose HTTP request logs from uvicorn
    - Uses shorter timestamp format (HH:MM:SS instead of full datetime)
    - Consolidates duplicate messages
    """

    # Root logger - minimal format
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    root.handlers.clear()

    # Create console handler with clean format
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)

    # Minimal format: time + level + message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"
    )
    console.setFormatter(formatter)
    root.addHandler(console)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Hide HTTP requests
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)  # Keep errors
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    # Keep application loggers at INFO
    logging.getLogger("__main__").setLevel(logging.INFO)
    logging.getLogger("dex.runner").setLevel(logging.INFO)
    logging.getLogger("triangular_arbitrage").setLevel(logging.INFO)


def setup_minimal():
    """
    Even more minimal logging - only warnings and errors.
    Good for production or when you only care about problems.
    """
    setup(level=logging.WARNING)


def setup_debug():
    """
    Verbose logging for debugging.
    Shows everything including HTTP requests.
    """
    setup(level=logging.DEBUG)
    logging.getLogger("uvicorn.access").setLevel(
        logging.INFO
    )  # Show HTTP in debug mode
