#!/usr/bin/env python3
"""Quick test of cross-DEX pair filtering logic."""

import asyncio
import sys
from decimal import Decimal

from web3 import Web3

from dex.config import load_config
from dex.runner import DexRunner
from triangular_arbitrage.utils import get_logger

logger = get_logger(__name__)


async def main():
    """Test cross-DEX filtering with limited pool scan."""
    config_path = "configs/dex_bsc_dynamic.yaml"

    logger.info(f"Loading config from {config_path}")
    config = load_config(config_path)

    # Override to scan fewer pools for faster testing
    if hasattr(config, "dynamic_pools") and config.dynamic_pools:
        config.dynamic_pools["max_scan_pools"] = 500  # Only scan 500 pools total
        config.dynamic_pools["max_pools_per_dex"] = 100  # Keep top 100 per DEX

    runner = DexRunner(config, quiet=False)

    logger.info("Connecting to RPC...")
    runner.connect()

    logger.info("Building token maps...")
    runner.build_token_maps()

    logger.info("Fetching pools with cross-DEX filtering...")
    runner.fetch_pools()

    if runner.pools:
        logger.info("\n✓ SUCCESS: Found %d pools after cross-DEX filtering", len(runner.pools))

        # Show sample of pools
        logger.info("\nSample pools (first 10):")
        for i, pool in enumerate(runner.pools[:10], 1):
            logger.info(f"  {i}. {pool.dex}: {pool.base_symbol}/{pool.quote_symbol}")

        # Group by pair to show cross-DEX coverage
        from collections import defaultdict

        pair_dexes = defaultdict(set)
        for pool in runner.pools:
            tokens = tuple(sorted([pool.base_symbol, pool.quote_symbol]))
            pair_dexes[tokens].add(pool.dex)

        logger.info("\nCross-DEX pair coverage:")
        for pair, dexes in sorted(
            pair_dexes.items(), key=lambda x: len(x[1]), reverse=True
        )[:10]:
            logger.info(
                f"  {pair[0]}/{pair[1]}: {', '.join(sorted(dexes))} ({len(dexes)} DEXes)"
            )

        return 0
    else:
        logger.error("\n✗ FAILURE: No pools found after filtering!")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
