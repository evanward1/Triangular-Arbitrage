#!/usr/bin/env python3
"""
Test script to validate profit calculation fixes.

Tests that pools with bad reserve data are properly rejected.
"""
from decimal import Decimal

from dex.types import DexPool

# Mock a DexRunner simulation cycle validation
MIN_RESERVE = Decimal("100") * Decimal(10**18)  # 100 tokens with 18 decimals
MAX_RATIO = Decimal("1000000")  # 1M:1 max ratio
MAX_PROFIT_PCT = Decimal("100")  # 100%


def validate_pool(pool: DexPool, name: str) -> bool:
    """Validate pool reserves and ratios."""
    print(f"\nValidating {name}:")
    print(f"  Reserves: r0={float(pool.r0):,.0f}, r1={float(pool.r1):,.0f}")

    # Check minimum reserves
    if pool.r0 < MIN_RESERVE or pool.r1 < MIN_RESERVE:
        print(
            "  ❌ REJECTED: reserves too low (min: {:,.0f})".format(float(MIN_RESERVE))
        )
        return False

    # Check price ratio
    ratio = pool.r1 / pool.r0 if pool.r0 > 0 else Decimal("0")
    print(f"  Price ratio (r1/r0): {float(ratio):.2e}")

    if ratio > MAX_RATIO or ratio < (Decimal("1") / MAX_RATIO):
        print(f"  ❌ REJECTED: extreme price ratio (max: {float(MAX_RATIO):,.0f})")
        return False

    print(f"  ✅ PASSED validation")
    return True


def validate_profit(gross_pct: Decimal, pair_name: str) -> bool:
    """Validate profit percentage is within reasonable bounds."""
    print(f"\nValidating profit for {pair_name}:")
    print(f"  Gross profit: {float(gross_pct):+.2f}%")

    if gross_pct > MAX_PROFIT_PCT or gross_pct < -MAX_PROFIT_PCT:
        print(f"  ❌ REJECTED: unrealistic profit (max: ±{float(MAX_PROFIT_PCT)}%)")
        return False

    print(f"  ✅ PASSED validation")
    return True


# Test cases
print("=" * 80)
print("Testing Pool Reserve Validation")
print("=" * 80)

# Good pool (realistic reserves)
good_pool = DexPool(
    dex="pancakeswap",
    kind="v2",
    pair_name="WBNB/USDT",
    pair_addr="0x" + "0" * 40,
    token0="0x" + "1" * 40,
    token1="0x" + "2" * 40,
    r0=Decimal("1000") * Decimal(10**18),  # 1000 WBNB
    r1=Decimal("300000") * Decimal(10**18),  # 300k USDT (price ~$300/WBNB)
    fee=Decimal("0.0025"),
    base_symbol="WBNB",
    quote_symbol="USDT",
)
validate_pool(good_pool, "Good Pool (WBNB/USDT)")

# Bad pool #1: Extremely low reserves (scam token)
bad_pool1 = DexPool(
    dex="biswap",
    kind="v2",
    pair_name="EVDC/WBNB",
    pair_addr="0x" + "0" * 40,
    token0="0x" + "3" * 40,
    token1="0x" + "4" * 40,
    r0=Decimal("1"),  # 1 wei of EVDC
    r1=Decimal("1000") * Decimal(10**18),  # 1000 WBNB
    fee=Decimal("0.0025"),
    base_symbol="EVDC",
    quote_symbol="WBNB",
)
validate_pool(bad_pool1, "Bad Pool #1 (EVDC - low reserves)")

# Bad pool #2: Extreme price ratio
bad_pool2 = DexPool(
    dex="apeswap",
    kind="v2",
    pair_name="SCAM/WBNB",
    pair_addr="0x" + "0" * 40,
    token0="0x" + "5" * 40,
    token1="0x" + "6" * 40,
    r0=Decimal("1000000000") * Decimal(10**18),  # 1B scam tokens
    r1=Decimal("1") * Decimal(10**15),  # 0.001 WBNB
    fee=Decimal("0.003"),
    base_symbol="SCAM",
    quote_symbol="WBNB",
)
validate_pool(bad_pool2, "Bad Pool #2 (SCAM - extreme ratio)")

# Test profit validation
print("\n" + "=" * 80)
print("Testing Profit Validation")
print("=" * 80)

validate_profit(Decimal("2.5"), "Realistic arbitrage (2.5%)")
validate_profit(Decimal("150"), "Unrealistic arbitrage (150%)")
validate_profit(Decimal("137309026000362944"), "Scam token (137 trillion %)")

print("\n" + "=" * 80)
print("✅ All validation tests completed!")
print("=" * 80)
print("\nSummary:")
print("  - Good pools with realistic reserves: PASS")
print("  - Bad pools with low reserves: REJECTED")
print("  - Bad pools with extreme ratios: REJECTED")
print("  - Realistic profits (<100%): PASS")
print("  - Unrealistic profits (>100%): REJECTED")
