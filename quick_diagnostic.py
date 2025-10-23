#!/usr/bin/env python3
"""
Quick diagnostic to test if fee double-counting is fixed.
Runs a minimal scan and prints diagnostic info.
"""

import logging
import sys

from dex.config import load_config
from dex.runner import DexRunner

# Set up logging to see warnings
logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")


def main():
    print("\n" + "=" * 80)
    print("  QUICK DIAGNOSTIC - Fee Double-Counting Test")
    print("=" * 80 + "\n")

    # Load config
    config = load_config("configs/dex_bsc_dynamic.yaml")

    # Override to scan fewer pools for speed
    if hasattr(config, "dynamic_pools") and config.dynamic_pools:
        config.dynamic_pools["max_scan_pools"] = 100  # Scan only 100 pools
        config.dynamic_pools["max_pools_per_dex"] = 20  # Keep only 20 best per DEX

    # Create runner
    runner = DexRunner(config, quiet=False, use_dynamic_pools=True)

    print("Connecting to RPC...")
    runner.connect()

    print("Building token maps...")
    runner.build_token_maps()

    print("Fetching pools (limited to 100 scanned, 20 per DEX for speed)...")
    runner.fetch_pools()

    print(f"\nFound {len(runner.pools)} pools\n")

    # Print banner (includes fee audit)
    runner.print_banner()

    # Run one scan
    print("\nRunning single scan...\n")
    import asyncio

    rows = asyncio.run(runner.scan_async())

    # Print results
    runner.print_results(rows, scan_num=1)

    print("\n" + "=" * 80)
    print("  DIAGNOSTIC COMPLETE")
    print("=" * 80)
    print("\nLook for warnings above:")
    print("  - '⚠ ACCOUNTING BUG DETECTED' means fees are still being double-counted")
    print("  - '⚠ DISPLAY MISMATCH' means hidden costs in the calculation")
    print("\nIf no warnings appeared, the fix worked! ✓")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
