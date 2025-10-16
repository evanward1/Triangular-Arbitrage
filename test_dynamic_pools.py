#!/usr/bin/env python3
"""
Test script for dynamic pool discovery.

Tests the new pool factory scanner with live blockchain data.
"""

import logging
import sys

from dex.config import load_config
from dex.runner import DexRunner

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def test_dynamic_pool_discovery():
    """Test dynamic pool discovery with live blockchain data."""

    logger.info("=" * 80)
    logger.info("Testing Dynamic Pool Discovery")
    logger.info("=" * 80)

    try:
        # Load dynamic config
        config_path = "configs/dex_mev_eth_dynamic.yaml"
        logger.info(f"Loading config: {config_path}")
        config = load_config(config_path)

        # Verify dynamic pools are enabled
        if not config.dynamic_pools or not config.dynamic_pools.get("enabled"):
            logger.error("Dynamic pools not enabled in config!")
            return False

        logger.info("✓ Dynamic pools enabled")
        logger.info(
            f"  Min liquidity: ${config.dynamic_pools['min_liquidity_usd']:,.0f}"
        )
        logger.info(
            f"  Max pools per DEX: {config.dynamic_pools.get('max_pools_per_dex', 'unlimited')}"
        )
        logger.info(f"  Factories: {len(config.dynamic_pools['factories'])}")

        for factory in config.dynamic_pools["factories"]:
            logger.info(f"    - {factory['name']} ({factory['address']})")

        # Initialize runner with dynamic pools enabled
        logger.info("\nInitializing DexRunner with dynamic pool discovery...")
        runner = DexRunner(config, quiet=False, use_dynamic_pools=True)

        # Connect to RPC
        logger.info("\nConnecting to RPC...")
        runner.connect()
        logger.info("✓ Connected to blockchain")

        # Build token maps (only need USD token now - others discovered dynamically)
        runner.build_token_maps()
        logger.info(
            f"✓ Loaded {len(config.tokens)} base tokens (others auto-discovered)"
        )

        # Fetch pools dynamically
        logger.info("\n" + "=" * 80)
        logger.info("Starting dynamic pool discovery...")
        logger.info("This may take 1-2 minutes to scan factory contracts...")
        logger.info("=" * 80 + "\n")

        runner.fetch_pools()

        # Print results
        logger.info("\n" + "=" * 80)
        logger.info("Discovery Results")
        logger.info("=" * 80)
        logger.info(f"Total pools discovered: {len(runner.pools)}")

        # Group by DEX
        dex_counts = {}
        for pool in runner.pools:
            dex_counts[pool.dex] = dex_counts.get(pool.dex, 0) + 1

        logger.info("\nPools by DEX:")
        for dex, count in sorted(dex_counts.items()):
            logger.info(f"  {dex}: {count} pools")

        # Show token pairs
        pairs = set()
        for pool in runner.pools:
            pairs.add(f"{pool.base_symbol}/{pool.quote_symbol}")

        logger.info(f"\nUnique trading pairs: {len(pairs)}")
        logger.info("\nTop 20 pairs by frequency:")
        pair_counts = {}
        for pool in runner.pools:
            pair = f"{pool.base_symbol}/{pool.quote_symbol}"
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

        for pair, count in sorted(
            pair_counts.items(), key=lambda x: x[1], reverse=True
        )[:20]:
            logger.info(f"  {pair}: {count} pools")

        # Calculate potential routes
        logger.info("\n" + "=" * 80)
        logger.info("Arbitrage Route Calculation")
        logger.info("=" * 80)

        # Count cross-DEX opportunities
        pair_groups = {}
        for pool in runner.pools:
            key = (pool.base_symbol, pool.quote_symbol)
            pair_groups.setdefault(key, []).append(pool)

        cross_dex_pairs = {
            pair: pools for pair, pools in pair_groups.items() if len(pools) >= 2
        }

        total_routes = sum(
            len(pools) * (len(pools) - 1)  # Each pool pair creates 2 routes
            for pools in cross_dex_pairs.values()
        )

        logger.info(f"Pairs with multiple DEXes: {len(cross_dex_pairs)}")
        logger.info(f"Potential arbitrage routes: {total_routes}")
        logger.info(f"\nComparison:")
        logger.info(f"  Old static config: 2 hardcoded pools → 2 routes")
        logger.info(
            f"  New dynamic discovery: {len(runner.pools)} pools → {total_routes} routes"
        )
        if total_routes > 0:
            logger.info("  Improvement: %.0fx more routes!", total_routes / 2)
        else:
            logger.info("  Note: No cross-DEX pairs found yet")

        # Show sample of discovered pools
        logger.info("\n" + "=" * 80)
        logger.info("Sample of Discovered Pools (first 10)")
        logger.info("=" * 80)

        for i, pool in enumerate(runner.pools[:10], 1):
            logger.info(
                f"{i:2d}. {pool.pair_name:15s} on {pool.dex:15s} "
                f"(r0={float(pool.r0):,.0f}, r1={float(pool.r1):,.0f})"
            )

        if len(runner.pools) > 10:
            logger.info(f"    ... and {len(runner.pools) - 10} more pools")

        logger.info("\n" + "=" * 80)
        logger.info("✓ Dynamic pool discovery test PASSED!")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"\n✗ Test FAILED: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_dynamic_pool_discovery()
    sys.exit(0 if success else 1)
