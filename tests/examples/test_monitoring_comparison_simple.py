#!/usr/bin/env python3
"""
Test script to compare order monitoring strategies:
1. Fixed interval polling (old approach)
2. Exponential backoff with jitter (new approach)

This simulates order monitoring over various fill times and demonstrates
the reduction in API calls with the new strategy.
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, Tuple
import statistics


@dataclass
class SimulatedOrder:
    """Simulated order with configurable fill time"""
    id: str
    fill_time: float  # Seconds until order fills
    created_at: float
    status: str = "open"
    filled_amount: float = 0
    total_amount: float = 100


class MockExchange:
    """Mock exchange that tracks API calls"""

    def __init__(self):
        self.api_calls = 0

    async def fetch_order(self, order_id: str, order: SimulatedOrder) -> Dict:
        """Simulate fetching order status"""
        self.api_calls += 1

        # Simulate API latency
        await asyncio.sleep(0.05)

        # Check if order should be filled
        elapsed = time.time() - order.created_at
        if elapsed >= order.fill_time:
            return {
                'id': order_id,
                'status': 'filled',
                'filled': order.total_amount,
                'remaining': 0
            }
        else:
            # Partial fill simulation
            progress = min(elapsed / order.fill_time, 1.0)
            return {
                'id': order_id,
                'status': 'open' if progress < 1.0 else 'filled',
                'filled': order.total_amount * progress,
                'remaining': order.total_amount * (1 - progress)
            }


class FixedIntervalMonitor:
    """Old monitoring approach with fixed interval"""

    def __init__(self, exchange: MockExchange):
        self.exchange = exchange

    async def monitor_order(self, order: SimulatedOrder, timeout: float = 30.0) -> Tuple[int, float]:
        """Monitor order with fixed interval polling"""
        start_time = time.time()
        check_interval = 0.5
        api_calls = 0

        while time.time() - start_time < timeout:
            result = await self.exchange.fetch_order(order.id, order)
            api_calls += 1

            if result['status'] == 'filled':
                elapsed = time.time() - start_time
                return api_calls, elapsed

            await asyncio.sleep(check_interval)
            check_interval = min(check_interval * 1.5, 2.0)

        return api_calls, timeout


class ExponentialBackoffMonitor:
    """New monitoring approach with exponential backoff and jitter"""

    def __init__(self, exchange: MockExchange):
        self.exchange = exchange

        # Configuration
        self.initial_delay = 0.1
        self.max_delay = 5.0
        self.backoff_multiplier = 2.0
        self.jitter_factor = 0.3
        self.rapid_check_threshold = 2.0
        self.rapid_check_interval = 0.05

        # Cache
        self.cache = {}
        self.cache_ttl = 0.5

    async def monitor_order(self, order: SimulatedOrder, timeout: float = 30.0) -> Tuple[int, float]:
        """Monitor order with exponential backoff and jitter"""
        start_time = time.time()
        check_count = 0
        api_calls = 0

        # Rapid check phase end time
        rapid_check_end = start_time + self.rapid_check_threshold

        while time.time() - start_time < timeout:
            # Check cache first
            cache_key = order.id
            cached_result = self._get_cached(cache_key)

            if cached_result is None:
                result = await self.exchange.fetch_order(order.id, order)
                api_calls += 1
                self._cache_result(cache_key, result)
            else:
                result = cached_result

            if result['status'] == 'filled':
                elapsed = time.time() - start_time
                return api_calls, elapsed

            check_count += 1

            # Calculate next delay
            if time.time() < rapid_check_end:
                # Rapid checking for new orders
                next_delay = self.rapid_check_interval
            else:
                # Exponential backoff with jitter
                base_delay = min(
                    self.initial_delay * (self.backoff_multiplier ** (check_count - 20)),
                    self.max_delay
                )
                jitter = base_delay * self.jitter_factor * (2 * random.random() - 1)
                next_delay = max(base_delay + jitter, 0.05)

            await asyncio.sleep(next_delay)

        return api_calls, timeout

    def _get_cached(self, key: str):
        """Get cached result if still valid"""
        if key in self.cache:
            timestamp, data = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
            del self.cache[key]
        return None

    def _cache_result(self, key: str, data: Dict):
        """Cache result with timestamp"""
        self.cache[key] = (time.time(), data)


async def run_comparison():
    """Run comparison test between monitoring strategies"""

    # Test configurations
    fill_times = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0]
    num_runs_per_time = 5  # Reduced for faster execution

    # Results storage
    all_reductions = []

    print("=" * 60)
    print("ORDER MONITORING STRATEGY COMPARISON")
    print("=" * 60)
    print()
    print("Fill Time | Fixed Calls | Backoff Calls | Reduction")
    print("-" * 60)

    for fill_time in fill_times:
        fixed_calls = []
        backoff_calls = []

        for run in range(num_runs_per_time):
            # Create fresh exchange instances
            fixed_exchange = MockExchange()
            backoff_exchange = MockExchange()

            # Create monitors
            fixed_monitor = FixedIntervalMonitor(fixed_exchange)
            backoff_monitor = ExponentialBackoffMonitor(backoff_exchange)

            # Create simulated order
            order = SimulatedOrder(
                id=f"order_{fill_time}_{run}",
                fill_time=fill_time,
                created_at=time.time()
            )

            # Run fixed interval monitor
            fixed_api_calls, _ = await fixed_monitor.monitor_order(order, timeout=30.0)

            # Reset order for backoff monitor
            order.created_at = time.time()
            backoff_api_calls, _ = await backoff_monitor.monitor_order(order, timeout=30.0)

            fixed_calls.append(fixed_api_calls)
            backoff_calls.append(backoff_api_calls)

        # Calculate averages
        avg_fixed = statistics.mean(fixed_calls)
        avg_backoff = statistics.mean(backoff_calls)
        reduction = (avg_fixed - avg_backoff) / avg_fixed * 100
        all_reductions.append(reduction)

        print(f"{fill_time:9.1f}s | {avg_fixed:11.1f} | {avg_backoff:13.1f} | {reduction:8.1f}%")

    print("-" * 60)

    # Generate summary statistics
    print()
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    overall_reduction = statistics.mean(all_reductions)
    best_reduction = max(all_reductions)
    worst_reduction = min(all_reductions)

    print(f"Average API Call Reduction: {overall_reduction:.1f}%")
    print(f"Best Case Reduction: {best_reduction:.1f}%")
    print(f"Worst Case Reduction: {worst_reduction:.1f}%")

    # Simulate long-running order timeline
    print()
    print("=" * 60)
    print("LONG-RUNNING ORDER SIMULATION (20 second fill)")
    print("=" * 60)
    print()
    print("Time(s) | Fixed Calls | Backoff Calls | Saved Calls")
    print("-" * 50)

    for checkpoint in [2, 5, 10, 15, 20]:
        # Calculate fixed interval calls
        fixed_total = 0
        check_time = 0
        interval = 0.5
        while check_time < checkpoint:
            fixed_total += 1
            check_time += interval
            interval = min(interval * 1.5, 2.0)

        # Calculate exponential backoff calls
        backoff_total = 0
        check_time = 0
        check_count = 0
        while check_time < checkpoint:
            backoff_total += 1
            check_count += 1

            if check_time < 2.0:  # Rapid check phase
                delay = 0.05
            else:
                base_delay = min(0.1 * (2.0 ** (check_count - 20)), 5.0)
                delay = max(base_delay, 0.05)

            check_time += delay

        saved = fixed_total - backoff_total
        print(f"{checkpoint:7d} | {fixed_total:11d} | {backoff_total:13d} | {saved:11d}")

    return overall_reduction


async def main():
    """Main entry point"""
    try:
        reduction = await run_comparison()
        print()
        print("=" * 60)
        print(f"✓ Test completed successfully!")
        print(f"✓ Overall API call reduction: {reduction:.1f}%")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)