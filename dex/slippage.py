"""
Dynamic slippage calculation for DEX trades.

Calculates realistic slippage based on pool depth, trade size,
and AMM mechanics (constant product formula).
"""

from decimal import Decimal
from typing import Tuple

from triangular_arbitrage.utils import get_logger

logger = get_logger(__name__)


def calculate_price_impact(
    amount_in: Decimal,
    reserve_in: Decimal,
    reserve_out: Decimal,
    fee: Decimal = Decimal("0.003"),
) -> Decimal:
    """
    Calculate price impact for a Uniswap V2 style swap using exact constant product formula.

    Uses the constant product formula: x * y = k
    Exact formula: price_impact = 1 - (amount_out_actual / amount_out_no_impact)

    Args:
        amount_in: Amount of input token (raw units)
        reserve_in: Input token reserve (raw units)
        reserve_out: Output token reserve (raw units)
        fee: DEX fee as decimal (0.003 = 0.3%)

    Returns:
        Price impact as decimal (e.g., 0.0025 = 0.25%)

    Example:
        >>> # $500 trade in $10,000 USDC reserve, $10,000 WETH reserve, 0.3% fee
        >>> impact = calculate_price_impact(
        ...     Decimal("500") * Decimal(10**6),  # 500 USDC (6 decimals)
        ...     Decimal("10000") * Decimal(10**6),  # 10k USDC reserve
        ...     Decimal("10000") * Decimal(10**18),  # 10k WETH reserve (18 decimals)
        ...     Decimal("0.003")
        ... )
        >>> # Expected: ~2.5% price impact (500/10000 = 5% of reserves)
        >>> assert impact < Decimal("0.03")  # Less than 3%
    """
    if reserve_in == 0 or reserve_out == 0:
        return Decimal("1.0")  # 100% slippage (pool is empty)

    # Use exact constant product formula for accurate pricing
    # amount_out = (reserve_out * amount_in * (1 - fee)) / (reserve_in + amount_in * (1 - fee))
    # price_impact = 1 - (amount_out_actual / amount_out_no_slippage)

    amount_in_after_fee = amount_in * (Decimal("1") - fee)

    # Calculate actual output using constant product formula
    amount_out = (reserve_out * amount_in_after_fee) / (
        reserve_in + amount_in_after_fee
    )

    # Calculate theoretical output with no slippage (just spot price)
    # spot_price = reserve_out / reserve_in
    # theoretical_output = amount_in_after_fee * spot_price
    theoretical_output = (amount_in_after_fee * reserve_out) / reserve_in

    # Price impact = difference between theoretical and actual
    if theoretical_output == 0:
        return Decimal("1.0")

    price_impact = Decimal("1") - (amount_out / theoretical_output)

    # Cap at 100% (can't have more than 100% slippage)
    return max(Decimal("0"), min(price_impact, Decimal("1.0")))


def calculate_dynamic_slippage(
    amount_in: Decimal,
    reserve_in: Decimal,
    reserve_out: Decimal,
    fee: Decimal = Decimal("0.003"),
    safety_multiplier: Decimal = Decimal("1.2"),
) -> Decimal:
    """
    Calculate dynamic slippage tolerance for a trade with adaptive safety buffer.

    Returns a slippage percentage that accounts for:
    1. Expected price impact from AMM mechanics
    2. Adaptive safety buffer based on trade size

    Args:
        amount_in: Amount of input token (raw units)
        reserve_in: Input token reserve (raw units)
        reserve_out: Output token reserve (raw units)
        fee: DEX fee as decimal (0.003 = 0.3%)
        safety_multiplier: Base multiplier for safety buffer (1.2 = 20% extra buffer)

    Returns:
        Slippage tolerance as decimal (e.g., 0.002 = 0.2%)

    Example:
        >>> # $500 trade in $10k/$10k pool
        >>> slippage = calculate_dynamic_slippage(
        ...     Decimal("500") * Decimal(10**6),
        ...     Decimal("10000") * Decimal(10**6),
        ...     Decimal("10000") * Decimal(10**18),
        ...     Decimal("0.003"),
        ...     Decimal("1.2")
        ... )
        >>> # Expected: ~3% (2.5% impact * 1.2 safety)
        >>> assert slippage < Decimal("0.04")
    """
    # Calculate expected price impact
    price_impact = calculate_price_impact(amount_in, reserve_in, reserve_out, fee)

    # Adaptive safety multiplier based on trade size
    # Larger trades (>5% of reserves) get higher safety buffer due to:
    # - More MEV risk (bigger profit = more competition)
    # - Higher execution uncertainty
    # - Greater chance of frontrunning
    trade_fraction = amount_in / reserve_in if reserve_in > 0 else Decimal("1")

    if trade_fraction > Decimal("0.05"):  # >5% of pool
        # Large trade: increase safety buffer
        adaptive_multiplier = safety_multiplier * Decimal("1.3")  # +30% extra
    elif trade_fraction < Decimal("0.01"):  # <1% of pool
        # Small trade: reduce safety buffer (less MEV risk)
        adaptive_multiplier = safety_multiplier * Decimal("0.9")  # -10%
    else:
        adaptive_multiplier = safety_multiplier

    # Apply safety multiplier for execution uncertainty
    safe_slippage = price_impact * adaptive_multiplier

    # Set minimum slippage (for very small trades)
    # Even tiny trades need some slippage tolerance due to rounding
    min_slippage = Decimal("0.0001")  # 0.01% minimum

    # Set maximum slippage (reject obviously bad trades)
    # If slippage > 5%, trade is too large for pool
    max_slippage = Decimal("0.05")  # 5% maximum

    final_slippage = max(min_slippage, min(safe_slippage, max_slippage))

    logger.debug(
        f"Dynamic slippage: {float(final_slippage)*100:.4f}% "
        f"(impact: {float(price_impact)*100:.4f}%, "
        f"multiplier: {float(adaptive_multiplier):.2f}x, "
        f"trade: {float(trade_fraction)*100:.1f}% of reserves)"
    )

    return final_slippage


def calculate_two_leg_slippage(
    leg1_amount_in: Decimal,
    leg1_reserve_in: Decimal,
    leg1_reserve_out: Decimal,
    leg1_fee: Decimal,
    leg2_amount_in: Decimal,
    leg2_reserve_in: Decimal,
    leg2_reserve_out: Decimal,
    leg2_fee: Decimal,
    safety_multiplier: Decimal = Decimal("1.5"),
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Calculate dynamic slippage for a 2-leg arbitrage trade.

    Returns individual leg slippages and combined total.

    Args:
        leg1_amount_in: Leg 1 input amount
        leg1_reserve_in: Leg 1 input reserve
        leg1_reserve_out: Leg 1 output reserve
        leg1_fee: Leg 1 fee
        leg2_amount_in: Leg 2 input amount
        leg2_reserve_in: Leg 2 input reserve
        leg2_reserve_out: Leg 2 output reserve
        leg2_fee: Leg 2 fee
        safety_multiplier: Safety buffer multiplier

    Returns:
        Tuple of (leg1_slippage, leg2_slippage, total_slippage_pct)
        where total_slippage_pct is the combined impact as percentage
    """
    # Calculate slippage for each leg
    leg1_slippage = calculate_dynamic_slippage(
        leg1_amount_in,
        leg1_reserve_in,
        leg1_reserve_out,
        leg1_fee,
        safety_multiplier,
    )

    leg2_slippage = calculate_dynamic_slippage(
        leg2_amount_in,
        leg2_reserve_in,
        leg2_reserve_out,
        leg2_fee,
        safety_multiplier,
    )

    # Combined slippage (additive for multi-leg trades)
    # Each leg compounds: (1 - s1) * (1 - s2) = 1 - (s1 + s2 - s1*s2)
    # For small slippages: s_total ≈ s1 + s2
    total_slippage_pct = (leg1_slippage + leg2_slippage) * Decimal("100")

    return leg1_slippage, leg2_slippage, total_slippage_pct


def estimate_max_trade_size(
    reserve_in: Decimal,
    reserve_out: Decimal,
    max_slippage: Decimal = Decimal("0.01"),
    fee: Decimal = Decimal("0.003"),
) -> Decimal:
    """
    Estimate maximum trade size for a given slippage tolerance.

    Uses binary search to find the largest trade that stays under
    the slippage limit.

    Args:
        reserve_in: Input token reserve
        reserve_out: Output token reserve
        max_slippage: Maximum acceptable slippage (0.01 = 1%)
        fee: DEX fee

    Returns:
        Maximum trade size in input token units

    Example:
        >>> # Find max trade for 1% slippage in $10k/$10k pool
        >>> max_size = estimate_max_trade_size(
        ...     Decimal("10000") * Decimal(10**6),
        ...     Decimal("10000") * Decimal(10**18),
        ...     Decimal("0.01"),
        ...     Decimal("0.003")
        ... )
        >>> # Expected: ~$1,000-2,000 (10-20% of reserves)
        >>> assert max_size > Decimal("1000") * Decimal(10**6)
    """
    # Binary search for max size
    low = Decimal("0")
    high = reserve_in * Decimal("0.5")  # Start with 50% of reserves as upper bound

    # Binary search with 20 iterations (enough for good precision)
    for _ in range(20):
        mid = (low + high) / Decimal("2")

        # Calculate slippage at midpoint
        impact = calculate_price_impact(mid, reserve_in, reserve_out, fee)

        if impact <= max_slippage:
            low = mid  # Can trade more
        else:
            high = mid  # Trade is too large

    return low


# ============================================================================
# Helper functions for integration with existing code
# ============================================================================


def get_slippage_config(
    trade_size_usd: float,
    enable_dynamic: bool = True,
    fallback_slippage_pct: float = 0.2,
) -> dict:
    """
    Get slippage configuration for scanner.

    Args:
        trade_size_usd: Trade size in USD
        enable_dynamic: Whether to enable dynamic slippage
        fallback_slippage_pct: Fixed slippage to use if dynamic disabled

    Returns:
        Dict with slippage config
    """
    return {
        "enabled": enable_dynamic,
        "trade_size_usd": trade_size_usd,
        "fallback_pct": fallback_slippage_pct,
        "safety_multiplier": 1.5,
        "min_slippage_pct": 0.01,  # 0.01% minimum
        "max_slippage_pct": 5.0,  # 5% maximum
    }
