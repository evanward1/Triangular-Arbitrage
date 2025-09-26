#!/usr/bin/env python3
"""
Quick test to verify monitor_cycles.py --cooldowns works correctly
"""

import tempfile
import shutil
from triangular_arbitrage.risk_controls import RiskControlManager


def test_monitor_cooldowns():
    print("\nTesting monitor cooldowns view...")

    temp_dir = tempfile.mkdtemp()
    state_file = f"{temp_dir}/cooldowns_state.json"

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=300
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")
        manager.slippage_tracker.add_to_cooldown("USDT->BTC->ETH")

        manager.save_cooldowns(state_file)

        print(f"Created state file: {state_file}")
        print(f"Active cooldowns: {len(manager.get_active_cooldowns())}")

        for cycle, remaining in manager.get_active_cooldowns():
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            print(f"  {cycle}: {minutes}m {seconds}s remaining")

        print("\n✓ Test passed - monitor should display these cooldowns")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    test_monitor_cooldowns()
