#!/usr/bin/env python3
"""
Run DEX arbitrage scanner with execution capability.

This script extends the paper trading scanner to actually execute profitable opportunities.

MODES:
  1. Paper Trading (default): Scan only, no execution
  2. Dry Run: Simulate execution (logs what would happen)
  3. Live: Execute real transactions (REQUIRES PRIVATE KEY)

SAFETY:
  - Dry run mode is enabled by default
  - Private key must be explicitly provided via env var
  - Min profit threshold enforced
  - Rate limiting prevents spam execution

Usage:
  # Paper trading (no execution)
  python run_dex_with_execution.py --config configs/dex_bsc_dynamic.yaml

  # Dry run (simulate execution)
  python run_dex_with_execution.py --config configs/dex_bsc_dynamic.yaml --dry-run

  # Live execution (DANGEROUS - requires private key)
  export DEX_PRIVATE_KEY="0x..."
  python run_dex_with_execution.py --config configs/dex_bsc_dynamic.yaml --live

Environment Variables:
  DEX_PRIVATE_KEY: Private key for signing transactions (required for --live)
  DEX_MAX_GAS_GWEI: Maximum gas price in gwei (default: 10)
  DEX_MIN_PROFIT_USD: Minimum profit to execute in USD (default: 5.0)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dex.config import load_config  # noqa: E402
from dex.execution_wrapper import ExecutionEnabledRunner  # noqa: E402
from dex.executor import ExecutionConfig  # noqa: E402
from triangular_arbitrage.utils import get_logger  # noqa: E402

logger = get_logger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="DEX Arbitrage Scanner with Execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to DEX config YAML file",
    )

    # Execution mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--paper",
        action="store_true",
        help="Paper trading mode (scan only, no execution) [DEFAULT]",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (simulate execution, no real transactions)",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Live mode (execute real transactions - REQUIRES DEX_PRIVATE_KEY)",
    )

    # Execution settings
    parser.add_argument(
        "--auto-execute",
        action="store_true",
        help="Automatically execute profitable opportunities (default: False)",
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=None,
        help="Minimum profit in USD to execute (default: from config or 5.0)",
    )
    parser.add_argument(
        "--max-gas",
        type=float,
        default=None,
        help="Maximum gas price in gwei (default: from env or 10.0)",
    )

    # Other options
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode (less output)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for testing)",
    )
    parser.add_argument(
        "--max-pools",
        type=int,
        help="Limit pools per DEX (for faster scanning)",
    )

    return parser.parse_args()


def get_execution_config(args) -> ExecutionConfig:
    """
    Build execution configuration from args and environment.

    Args:
        args: Parsed command line arguments

    Returns:
        ExecutionConfig instance
    """
    # Determine mode
    if args.live:
        dry_run = False
        mode_name = "LIVE"
    elif args.dry_run:
        dry_run = True
        mode_name = "DRY RUN"
    else:  # paper (default)
        dry_run = True
        mode_name = "PAPER"

    # Get private key from environment
    private_key = os.getenv("DEX_PRIVATE_KEY")

    if args.live and not private_key:
        logger.error("LIVE mode requires DEX_PRIVATE_KEY environment variable")
        logger.error("Set it with: export DEX_PRIVATE_KEY='0x...'")
        sys.exit(1)

    # Get execution parameters from env or args
    max_gas_gwei = args.max_gas or float(os.getenv("DEX_MAX_GAS_GWEI", "10.0"))
    min_profit_usd = args.min_profit or float(os.getenv("DEX_MIN_PROFIT_USD", "5.0"))

    # Build config
    config = ExecutionConfig(
        private_key=private_key,
        max_gas_price_gwei=max_gas_gwei,
        max_priority_fee_gwei=2.0,
        use_flashbots=True,  # Always use MEV protection if available
        dry_run_mode=dry_run,
        min_profit_threshold_usd=min_profit_usd,
        max_slippage_pct=1.0,
    )

    logger.info(f"Execution Mode: {mode_name}")
    if not dry_run and private_key:
        # Show first/last 4 chars of key for verification
        key_preview = f"{private_key[:6]}...{private_key[-4:]}"
        logger.info(f"Private Key: {key_preview}")
    logger.info(f"Min Profit: ${min_profit_usd:.2f}")
    logger.info(f"Max Gas: {max_gas_gwei:.1f} gwei")
    logger.info(f"Auto-Execute: {args.auto_execute}")

    return config


async def main():
    """Main entry point."""
    args = parse_args()

    try:
        # Load DEX config
        logger.info(f"Loading config from {args.config}...")
        config = load_config(args.config)

        # Override once flag if specified
        if args.once:
            config.once = True

        # Build execution config
        exec_config = get_execution_config(args)

        # Initialize runner with execution capability
        runner = ExecutionEnabledRunner(
            config=config,
            execution_config=exec_config,
            auto_execute=args.auto_execute,
            quiet=args.quiet,
        )

        # Connect to RPC
        logger.info("Connecting to RPC...")
        runner.connect()

        # Build token maps
        runner.build_token_maps()

        # Fetch pools
        logger.info("Fetching pools...")
        runner.fetch_pools(max_pools_per_dex=args.max_pools)

        # Run scanner with execution
        logger.info("Starting scanner with execution capability...\n")

        if args.auto_execute:
            # Run with auto-execution
            await runner.run_with_execution_async()
        else:
            # Run normal scanner (manual execution only)
            await runner.run_async()

    except KeyboardInterrupt:
        logger.info("\n\nShutdown requested by user")

        # Print execution summary
        if hasattr(runner, "print_execution_summary"):
            runner.print_execution_summary()

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
