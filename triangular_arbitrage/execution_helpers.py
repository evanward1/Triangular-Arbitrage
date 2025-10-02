#!/usr/bin/env python3
"""
Execution Helpers - Order book depth analysis and execution utilities
"""

import asyncio
from typing import Dict, List, Optional, Tuple


def depth_fill_price(
    book_side: List[Tuple[float, float]], amount: float
) -> Optional[float]:
    """
    Compute volume-weighted average price (VWAP) from order book.

    Args:
        book_side: List of [price, size] tuples from order book
        amount: Amount to fill

    Returns:
        VWAP or None if insufficient depth
    """
    if not book_side or amount <= 0:
        return None

    filled = 0.0
    cost = 0.0

    for price, size in book_side:
        if filled >= amount:
            break

        take = min(size, amount - filled)
        cost += take * price
        filled += take

    if filled < amount * 0.95:  # Need at least 95% fill
        return None

    return cost / filled if filled > 0 else None


def depth_limited_size(
    book_side: List[Tuple[float, float]],
    best_price: float,
    max_slippage_pct: float = 0.10,
) -> float:
    """
    Calculate maximum executable size within slippage tolerance.

    Args:
        book_side: List of [price, size] tuples
        best_price: Best bid/ask price
        max_slippage_pct: Maximum acceptable slippage (default 0.10%)

    Returns:
        Maximum size that can be executed within slippage limit
    """
    if not book_side or best_price <= 0:
        return 0.0

    max_price = best_price * (1 + max_slippage_pct / 100)
    total_size = 0.0

    for price, size in book_side:
        if price > max_price:
            break
        total_size += size

    return total_size


def estimate_cycle_slippage_pct(books: List[Dict], amounts: List[float]) -> float:
    """
    Estimate total slippage for a cycle from order books.

    Args:
        books: List of order book dicts with 'bids'/'asks' keys
        amounts: List of amounts for each leg

    Returns:
        Total estimated slippage percentage
    """
    if len(books) != len(amounts):
        return 999.0  # Invalid input

    total_slippage = 0.0

    for book, amount in zip(books, amounts):
        if not book:
            return 999.0

        # Determine which side to use (asks for buys, bids for sells)
        # For simplicity, we'll check both and use the one with data
        if "asks" in book and book["asks"]:
            side = book["asks"]
            best_price = side[0][0]
        elif "bids" in book and book["bids"]:
            side = book["bids"]
            best_price = side[0][0]
        else:
            return 999.0

        vwap = depth_fill_price(side, amount)
        if vwap is None:
            return 999.0  # Insufficient depth

        leg_slippage = abs((vwap - best_price) / best_price) * 100
        total_slippage += leg_slippage

    return total_slippage


async def leg_timed(coro, timeout_ms: int = 2000, label: str = "leg") -> Optional[any]:
    """
    Execute coroutine with timeout guard for latency control.

    Args:
        coro: Coroutine to execute
        timeout_ms: Timeout in milliseconds
        label: Label for logging

    Returns:
        Result or None on timeout
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)
        return result
    except asyncio.TimeoutError:
        print(f"⚠️  {label} timed out after {timeout_ms}ms")
        return None
    except Exception as e:
        print(f"❌ {label} error: {e}")
        return None


def fee_cost_pct_for_legs(fee_rates: List[float], leg_count: int = 3) -> float:
    """
    Calculate total fee cost percentage for multi-leg cycle.

    Args:
        fee_rates: List of fee rates (as decimals, e.g., 0.001 for 0.1%)
        leg_count: Number of legs (default 3 for triangular)

    Returns:
        Total fee cost as percentage
    """
    if not fee_rates:
        return 0.0

    # Use average if multiple rates provided, or first rate if uniform
    avg_fee = sum(fee_rates) / len(fee_rates) if len(fee_rates) > 1 else fee_rates[0]

    return leg_count * (avg_fee * 100)
