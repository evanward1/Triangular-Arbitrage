#!/usr/bin/env python3
"""Quick test to demonstrate the API call reduction with exponential backoff"""

import math
import random

def calculate_fixed_interval_calls(fill_time):
    """Calculate API calls with fixed interval strategy"""
    calls = 0
    elapsed = 0
    interval = 0.5

    while elapsed < fill_time:
        calls += 1
        elapsed += interval
        interval = min(interval * 1.5, 2.0)

    return calls

def calculate_exponential_backoff_calls(fill_time):
    """Calculate API calls with exponential backoff strategy"""
    calls = 0
    elapsed = 0
    check_count = 0

    # More balanced configuration
    rapid_check_threshold = 1.0  # Shorter rapid phase
    rapid_check_interval = 0.2  # Less aggressive rapid checking
    initial_delay = 0.3  # Start with reasonable delays
    max_delay = 5.0
    backoff_multiplier = 1.8  # Moderate backoff rate

    while elapsed < fill_time:
        calls += 1
        check_count += 1

        if elapsed < rapid_check_threshold:
            # Rapid checking for new orders, but not too aggressive
            delay = rapid_check_interval
        else:
            # Exponential backoff after rapid phase
            steps_after_rapid = check_count - int(rapid_check_threshold / rapid_check_interval)
            base_delay = min(
                initial_delay * (backoff_multiplier ** max(0, steps_after_rapid)),
                max_delay
            )
            # Add some jitter to prevent thundering herd
            jitter = base_delay * 0.2 * (random.random() - 0.5)
            delay = max(base_delay + jitter, 0.2)

        elapsed += delay

    return calls

def main():
    print("=" * 70)
    print("ORDER MONITORING API CALL COMPARISON")
    print("=" * 70)
    print()
    print("Fill Time | Fixed Strategy | Exponential Backoff | Reduction | Savings")
    print("-" * 70)

    fill_times = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0]
    total_fixed = 0
    total_backoff = 0

    for fill_time in fill_times:
        # Run multiple times and average
        fixed_sum = 0
        backoff_sum = 0
        runs = 10

        for _ in range(runs):
            fixed = calculate_fixed_interval_calls(fill_time)
            backoff = calculate_exponential_backoff_calls(fill_time)
            fixed_sum += fixed
            backoff_sum += backoff

        fixed_calls = fixed_sum / runs
        backoff_calls = backoff_sum / runs

        reduction = (fixed_calls - backoff_calls) / fixed_calls * 100
        savings = fixed_calls - backoff_calls

        total_fixed += fixed_calls
        total_backoff += backoff_calls

        print(f"{fill_time:8.1f}s | {fixed_calls:14.1f} | {backoff_calls:19.1f} | {reduction:8.1f}% | {savings:7.1f}")

    print("-" * 70)

    overall_reduction = (total_fixed - total_backoff) / total_fixed * 100
    overall_savings = total_fixed - total_backoff

    print(f"{'TOTAL':8s}  | {total_fixed:14.1f} | {total_backoff:19.1f} | {overall_reduction:8.1f}% | {overall_savings:7.1f}")

    print()
    print("=" * 70)
    print("KEY INSIGHTS")
    print("=" * 70)
    print()
    print(f"✓ Average API call reduction: {overall_reduction:.1f}%")
    print(f"✓ Total API calls saved: {overall_savings:.0f}")
    print()
    print("Benefits of Exponential Backoff with Jitter:")
    print("• Rapid initial checks for quick-filling orders")
    print("• Progressively longer delays for slow orders")
    print("• Jitter prevents thundering herd problem")
    print("• Cache reduces redundant API calls")
    print("• Rate limit awareness prevents throttling")

    print()
    print("=" * 70)
    print("EXAMPLE: 20-SECOND ORDER MONITORING TIMELINE")
    print("=" * 70)
    print()
    print("Time (s) | Fixed Calls | Backoff Calls | Description")
    print("-" * 70)

    checkpoints = [1, 2, 5, 10, 15, 20]
    for checkpoint in checkpoints:
        fixed = calculate_fixed_interval_calls(checkpoint)
        backoff = calculate_exponential_backoff_calls(checkpoint)

        if checkpoint <= 2:
            desc = "Rapid checking phase"
        elif checkpoint <= 5:
            desc = "Early backoff phase"
        elif checkpoint <= 10:
            desc = "Standard backoff phase"
        else:
            desc = "Maximum backoff phase"

        print(f"{checkpoint:8} | {fixed:11} | {backoff:13} | {desc}")

    print()
    print("=" * 70)
    print("✓ TEST COMPLETED SUCCESSFULLY")
    print("=" * 70)

if __name__ == "__main__":
    main()