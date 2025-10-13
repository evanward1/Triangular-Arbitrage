"""
Breakeven validation and profitability math single source of truth.

Enforces four invariants at every arbitrage decision point:
1. Executable prices only (buy=ask, sell=bid)
2. Per-leg accounting (sum fees and slippage across legs)
3. Correct gas normalization (gas_pct decreases as notional increases)
4. Strict breakeven inequality (net>0 implies gross > fees+slip+gas+thresh)
"""

from dataclasses import dataclass
from typing import Literal, Sequence


@dataclass
class LegInfo:
    """Information for a single leg of a triangular arbitrage cycle."""

    pair: str
    side: Literal["buy", "sell"]
    price_used: float
    price_source: str
    vwap_levels: int
    slippage_pct: float
    fee_pct: float
    notional_quote: float
    latency_ms: int


@dataclass
class BreakevenLine:
    """Single breakeven calculation result with WHY audit format."""

    gross_pct: float
    fees_pct: float
    slip_pct: float
    gas_pct: float
    threshold_pct: float
    net_pct: float

    def as_why(self) -> str:
        """Return exactly one WHY audit line per decision."""
        return (
            f"WHY breakeven_gross={self.gross_pct:.2f}% "
            f"(fees={self.fees_pct:.2f}% "
            f"slippage={self.slip_pct:.2f}% "
            f"gas={self.gas_pct:.2f}% "
            f"threshold={self.threshold_pct:.2f}%)"
        )


class BreakevenGuard:
    """
    Validates profitability math at every decision point.

    Ensures executable prices, per-leg accounting, correct gas normalization,
    and strict breakeven inequality.
    """

    def __init__(self, max_leg_latency_ms: int = 750):
        """
        Initialize breakeven guard.

        Args:
            max_leg_latency_ms: Maximum allowed latency per leg in milliseconds
        """
        self.max_leg_latency_ms = max_leg_latency_ms

    def compute(
        self,
        legs: Sequence[LegInfo],
        gross_pct: float,
        gas_units: int,
        gas_price_quote: float,
        total_notional_quote: float,
        threshold_pct: float,
    ) -> BreakevenLine:
        """
        Compute breakeven line with all invariants enforced.

        Args:
            legs: Sequence of LegInfo for the arbitrage cycle
            gross_pct: Gross profit percentage before costs
            gas_units: Gas units consumed
            gas_price_quote: Gas price in quote currency
            total_notional_quote: Total notional in quote currency
            threshold_pct: Minimum threshold percentage

        Returns:
            BreakevenLine with validated calculations

        Raises:
            ValueError: If executable price validation fails or latency exceeded
            AssertionError: If breakeven inequality is violated
        """
        # 1. Validate executable prices and latency
        for leg in legs:
            expected_source = "ask" if leg.side == "buy" else "bid"
            if leg.price_source != expected_source:
                raise ValueError(
                    f"Leg {leg.pair} {leg.side} must use {expected_source} "
                    f"but used {leg.price_source}"
                )

            if leg.latency_ms > self.max_leg_latency_ms:
                raise ValueError(
                    f"Leg {leg.pair} latency {leg.latency_ms}ms "
                    f"exceeds max {self.max_leg_latency_ms}ms"
                )

            if leg.notional_quote <= 0:
                raise ValueError(
                    f"Leg {leg.pair} notional_quote must be positive, "
                    f"got {leg.notional_quote}"
                )

        # 2. Sum per-leg fees and slippage
        fees_pct = sum(leg.fee_pct for leg in legs)
        slip_pct = sum(leg.slippage_pct for leg in legs)

        # 3. Compute gas percentage with correct normalization
        if total_notional_quote > 0:
            gas_pct = 100.0 * gas_units * gas_price_quote / total_notional_quote
        else:
            gas_pct = 0.0

        # 4. Compute net and validate breakeven inequality
        threshold_pct_clamped = max(0.0, threshold_pct)
        net_pct = gross_pct - fees_pct - slip_pct - gas_pct - threshold_pct_clamped

        # Strict breakeven inequality check
        if net_pct > 0:
            total_costs = fees_pct + slip_pct + gas_pct + threshold_pct_clamped
            if not (gross_pct > total_costs):
                raise AssertionError(
                    f"Breakeven inequality violated: "
                    f"net_pct={net_pct:.4f}% > 0 but "
                    f"gross_pct={gross_pct:.4f}% <= "
                    f"total_costs={total_costs:.4f}%"
                )

        # 5. Return breakeven line
        return BreakevenLine(
            gross_pct=gross_pct,
            fees_pct=fees_pct,
            slip_pct=slip_pct,
            gas_pct=gas_pct,
            threshold_pct=threshold_pct_clamped,
            net_pct=net_pct,
        )
