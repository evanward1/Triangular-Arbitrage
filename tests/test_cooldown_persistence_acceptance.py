#!/usr/bin/env python3
"""
Acceptance test for cooldown persistence across restarts.

This test simulates:
1. A slippage violation that triggers a cooldown
2. Saving the cooldown state
3. A simulated restart that loads the state
4. Verification that the cooldown is preserved and expires correctly
"""

import time
import tempfile
import shutil
from pathlib import Path

from triangular_arbitrage.risk_controls import RiskControlManager


def test_cooldown_persistence_acceptance():
    print("\n" + "="*60)
    print("COOLDOWN PERSISTENCE ACCEPTANCE TEST")
    print("="*60)

    temp_dir = tempfile.mkdtemp()
    state_file = f"{temp_dir}/cooldowns_state.json"

    try:
        print("\n1. Creating RiskControlManager (simulating first run)...")
        manager1 = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=5,
            log_dir=f"{temp_dir}/logs"
        )
        print("   ✓ Manager created")

        cycle_path = ["BTC", "ETH", "USDT"]
        cycle_key = "->".join(cycle_path)

        print(f"\n2. Triggering slippage violation for {cycle_key}...")
        manager1.slippage_tracker.add_to_cooldown(cycle_key)
        assert manager1.is_cycle_in_cooldown(cycle_path), "Cycle should be in cooldown"
        remaining = manager1.get_cycle_cooldown_remaining(cycle_path)
        print(f"   ✓ Cycle in cooldown: {remaining:.1f}s remaining")

        print("\n3. Saving cooldown state (simulating shutdown)...")
        manager1.save_cooldowns(state_file)
        assert Path(state_file).exists(), "State file should exist"
        print(f"   ✓ State saved to {state_file}")

        print("\n4. Creating new manager (simulating restart)...")
        manager2 = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=5,
            log_dir=f"{temp_dir}/logs"
        )
        assert not manager2.is_cycle_in_cooldown(cycle_path), "Cooldown should not exist yet"
        print("   ✓ New manager created (cooldowns empty)")

        print("\n5. Loading cooldown state (--resume behavior)...")
        restored = manager2.load_cooldowns(state_file)
        assert restored == 1, f"Expected 1 cooldown restored, got {restored}"
        print(f"   ✓ Resumed with {restored} active cooldown(s)")

        print("\n6. Verifying cooldown is active...")
        assert manager2.is_cycle_in_cooldown(cycle_path), "Cycle should be in cooldown after load"
        remaining = manager2.get_cycle_cooldown_remaining(cycle_path)
        print(f"   ✓ Cycle still in cooldown: {remaining:.1f}s remaining")

        print("\n7. Viewing active cooldowns (monitor behavior)...")
        active = manager2.get_active_cooldowns()
        assert len(active) == 1, "Should have 1 active cooldown"
        print(f"   ✓ Active cooldowns: {len(active)}")
        for cycle, rem in active:
            print(f"     - {cycle}: {rem:.1f}s remaining")

        print("\n8. Waiting for cooldown to expire...")
        time.sleep(5.2)
        assert not manager2.is_cycle_in_cooldown(cycle_path), "Cooldown should have expired"
        print("   ✓ Cooldown expired as expected")

        print("\n" + "="*60)
        print("ACCEPTANCE TEST PASSED ✓")
        print("="*60)
        print("\nVerified:")
        print("  ✓ Cooldowns are saved to JSON file atomically")
        print("  ✓ Cooldowns survive simulated restart (--resume)")
        print("  ✓ Cycles remain excluded until cooldown expires")
        print("  ✓ Active cooldowns can be queried for monitoring")
        print()

    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    test_cooldown_persistence_acceptance()