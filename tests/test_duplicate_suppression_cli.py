#!/usr/bin/env python3
"""
CLI smoke test for duplicate suppression feature
"""

import tempfile
import shutil
import time
from triangular_arbitrage.risk_controls import RiskControlManager, RiskControlViolation


def test_suppression_stats_displayed():
    """Test that suppression stats are displayed in get_stats()"""
    print("\nTesting suppression stats display...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir
        )

        cycle_id = "test-cycle-1"
        stop_reason = "latency_exceeded"

        violation = RiskControlViolation(
            timestamp=time.time(),
            cycle_id=cycle_id,
            strategy_name="test_strategy",
            violation_type=stop_reason,
            cycle_path=["BTC", "ETH", "USDT"],
            cycle_direction="forward",
            expected_prices=[1.0, 1.0, 1.0],
            actual_prices=[1.0, 1.0, 1.0],
            latencies_ms=[150, 100, 100],
            slippages_bps=[0, 0, 0],
            threshold_violated={"latency_ms": 150},
            leg_details=[],
            metadata={}
        )

        manager.logger.log_violation(violation, is_executed=False)
        time.sleep(0.1)
        manager.logger.log_violation(violation, is_executed=False)

        stats = manager.get_stats()

        assert 'suppression' in stats
        assert stats['suppression']['total_duplicates_suppressed'] == 1
        assert stats['suppression']['cache_size'] == 1
        assert stats['suppression']['suppression_window_seconds'] == 2.0

        print(f"  ✓ Stats contain suppression section")
        print(f"  ✓ Total duplicates suppressed: {stats['suppression']['total_duplicates_suppressed']}")
        print(f"  ✓ Cache size: {stats['suppression']['cache_size']}")
        print(f"  ✓ Suppression window: {stats['suppression']['suppression_window_seconds']}s")

    finally:
        shutil.rmtree(temp_dir)


def test_no_suppression_when_disabled():
    """Test that suppression can be disabled with window=0"""
    print("\nTesting suppression disabled (window=0)...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=0.0,
            log_dir=temp_dir
        )

        cycle_id = "test-cycle-1"
        stop_reason = "latency_exceeded"

        violation = RiskControlViolation(
            timestamp=time.time(),
            cycle_id=cycle_id,
            strategy_name="test_strategy",
            violation_type=stop_reason,
            cycle_path=["BTC", "ETH", "USDT"],
            cycle_direction="forward",
            expected_prices=[1.0, 1.0, 1.0],
            actual_prices=[1.0, 1.0, 1.0],
            latencies_ms=[150, 100, 100],
            slippages_bps=[0, 0, 0],
            threshold_violated={"latency_ms": 150},
            leg_details=[],
            metadata={}
        )

        manager.logger.log_violation(violation, is_executed=False)
        time.sleep(0.01)
        manager.logger.log_violation(violation, is_executed=False)

        stats = manager.logger.get_suppression_stats()

        assert stats['suppression_window_seconds'] == 0.0
        assert stats['total_duplicates_suppressed'] == 0

        print(f"  ✓ Suppression window set to 0.0")
        print(f"  ✓ No duplicates suppressed (window disabled)")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    print("="*60)
    print("CLI SMOKE TEST: Duplicate Suppression")
    print("="*60)

    test_suppression_stats_displayed()
    test_no_suppression_when_disabled()

    print("\n" + "="*60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("="*60)
    print()