#!/usr/bin/env python3
"""
DEX arbitrage paper trading CLI.

Scans for cross-DEX arbitrage opportunities and prints results
in a console-friendly format.

Usage:
    python3 run_dex_paper.py
    python3 run_dex_paper.py --config configs/dex_mev.yaml
    python3 run_dex_paper.py --config configs/dex_mev.yaml --once
"""

import argparse
import sys
from pathlib import Path

from dex.config import ConfigError, load_config
from dex.runner import DexRunner

# Add repo root to path for imports
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="DEX arbitrage paper trading scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config
  python3 run_dex_paper.py

  # Use custom config
  python3 run_dex_paper.py --config configs/dex_mev.yaml

  # Single scan (for testing/CI)
  python3 run_dex_paper.py --config configs/dex_mev.yaml --once
        """,
    )

    parser.add_argument(
        "--config",
        default="configs/dex_mev_eth_test.yaml",
        help="Path to config YAML file (default: configs/dex_mev_eth_test.yaml)",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit (overrides config setting)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as e:
        print(f"❌ Config error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error loading config: {e}", file=sys.stderr)
        return 1

    # Override once setting if CLI flag set
    if args.once:
        config.once = True

    # Initialize runner
    try:
        runner = DexRunner(config)
        runner.connect()
        runner.build_token_maps()
        runner.fetch_pools()
    except Exception as e:
        print(f"❌ Initialization failed: {e}", file=sys.stderr)
        return 1

    # Run scanner
    try:
        runner.run()
    except KeyboardInterrupt:
        print("\n\n⏸ Stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Runner failed: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
