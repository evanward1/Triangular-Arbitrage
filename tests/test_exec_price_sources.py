"""
Test executable price source validation.

Validates:
1. Reject midpoint or wrong side source
2. Accept valid trio with buy using ask and sell using bid
"""

import pytest

from triangular_arbitrage.validation.breakeven import BreakevenGuard, LegInfo


def test_reject_midpoint_source():
    """Reject leg using midpoint instead of ask/bid."""
    guard = BreakevenGuard()

    legs = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="midpoint",  # Invalid: should be "ask" for buy
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=50,
        ),
    ]

    with pytest.raises(ValueError, match="must use ask but used midpoint"):
        guard.compute(
            legs=legs,
            gross_pct=1.0,
            gas_units=0,
            gas_price_quote=0.0,
            total_notional_quote=100.0,
            threshold_pct=0.20,
        )


def test_reject_buy_using_bid():
    """Reject buy leg using bid instead of ask."""
    guard = BreakevenGuard()

    legs = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="bid",  # Invalid: buy should use ask
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=50,
        ),
    ]

    with pytest.raises(ValueError, match="must use ask but used bid"):
        guard.compute(
            legs=legs,
            gross_pct=1.0,
            gas_units=0,
            gas_price_quote=0.0,
            total_notional_quote=100.0,
            threshold_pct=0.20,
        )


def test_reject_sell_using_ask():
    """Reject sell leg using ask instead of bid."""
    guard = BreakevenGuard()

    legs = [
        LegInfo(
            pair="BTC/USD",
            side="sell",
            price_used=50000.0,
            price_source="ask",  # Invalid: sell should use bid
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=50,
        ),
    ]

    with pytest.raises(ValueError, match="must use bid but used ask"):
        guard.compute(
            legs=legs,
            gross_pct=1.0,
            gas_units=0,
            gas_price_quote=0.0,
            total_notional_quote=100.0,
            threshold_pct=0.20,
        )


def test_accept_valid_buy_ask_trio():
    """Accept valid trio with buy using ask and sells using bid."""
    guard = BreakevenGuard()

    legs = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="ask",  # Valid: buy uses ask
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=50,
        ),
        LegInfo(
            pair="ETH/BTC",
            side="sell",
            price_used=0.05,
            price_source="bid",  # Valid: sell uses bid
            vwap_levels=3,
            slippage_pct=0.03,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=60,
        ),
        LegInfo(
            pair="ETH/USD",
            side="sell",
            price_used=2500.0,
            price_source="bid",  # Valid: sell uses bid
            vwap_levels=3,
            slippage_pct=0.04,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=70,
        ),
    ]

    # Should not raise any exception
    result = guard.compute(
        legs=legs,
        gross_pct=1.0,
        gas_units=0,
        gas_price_quote=0.0,
        total_notional_quote=300.0,
        threshold_pct=0.20,
    )

    # Verify result is valid
    assert result.gross_pct == 1.0
    assert result.net_pct < 1.0  # Net is less than gross after costs


def test_accept_valid_mixed_trio():
    """Accept valid trio with mix of buy and sell operations."""
    guard = BreakevenGuard()

    legs = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="ask",
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=50,
        ),
        LegInfo(
            pair="ETH/BTC",
            side="buy",
            price_used=0.05,
            price_source="ask",
            vwap_levels=3,
            slippage_pct=0.03,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=60,
        ),
        LegInfo(
            pair="ETH/USD",
            side="sell",
            price_used=2500.0,
            price_source="bid",
            vwap_levels=3,
            slippage_pct=0.04,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=70,
        ),
    ]

    # Should not raise any exception
    result = guard.compute(
        legs=legs,
        gross_pct=1.0,
        gas_units=0,
        gas_price_quote=0.0,
        total_notional_quote=300.0,
        threshold_pct=0.20,
    )

    assert result is not None


def test_reject_excessive_latency():
    """Reject leg with latency exceeding max threshold."""
    guard = BreakevenGuard(max_leg_latency_ms=500)

    legs = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="ask",
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=100.0,
            latency_ms=1000,  # Exceeds max of 500ms
        ),
    ]

    with pytest.raises(ValueError, match="latency 1000ms exceeds max 500ms"):
        guard.compute(
            legs=legs,
            gross_pct=1.0,
            gas_units=0,
            gas_price_quote=0.0,
            total_notional_quote=100.0,
            threshold_pct=0.20,
        )


def test_reject_non_positive_notional():
    """Reject leg with non-positive notional_quote."""
    guard = BreakevenGuard()

    # Test zero notional
    legs_zero = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="ask",
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=0.0,  # Zero notional
            latency_ms=50,
        ),
    ]

    with pytest.raises(ValueError, match="notional_quote must be positive"):
        guard.compute(
            legs=legs_zero,
            gross_pct=1.0,
            gas_units=0,
            gas_price_quote=0.0,
            total_notional_quote=100.0,
            threshold_pct=0.20,
        )

    # Test negative notional
    legs_neg = [
        LegInfo(
            pair="BTC/USD",
            side="buy",
            price_used=50000.0,
            price_source="ask",
            vwap_levels=3,
            slippage_pct=0.05,
            fee_pct=0.10,
            notional_quote=-100.0,  # Negative notional
            latency_ms=50,
        ),
    ]

    with pytest.raises(ValueError, match="notional_quote must be positive"):
        guard.compute(
            legs=legs_neg,
            gross_pct=1.0,
            gas_units=0,
            gas_price_quote=0.0,
            total_notional_quote=100.0,
            threshold_pct=0.20,
        )


def test_two_leg_dex_cycle():
    """Accept valid two-leg DEX cycle."""
    guard = BreakevenGuard()

    legs = [
        LegInfo(
            pair="WETH/USDC@UniswapV2",
            side="buy",
            price_used=2000.0,
            price_source="ask",
            vwap_levels=1,
            slippage_pct=0.30,
            fee_pct=0.30,
            notional_quote=100.0,
            latency_ms=0,
        ),
        LegInfo(
            pair="WETH/USDC@SushiSwap",
            side="sell",
            price_used=2010.0,
            price_source="bid",
            vwap_levels=1,
            slippage_pct=0.05,
            fee_pct=0.30,
            notional_quote=100.0,
            latency_ms=0,
        ),
    ]

    # Should accept two-leg cycle
    result = guard.compute(
        legs=legs,
        gross_pct=0.50,
        gas_units=0,
        gas_price_quote=0.0,
        total_notional_quote=200.0,
        threshold_pct=0.00,
    )

    assert result is not None
    assert len(legs) == 2  # DEX cycles have 2 legs
