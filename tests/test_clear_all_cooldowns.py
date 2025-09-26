#!/usr/bin/env python3
"""
CLI smoke test for --clear-all-cooldowns command
"""

import tempfile
import shutil
from unittest.mock import patch

from triangular_arbitrage.risk_controls import RiskControlManager


def test_clear_all_cooldowns_with_confirmation():
    """Test --clear-all-cooldowns with 'y' confirmation"""
    print("\nTesting --clear-all-cooldowns with 'y' confirmation...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")
        manager.slippage_tracker.add_to_cooldown("USDT->BTC->ETH")
        manager.save_cooldowns()

        assert len(manager.slippage_tracker.cooldown_cycles) == 3

        with patch('builtins.input', return_value='y'):
            count = manager.clear_all_cooldowns()

        assert count == 3
        assert len(manager.slippage_tracker.cooldown_cycles) == 0

        active = manager.get_active_cooldowns()
        assert len(active) == 0

        print(f"  ✓ Cleared {count} cooldowns with 'y' confirmation")
        print(f"  ✓ Active cooldowns now: {len(active)}")

    finally:
        shutil.rmtree(temp_dir)


def test_clear_all_cooldowns_when_empty():
    """Test --clear-all-cooldowns when no cooldowns exist"""
    print("\nTesting --clear-all-cooldowns when empty...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir
        )

        count = manager.clear_all_cooldowns()

        assert count == 0

        print(f"  ✓ Returns 0 when no cooldowns exist")

    finally:
        shutil.rmtree(temp_dir)


def test_clear_all_updates_state_file():
    """Test that state file is emptied after clear_all"""
    print("\nTesting state file persistence...")

    temp_dir = tempfile.mkdtemp()
    state_file = f"{temp_dir}/cooldowns_state.json"

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_dir
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")
        manager.save_cooldowns()

        import json
        with open(state_file, 'r') as f:
            data_before = json.load(f)
        assert len(data_before) == 2

        manager.clear_all_cooldowns()

        with open(state_file, 'r') as f:
            data_after = json.load(f)
        assert len(data_after) == 0

        print(f"  ✓ State file before: {len(data_before)} cooldowns")
        print(f"  ✓ State file after: {len(data_after)} cooldowns")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    print("="*60)
    print("CLI SMOKE TEST: --clear-all-cooldowns")
    print("="*60)

    test_clear_all_cooldowns_with_confirmation()
    test_clear_all_cooldowns_when_empty()
    test_clear_all_updates_state_file()

    print("\n" + "="*60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("="*60)
    print()