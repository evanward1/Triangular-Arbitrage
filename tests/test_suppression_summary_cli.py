#!/usr/bin/env python3
"""
CLI smoke test for --suppression-summary
"""

import tempfile
import shutil
import time
from triangular_arbitrage.risk_controls import RiskControlManager, RiskControlViolation


def test_suppression_summary_with_events():
    """Test --suppression-summary with suppressed events"""
    print("\nTesting --suppression-summary with events...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir,
        )

        cycles = [
            ("BTC->ETH->USDT", "latency_exceeded", 5),
            ("ETH->USDT->BTC", "slippage_exceeded", 3),
        ]

        for cycle_id, reason, dup_count in cycles:
            for i in range(dup_count + 1):
                violation = RiskControlViolation(
                    timestamp=time.time(),
                    cycle_id=cycle_id,
                    strategy_name="test_strategy",
                    violation_type=reason,
                    cycle_path=cycle_id.split("->"),
                    cycle_direction="forward",
                    expected_prices=[1.0, 1.0, 1.0],
                    actual_prices=[1.0, 1.0, 1.0],
                    latencies_ms=[150, 100, 100],
                    slippages_bps=[0, 0, 0],
                    threshold_violated={},
                    leg_details=[],
                    metadata={},
                )
                manager.logger.log_violation(violation, is_executed=False)
                time.sleep(0.01)

        summary = manager.logger.get_suppression_summary(window_seconds=60)

        assert summary["total_suppressed"] == 8
        assert summary["unique_pairs"] == 2
        assert summary["suppression_rate"] > 0
        assert len(summary["top_pairs"]) == 2
        assert summary["top_pairs"][0]["cycle_id"] == "BTC->ETH->USDT"

        print(f"  ✓ Total suppressed: {summary['total_suppressed']}")
        print(f"  ✓ Unique pairs: {summary['unique_pairs']}")
        print(f"  ✓ Suppression rate: {summary['suppression_rate']:.2f}%")
        print(f"  ✓ Top pair: {summary['top_pairs'][0]['cycle_id']}")

    finally:
        shutil.rmtree(temp_dir)


def test_suppression_summary_empty():
    """Test --suppression-summary with no events"""
    print("\nTesting --suppression-summary when empty...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir,
        )

        summary = manager.logger.get_suppression_summary(window_seconds=300)

        assert summary["total_suppressed"] == 0
        assert summary["unique_pairs"] == 0
        assert summary["suppression_rate"] == 0.0
        assert summary["top_pairs"] == []

        print(f"  ✓ Returns empty summary when no events")

    finally:
        shutil.rmtree(temp_dir)


def test_suppression_summary_window_filtering():
    """Test --suppression-summary filters by window"""
    print("\nTesting --suppression-summary window filtering...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir,
        )

        old_time = time.time() - 400
        manager.logger._suppressed_history.append(
            {
                "cycle_id": "OLD->CYCLE",
                "stop_reason": "latency_exceeded",
                "first_seen": old_time,
                "last_seen": old_time,
                "duplicate_count": 10,
            }
        )

        for i in range(3):
            violation = RiskControlViolation(
                timestamp=time.time(),
                cycle_id="NEW->CYCLE",
                strategy_name="test_strategy",
                violation_type="latency_exceeded",
                cycle_path=["NEW", "CYCLE"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0],
                actual_prices=[1.0, 1.0],
                latencies_ms=[150, 100],
                slippages_bps=[0, 0],
                threshold_violated={},
                leg_details=[],
                metadata={},
            )
            manager.logger.log_violation(violation, is_executed=False)
            time.sleep(0.01)

        summary = manager.logger.get_suppression_summary(window_seconds=300)

        assert summary["total_suppressed"] == 2
        assert summary["unique_pairs"] == 1
        assert summary["top_pairs"][0]["cycle_id"] == "NEW->CYCLE"

        print(f"  ✓ Excludes old events (> {summary['window_seconds']}s)")
        print(f"  ✓ Only counts recent events: {summary['total_suppressed']}")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("=" * 60)
    print("CLI SMOKE TEST: --suppression-summary")
    print("=" * 60)

    test_suppression_summary_with_events()
    test_suppression_summary_empty()
    test_suppression_summary_window_filtering()

    print("\n" + "=" * 60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("=" * 60)
    print()
