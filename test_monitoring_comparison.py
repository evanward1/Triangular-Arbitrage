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
import matplotlib.pyplot as plt
import numpy as np


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
        self.rate_limit_hits = 0
        self.max_requests_per_second = 10

    async def fetch_order(self, order_id: str, order: SimulatedOrder) -> Dict:
        """Simulate fetching order status"""
        self.api_calls += 1

        # Simulate rate limiting
        await asyncio.sleep(0.05)  # Minimum API latency

        # Check if order should be filled
        elapsed = time.time() - order.created_at
        if elapsed >= order.fill_time:
            return {
                'id': order_id,
                'status': 'filled',
                'filled': order.total_amount,
                'remaining': 0,
                'average': 100.0
            }
        else:
            # Partial fill simulation
            progress = elapsed / order.fill_time
            return {
                'id': order_id,
                'status': 'open',
                'filled': order.total_amount * progress,
                'remaining': order.total_amount * (1 - progress),
                'average': 100.0
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

    def __init__(self, exchange: MockExchange, config: Dict = None):
        self.exchange = exchange
        config = config or {}

        # Load configuration
        self.initial_delay = config.get('initial_delay_ms', 100) / 1000.0
        self.max_delay = config.get('max_delay_ms', 5000) / 1000.0
        self.backoff_multiplier = config.get('backoff_multiplier', 2.0)
        self.jitter_factor = config.get('jitter_factor', 0.3)
        self.rapid_check_threshold = config.get('rapid_check_threshold_ms', 2000) / 1000.0
        self.rapid_check_interval = config.get('rapid_check_interval_ms', 50) / 1000.0

        # Cache
        self.cache = {}
        self.cache_ttl = config.get('cache_ttl_ms', 500) / 1000.0

    async def monitor_order(self, order: SimulatedOrder, timeout: float = 30.0) -> Tuple[int, float]:
        """Monitor order with exponential backoff and jitter"""
        start_time = time.time()
        check_count = 0
        api_calls = 0
        current_delay = self.initial_delay

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
                    self.initial_delay * (self.backoff_multiplier ** check_count),
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
    fill_times = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0]  # Various order fill times
    num_runs_per_time = 10  # Number of test runs per fill time

    # Results storage
    fixed_results = {'api_calls': [], 'fill_times': []}
    backoff_results = {'api_calls': [], 'fill_times': []}

    print("=" * 60)
    print("ORDER MONITORING STRATEGY COMPARISON")
    print("=" * 60)
    print()

    for fill_time in fill_times:
        print(f"Testing orders with {fill_time}s fill time...")

        fixed_calls = []
        backoff_calls = []

        for _ in range(num_runs_per_time):
            # Create fresh exchange instances
            fixed_exchange = MockExchange()
            backoff_exchange = MockExchange()

            # Create monitors
            fixed_monitor = FixedIntervalMonitor(fixed_exchange)
            backoff_monitor = ExponentialBackoffMonitor(backoff_exchange, {
                'initial_delay_ms': 100,
                'max_delay_ms': 5000,
                'backoff_multiplier': 2.0,
                'jitter_factor': 0.3,
                'rapid_check_threshold_ms': 2000,
                'rapid_check_interval_ms': 50,
                'cache_ttl_ms': 500
            })

            # Create simulated order
            order = SimulatedOrder(
                id=f"order_{fill_time}_{_}",
                fill_time=fill_time,
                created_at=time.time()
            )

            # Run both monitors
            fixed_api_calls, _ = await fixed_monitor.monitor_order(order, timeout=30.0)

            # Reset order for backoff monitor
            order.created_at = time.time()
            backoff_api_calls, _ = await backoff_monitor.monitor_order(order, timeout=30.0)

            fixed_calls.append(fixed_api_calls)
            backoff_calls.append(backoff_api_calls)

        # Calculate averages
        avg_fixed = np.mean(fixed_calls)
        avg_backoff = np.mean(backoff_calls)
        reduction = (avg_fixed - avg_backoff) / avg_fixed * 100

        fixed_results['api_calls'].append(avg_fixed)
        fixed_results['fill_times'].append(fill_time)
        backoff_results['api_calls'].append(avg_backoff)
        backoff_results['fill_times'].append(fill_time)

        print(f"  Fixed Interval: {avg_fixed:.1f} API calls")
        print(f"  Exponential Backoff: {avg_backoff:.1f} API calls")
        print(f"  Reduction: {reduction:.1f}%")
        print()

    # Generate summary statistics
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    total_fixed = sum(fixed_results['api_calls'])
    total_backoff = sum(backoff_results['api_calls'])
    overall_reduction = (total_fixed - total_backoff) / total_fixed * 100

    print(f"Total API calls (Fixed Interval): {total_fixed:.0f}")
    print(f"Total API calls (Exponential Backoff): {total_backoff:.0f}")
    print(f"Overall Reduction: {overall_reduction:.1f}%")
    print()

    # Best and worst case improvements
    reductions = [(fixed - backoff) / fixed * 100
                  for fixed, backoff in zip(fixed_results['api_calls'], backoff_results['api_calls'])]

    best_idx = np.argmax(reductions)
    worst_idx = np.argmin(reductions)

    print(f"Best improvement: {reductions[best_idx]:.1f}% reduction for {fill_times[best_idx]}s orders")
    print(f"Worst improvement: {reductions[worst_idx]:.1f}% reduction for {fill_times[worst_idx]}s orders")

    # Create visualization
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Plot 1: API calls comparison
    ax1.plot(fill_times, fixed_results['api_calls'], 'r-o', label='Fixed Interval', linewidth=2)
    ax1.plot(fill_times, backoff_results['api_calls'], 'g-o', label='Exponential Backoff', linewidth=2)
    ax1.set_xlabel('Order Fill Time (seconds)')
    ax1.set_ylabel('Average API Calls')
    ax1.set_title('API Calls vs Order Fill Time')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xscale('log')

    # Plot 2: Reduction percentage
    ax2.bar(range(len(fill_times)), reductions, color='blue', alpha=0.7)
    ax2.set_xlabel('Order Fill Time (seconds)')
    ax2.set_ylabel('API Call Reduction (%)')
    ax2.set_title('Percentage Reduction in API Calls')
    ax2.set_xticks(range(len(fill_times)))
    ax2.set_xticklabels([str(t) for t in fill_times], rotation=45)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=overall_reduction, color='red', linestyle='--',
                label=f'Average: {overall_reduction:.1f}%')
    ax2.legend()

    plt.tight_layout()
    plt.savefig('monitoring_comparison.png', dpi=150, bbox_inches='tight')
    print("\nVisualization saved as 'monitoring_comparison.png'")

    # Calculate API calls over time for a long-running order
    print("\n" + "=" * 60)
    print("LONG-RUNNING ORDER SIMULATION (20 second fill time)")
    print("=" * 60)

    # Track API calls over time
    time_points = []
    fixed_calls_timeline = []
    backoff_calls_timeline = []

    # Simulate monitoring timeline
    for checkpoint in range(1, 21):
        time_points.append(checkpoint)

        # Fixed interval calculation
        fixed_total = 0
        check_time = 0
        interval = 0.5
        while check_time < checkpoint:
            fixed_total += 1
            check_time += interval
            interval = min(interval * 1.5, 2.0)
        fixed_calls_timeline.append(fixed_total)

        # Exponential backoff calculation
        backoff_total = 0
        check_time = 0
        check_count = 0
        while check_time < checkpoint:
            backoff_total += 1
            check_count += 1

            if check_time < 2.0:  # Rapid check phase
                delay = 0.05
            else:
                base_delay = min(0.1 * (2.0 ** check_count), 5.0)
                delay = base_delay

            check_time += delay
        backoff_calls_timeline.append(backoff_total)

    print("\nTime(s) | Fixed Calls | Backoff Calls | Difference")
    print("-" * 50)
    for t, f, b in zip(time_points[::2], fixed_calls_timeline[::2], backoff_calls_timeline[::2]):
        diff = f - b
        print(f"{t:7d} | {f:11d} | {b:13d} | {diff:+10d}")

    return overall_reduction


async def main():
    """Main entry point"""
    try:
        reduction = await run_comparison()
        print("\n" + "=" * 60)
        print(f"✓ Test completed successfully!")
        print(f"✓ Overall API call reduction: {reduction:.1f}%")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())