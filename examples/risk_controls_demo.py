#!/usr/bin/env python3
"""
Risk Controls Demonstration Script

This script demonstrates the risk control features:
1. Latency monitoring and violation detection
2. Slippage tracking and cooldown mechanism
3. Structured logging to console and JSON
"""

import time
import asyncio
from triangular_arbitrage.risk_controls import RiskControlManager


async def demo_latency_violation():
    print("\n" + "=" * 60)
    print("DEMO 1: Latency Violation Detection")
    print("=" * 60)

    manager = RiskControlManager(
        max_leg_latency_ms=50,
        max_slippage_bps=100,
        slippage_cooldown_seconds=5,
        log_dir="logs/risk_controls_demo"
    )

    print("\nSimulating a trade leg with excessive latency...")
    print("Max allowed latency: 50ms")

    start_time = manager.start_leg_timing()
    await asyncio.sleep(0.1)

    measurement, violated = manager.end_leg_timing(
        leg_index=0,
        market_symbol="BTC/USDT",
        start_time=start_time,
        side="buy"
    )

    print(f"Measured latency: {measurement.latency_ms:.2f}ms")
    print(f"Violation detected: {violated}")

    if violated:
        print("\nLogging latency violation...")
        manager.log_latency_violation(
            cycle_id="demo_cycle_001",
            strategy_name="demo_strategy",
            cycle_path=["BTC", "ETH", "USDT"],
            cycle_direction="->",
            violated_leg=measurement
        )
        print("✓ Violation logged to console and JSON file")


async def demo_slippage_violation():
    print("\n" + "=" * 60)
    print("DEMO 2: Slippage Violation and Cooldown")
    print("=" * 60)

    manager = RiskControlManager(
        max_leg_latency_ms=1000,
        max_slippage_bps=50,
        slippage_cooldown_seconds=5,
        log_dir="logs/risk_controls_demo"
    )

    print("\nSimulating a trade with excessive slippage...")
    print("Expected price: 100.00")
    print("Executed price: 102.00")
    print("Max allowed slippage: 50 bps")

    measurement, violated = manager.track_slippage(
        leg_index=0,
        market_symbol="ETH/USDT",
        expected_price=100.0,
        executed_price=102.0,
        side="buy"
    )

    print(f"Calculated slippage: {measurement.slippage_bps:.2f} bps")
    print(f"Violation detected: {violated}")

    if violated:
        cycle_path = ["BTC", "ETH", "USDT"]
        print("\nLogging slippage violation and adding to cooldown...")

        manager.log_slippage_violation(
            cycle_id="demo_cycle_002",
            strategy_name="demo_strategy",
            cycle_path=cycle_path,
            cycle_direction="->",
            violated_leg=measurement
        )

        print("✓ Violation logged to console and JSON file")

        print(f"\nChecking cooldown status...")
        in_cooldown = manager.is_cycle_in_cooldown(cycle_path)
        remaining = manager.get_cycle_cooldown_remaining(cycle_path)
        print(f"Cycle in cooldown: {in_cooldown}")
        print(f"Remaining cooldown time: {remaining:.1f}s")

        print("\nWaiting for cooldown to expire...")
        await asyncio.sleep(5.1)

        in_cooldown = manager.is_cycle_in_cooldown(cycle_path)
        print(f"Cycle in cooldown after 5s: {in_cooldown}")
        print("✓ Cooldown expired successfully")


async def demo_statistics():
    print("\n" + "=" * 60)
    print("DEMO 3: Risk Control Statistics")
    print("=" * 60)

    manager = RiskControlManager(
        max_leg_latency_ms=100,
        max_slippage_bps=50,
        slippage_cooldown_seconds=300,
        log_dir="logs/risk_controls_demo"
    )

    print("\nGenerating sample violations...")

    for i in range(3):
        start_time = time.time() - 0.15
        measurement = manager.latency_monitor.end_measurement(
            i, f"PAIR{i}/USDT", start_time, "buy"
        )
        manager.log_latency_violation(
            f"cycle_{i}",
            "demo_strategy",
            ["BTC", "ETH", "USDT"],
            "->",
            measurement
        )

    for i in range(2):
        measurement, _ = manager.track_slippage(
            i, f"PAIR{i}/USDT", 100.0, 102.0, "buy"
        )
        manager.log_slippage_violation(
            f"cycle_{i+3}",
            "demo_strategy",
            ["ETH", "BTC", "USDT"],
            "->",
            measurement
        )

    print("✓ Generated 3 latency violations and 2 slippage violations")

    print("\nRetrieving statistics...")
    stats = manager.get_stats()

    print(f"\nTotal violations: {stats['violations']['total_violations']}")
    print(f"Active cooldowns: {stats['active_cooldowns']}")

    print("\nViolations by type:")
    for vtype, count in stats['violations']['by_type'].items():
        print(f"  {vtype}: {count}")

    print("\nConfiguration:")
    for key, value in stats['config'].items():
        print(f"  {key}: {value}")


async def main():
    print("\n" + "=" * 60)
    print("RISK CONTROLS DEMONSTRATION")
    print("=" * 60)

    await demo_latency_violation()
    await demo_slippage_violation()
    await demo_statistics()

    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
    print("\nCheck logs/risk_controls_demo/risk_violations.jsonl for detailed logs")
    print()


if __name__ == "__main__":
    asyncio.run(main())