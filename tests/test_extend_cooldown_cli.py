#!/usr/bin/env python3
"""
CLI smoke test for --extend-cooldown and --shorten-cooldown commands
"""

import tempfile
import shutil
from unittest.mock import patch
from io import StringIO

from triangular_arbitrage.risk_controls import RiskControlManager


def test_extend_cooldown_cli():
    """Test --extend-cooldown with mocked confirmation"""
    print("\nTesting --extend-cooldown CLI...")

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

        remaining_before = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])

        with patch("builtins.input", return_value="y"):
            success = manager.extend_cooldown(pair, 60)

        assert success is True

        remaining_after = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])
        assert remaining_after > remaining_before

        print(
            f"  ✓ Extended cooldown by 60s: {remaining_before:.1f}s → {remaining_after:.1f}s"
        )

    finally:
        shutil.rmtree(temp_dir)


def test_shorten_cooldown_cli():
    """Test --shorten-cooldown (extend with negative seconds)"""
    print("\nTesting --shorten-cooldown CLI...")

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
        manager.save_cooldowns()

        remaining_before = manager.get_cycle_cooldown_remaining(["ETH", "USDT", "BTC"])

        with patch("builtins.input", return_value="y"):
            success = manager.extend_cooldown(pair, -30)

        assert success is True

        remaining_after = manager.get_cycle_cooldown_remaining(["ETH", "USDT", "BTC"])
        assert remaining_after < remaining_before

        print(
            f"  ✓ Shortened cooldown by 30s: {remaining_before:.1f}s → {remaining_after:.1f}s"
        )

    finally:
        shutil.rmtree(temp_dir)


def test_extend_cooldown_clamping():
    """Test that extreme shortening clamps to minimum"""
    print("\nTesting clamping behavior...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_dir,
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)

        success = manager.extend_cooldown(pair, -1000)

        assert success is True

        remaining = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])
        assert 0.9 <= remaining <= 2.0

        print(f"  ✓ Extreme shorten (-1000s) clamped to minimum: {remaining:.1f}s")

    finally:
        shutil.rmtree(temp_dir)


def test_extend_not_found():
    """Test extend on non-existent cooldown"""
    print("\nTesting extend on non-existent cooldown...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir,
        )

        success = manager.extend_cooldown("NONEXISTENT", 60)

        assert success is False

        print(f"  ✓ Returns False for non-existent pair")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("=" * 60)
    print("CLI SMOKE TEST: --extend/shorten-cooldown")
    print("=" * 60)

    test_extend_cooldown_cli()
    test_shorten_cooldown_cli()
    test_extend_cooldown_clamping()
    test_extend_not_found()

    print("\n" + "=" * 60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("=" * 60)
    print()
