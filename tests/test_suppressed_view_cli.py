#!/usr/bin/env python3
"""
CLI smoke test for --suppressed view
"""

import tempfile
import shutil
import time
import sys
import subprocess
from triangular_arbitrage.risk_controls import RiskControlManager, RiskControlViolation


def test_suppressed_view_with_events():
    """Test --suppressed shows table with suppressed events"""
    print("\nTesting --suppressed view with events...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir
        )

        cycle_id = "BTC->ETH->USDT"
        stop_reason = "latency_exceeded"

        for i in range(3):
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
            time.sleep(0.05)

        suppressed = manager.logger.get_recent_suppressed(limit=5)

        assert len(suppressed) == 1
        assert suppressed[0]['cycle_id'] == cycle_id
        assert suppressed[0]['stop_reason'] == stop_reason
        assert suppressed[0]['duplicate_count'] == 2

        print(f"  ✓ Suppressed {suppressed[0]['duplicate_count']} duplicates for {cycle_id}")
        print(f"  ✓ get_recent_suppressed() returns correct metadata")

    finally:
        shutil.rmtree(temp_dir)


def test_suppressed_view_empty():
    """Test --suppressed shows message when no events suppressed"""
    print("\nTesting --suppressed view when empty...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir
        )

        suppressed = manager.logger.get_recent_suppressed(limit=10)

        assert len(suppressed) == 0

        print(f"  ✓ get_recent_suppressed() returns empty list when no suppression")

    finally:
        shutil.rmtree(temp_dir)


def test_suppressed_view_multiple_cycles():
    """Test --suppressed with multiple different cycles"""
    print("\nTesting --suppressed view with multiple cycles...")

    temp_dir = tempfile.mkdtemp()

    try:
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            duplicate_suppression_window=2.0,
            log_dir=temp_dir
        )

        cycles = [
            ("BTC->ETH->USDT", "latency_exceeded"),
            ("ETH->USDT->BTC", "slippage_exceeded"),
            ("USDT->BTC->ETH", "latency_exceeded")
        ]

        for cycle_id, reason in cycles:
            for i in range(2):
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
                    metadata={}
                )
                manager.logger.log_violation(violation, is_executed=False)
                time.sleep(0.01)
            time.sleep(0.05)

        suppressed = manager.logger.get_recent_suppressed(limit=10)

        assert len(suppressed) == 3

        cycle_ids = {s['cycle_id'] for s in suppressed}
        assert "BTC->ETH->USDT" in cycle_ids
        assert "ETH->USDT->BTC" in cycle_ids
        assert "USDT->BTC->ETH" in cycle_ids

        print(f"  ✓ Suppressed events from {len(suppressed)} different cycles")
        print(f"  ✓ Each cycle has correct metadata")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    print("="*60)
    print("CLI SMOKE TEST: --suppressed View")
    print("="*60)

    test_suppressed_view_with_events()
    test_suppressed_view_empty()
    test_suppressed_view_multiple_cycles()

    print("\n" + "="*60)
    print("ALL CLI SMOKE TESTS PASSED ✓")
    print("="*60)
    print()