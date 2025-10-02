#!/usr/bin/env python3
"""
Test helper functions
"""

from triangular_arbitrage.execution_helpers import (
    depth_fill_price,
    depth_limited_size,
    estimate_cycle_slippage_pct,
    fee_cost_pct_for_legs,
)


def test_depth_fill_price():
    """Test VWAP calculation"""
    # Order book: [(price, size), ...]
    book = [
        (100.0, 1.0),
        (100.5, 2.0),
        (101.0, 3.0),
    ]

    # Fill 2 units
    vwap = depth_fill_price(book, 2.0)
    print(f"VWAP for 2 units: ${vwap:.2f}")
    # Expected: (1*100 + 1*100.5) / 2 = 100.25

    # Fill 4 units
    vwap = depth_fill_price(book, 4.0)
    print(f"VWAP for 4 units: ${vwap:.2f}")
    # Expected: (1*100 + 2*100.5 + 1*101) / 4 = 100.5

    # Fill too much (insufficient depth)
    vwap = depth_fill_price(book, 10.0)
    print(f"VWAP for 10 units (insufficient): {vwap}")
    # Expected: None


def test_depth_limited_size():
    """Test depth-limited sizing"""
    # Order book: [(price, size), ...]
    book = [
        (100.0, 1.0),
        (100.5, 2.0),
        (101.0, 3.0),
        (102.0, 5.0),
    ]

    best_price = 100.0

    # Max 0.10% slippage
    max_size = depth_limited_size(book, best_price, max_slippage_pct=0.10)
    print(f"Max size at 0.10% slippage: {max_size:.2f}")
    # 0.10% of 100 = 0.10, so max price = 100.10
    # Only first order qualifies: size = 1.0

    # Max 1.0% slippage
    max_size = depth_limited_size(book, best_price, max_slippage_pct=1.0)
    print(f"Max size at 1.0% slippage: {max_size:.2f}")
    # 1.0% of 100 = 1.0, so max price = 101.0
    # Orders at 100, 100.5, 101: size = 1 + 2 + 3 = 6.0


def test_estimate_cycle_slippage():
    """Test cycle slippage estimation"""
    # 3-leg cycle with order books
    books = [
        {
            "asks": [(100.0, 1.0), (101.0, 2.0)],
            "bids": [(99.0, 1.0), (98.0, 2.0)],
        },
        {
            "asks": [(200.0, 0.5), (202.0, 1.0)],
            "bids": [(198.0, 0.5), (196.0, 1.0)],
        },
        {
            "asks": [(50.0, 2.0), (51.0, 4.0)],
            "bids": [(49.0, 2.0), (48.0, 4.0)],
        },
    ]

    amounts = [1.0, 0.5, 2.0]

    slippage = estimate_cycle_slippage_pct(books, amounts)
    print(f"Cycle slippage: {slippage:.4f}%")


def test_fee_cost():
    """Test fee cost calculation"""
    # Uniform 0.10% fee (Binance.US)
    fee_rates = [0.001]
    total_fee = fee_cost_pct_for_legs(fee_rates, leg_count=3)
    print(f"Total fee for 3 legs at 0.10%: {total_fee:.2f}%")
    # Expected: 3 * 0.10% = 0.30%

    # Mixed fees (Kraken)
    fee_rates = [0.0016, 0.0026, 0.0026]
    total_fee = fee_cost_pct_for_legs(fee_rates, leg_count=3)
    print(f"Total fee for 3 legs (mixed): {total_fee:.2f}%")
    # Expected: (0.16 + 0.26 + 0.26) / 3 * 3 = 0.68%


if __name__ == "__main__":
    print("Testing helper functions\n")
    print("=" * 60)

    print("\n1. Testing depth_fill_price:")
    test_depth_fill_price()

    print("\n2. Testing depth_limited_size:")
    test_depth_limited_size()

    print("\n3. Testing estimate_cycle_slippage:")
    test_estimate_cycle_slippage()

    print("\n4. Testing fee_cost_pct_for_legs:")
    test_fee_cost()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
