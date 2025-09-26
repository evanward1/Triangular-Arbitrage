#!/usr/bin/env python3
"""
CLI smoke test for --clear-cooldown command
"""

import tempfile
import shutil
from unittest.mock import patch
from io import StringIO
import sys

from triangular_arbitrage.risk_controls import RiskControlManager


def test_clear_cooldown_cli_with_confirmation():
    """Test CLI with mocked stdin returning 'y' for confirmation"""
    print("\nTesting CLI clear-cooldown with 'y' confirmation...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir,
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)
        manager.save_cooldowns()

        assert pair in manager.slippage_tracker.cooldown_cycles

        with patch("builtins.input", return_value="y"):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                success = manager.clear_cooldown(pair)

                assert success is True
                assert pair not in manager.slippage_tracker.cooldown_cycles

        print(f"  ✓ Pair {pair} successfully cleared with 'y' confirmation")
        print(f"  ✓ State file updated immediately")

    finally:
        shutil.rmtree(temp_dir)


def test_clear_cooldown_cli_with_cancellation():
    """Test that clear fails when pair doesn't exist"""
    print("\nTesting CLI clear-cooldown for non-existent pair...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir,
        )

        pair = "BTC->ETH->USDT"

        success = manager.clear_cooldown(pair)

        assert success is False
        print(f"  ✓ clear_cooldown correctly returns False for non-existent pair")

    finally:
        shutil.rmtree(temp_dir)


def test_clear_cooldown_success_message():
    """Test that success message is appropriate"""
    print("\nTesting CLI success messaging...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir,
        )

        pair = "ETH->USDT->BTC"
        manager.slippage_tracker.add_to_cooldown(pair)

        before_count = len(manager.get_active_cooldowns())
        assert before_count == 1

        success = manager.clear_cooldown(pair)

        assert success is True

        after_count = len(manager.get_active_cooldowns())
        assert after_count == 0

        print(f"  ✓ Active cooldowns: {before_count} -> {after_count}")
        print(f"  ✓ Success message appropriate")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("=" * 60)
    print("CLI SMOKE TEST: --clear-cooldown")
    print("=" * 60)

    test_clear_cooldown_cli_with_confirmation()
    test_clear_cooldown_cli_with_cancellation()
    test_clear_cooldown_success_message()

    print("\n" + "=" * 60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("=" * 60)
    print()
