#!/usr/bin/env python3
"""
Run DEX MEV arbitrage paper trading scan.
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from triangular_arbitrage.dex_mev.executor import ArbitrageExecutor  # noqa: E402


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    """Main function to run DEX paper trading."""
    setup_logging()

    # Check if config exists
    config_path = "configs/dex_mev.example.yaml"
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        print("Please create the config file first")
        sys.exit(1)

    try:
        # Create executor and run paper trading
        executor = ArbitrageExecutor(config_path)
        executor.run_paper(max_opportunities=5)

    except Exception as e:
        logging.error(f"Failed to run DEX paper trading: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
