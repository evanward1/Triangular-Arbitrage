"""
Single source of truth for opportunity math calculations.

All profit calculations use Decimal for precision and consistent rounding.
This module is the ONLY place where net profit percentages are computed.
Both the executor logger and the UI serializer MUST use this module.

Conversion policy:
- Internal: Decimal with 50 digits precision
- Output: Round to 2 decimal places for percent, 2 for USD
- No inline *100 or /10000 - use pct_to_bps() and bps_to_pct()
"""

import logging
from dataclasses import dataclass
from decimal import Decimal, getcontext

# Set high precision for all decimal operations
getcontext().prec = 50

logger = logging.getLogger(__name__)


# ============================================================================
# Conversion helpers (ONLY place to convert between percent and bps)
# ============================================================================


def pct_to_bps(pct: Decimal) -> Decimal:
    """Convert percent to basis points. 0.15% -> 15 bps"""
    return pct * Decimal("100")


def bps_to_pct(bps: Decimal) -> Decimal:
    """Convert basis points to percent. 15 bps -> 0.15%"""
    return bps / Decimal("100")


def round_to_bps(value: Decimal) -> int:
    """Round a bps value to integer bps for comparison."""
    return int(value.quantize(Decimal("1")))


def round_cents(value: Decimal) -> Decimal:
    """Round USD value to nearest cent."""
    return value.quantize(Decimal("0.01"))


# ============================================================================
# Opportunity breakdown dataclass
# ============================================================================


@dataclass(frozen=True)
class OpportunityBreakdown:
    """
    Complete breakdown of an arbitrage opportunity.
    All percentages are stored as Decimal percent values (e.g., 0.15 for 0.15%).
    """

    # Inputs
    gross_pct: Decimal  # Gross profit before any costs
    fee_pct: Decimal  # Total trading fees
    safety_pct: Decimal  # Price safety margin (slippage buffer)
    gas_usd: Decimal  # Gas cost in USD
    gas_pct: Decimal  # Gas cost as percent of trade size

    # Derived outputs
    net_pct: Decimal  # Net profit after all costs
    pnl_usd: Decimal  # P&L in USD for given trade size

    # Metadata
    trade_amount_usd: Decimal

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "gross_pct": float(self.gross_pct),
            "fee_pct": float(self.fee_pct),
            "safety_pct": float(self.safety_pct),
            "gas_usd": float(self.gas_usd),
            "gas_pct": float(self.gas_pct),
            "net_pct": float(self.net_pct),
            "pnl_usd": float(self.pnl_usd),
            "trade_amount_usd": float(self.trade_amount_usd),
        }

    def format_log(self) -> str:
        """Format for consistent logging (both executor and UI)."""
        return (
            f"Net {self.net_pct:.3f}% "
            f"(Gross {self.gross_pct:.3f}% - "
            f"Fees {self.fee_pct:.3f}% - "
            f"Safety {self.safety_pct:.3f}% - "
            f"Gas {self.gas_pct:.3f}%) "
            f"= ${self.pnl_usd:.2f} @ ${self.trade_amount_usd:.0f}"
        )


# ============================================================================
# Core computation function (SINGLE SOURCE OF TRUTH)
# ============================================================================


def compute_opportunity_breakdown(
    gross_bps: float,
    fee_bps: float,
    safety_bps: float,
    gas_usd: float,
    trade_amount_usd: float,
) -> OpportunityBreakdown:
    """
    Compute complete opportunity breakdown from raw inputs.

    This is the ONLY function that computes net_pct and pnl_usd.
    All other code must call this function.

    Args:
        gross_bps: Gross profit in basis points (e.g., 125 for 1.25%)
        fee_bps: Total fees in basis points (e.g., 90 for 0.90%)
        safety_bps: Safety margin in basis points (e.g., 2 for 0.02%)
        gas_usd: Gas cost in USD (e.g., 1.80)
        trade_amount_usd: Trade size in USD (e.g., 1000)

    Returns:
        OpportunityBreakdown with all fields computed

    Example:
        >>> bd = compute_opportunity_breakdown(125, 90, 2, 1.80, 1000)
        >>> assert round(bd.net_pct, 3) == 0.150  # Net 0.150%
        >>> assert round(bd.pnl_usd, 2) == 1.50   # PnL $1.50
    """
    # Convert all inputs to Decimal for precision
    gross_bps_d = Decimal(str(gross_bps))
    fee_bps_d = Decimal(str(fee_bps))
    safety_bps_d = Decimal(str(safety_bps))
    gas_usd_d = Decimal(str(gas_usd))
    trade_amount_usd_d = Decimal(str(trade_amount_usd))

    # Convert bps to percent
    gross_pct = bps_to_pct(gross_bps_d)
    fee_pct = bps_to_pct(fee_bps_d)
    safety_pct = bps_to_pct(safety_bps_d)

    # Compute gas as percent of trade size
    if trade_amount_usd_d > 0:
        gas_pct = (gas_usd_d / trade_amount_usd_d) * Decimal("100")
    else:
        gas_pct = Decimal("0")

    # Compute net percent (SINGLE SOURCE OF TRUTH)
    net_pct = gross_pct - fee_pct - safety_pct - gas_pct

    # Compute PnL in USD (SINGLE SOURCE OF TRUTH)
    pnl_usd = (net_pct / Decimal("100")) * trade_amount_usd_d

    return OpportunityBreakdown(
        gross_pct=gross_pct,
        fee_pct=fee_pct,
        safety_pct=safety_pct,
        gas_usd=gas_usd_d,
        gas_pct=gas_pct,
        net_pct=net_pct,
        pnl_usd=pnl_usd,
        trade_amount_usd=trade_amount_usd_d,
    )


# ============================================================================
# Validation and assertion helpers
# ============================================================================


def assert_breakdown_equals(
    bd1: OpportunityBreakdown,
    bd2: OpportunityBreakdown,
    tolerance_bps: int = 1,
    tolerance_usd: Decimal = Decimal("0.01"),
) -> None:
    """
    Assert two breakdowns are equivalent within tolerance.

    Used to verify that executor logs and UI displays match.

    Args:
        bd1: First breakdown
        bd2: Second breakdown
        tolerance_bps: Maximum difference in bps (default 1 bps)
        tolerance_usd: Maximum difference in USD (default $0.01)

    Raises:
        AssertionError: If breakdowns differ beyond tolerance
    """
    # Compare net percent
    net_bps_1 = pct_to_bps(bd1.net_pct)
    net_bps_2 = pct_to_bps(bd2.net_pct)
    diff_bps = abs(net_bps_1 - net_bps_2)

    assert diff_bps <= Decimal(tolerance_bps), (
        f"Net percent mismatch: {bd1.net_pct:.4f}% vs {bd2.net_pct:.4f}% "
        f"(diff: {diff_bps:.2f} bps)"
    )

    # Compare PnL USD
    diff_usd = abs(bd1.pnl_usd - bd2.pnl_usd)
    assert diff_usd <= tolerance_usd, (
        f"PnL USD mismatch: ${bd1.pnl_usd:.2f} vs ${bd2.pnl_usd:.2f} "
        f"(diff: ${diff_usd:.2f})"
    )


def validate_example_snapshot():
    """
    Validate the snapshot case from the requirements.

    Snapshot:
    - Gross: 1.25% (125 bps)
    - Fees: 0.90% (90 bps, 3 legs × 0.30%)
    - Safety: 0.02% (2 bps, doubled in display bug)
    - Gas: $1.80 at $1000 size = 0.18%
    - Expected net: 0.15% (15 bps)
    - Expected PnL: $1.50
    """
    bd = compute_opportunity_breakdown(
        gross_bps=125,
        fee_bps=90,
        safety_bps=2,  # Configured value (0.02%), not doubled
        gas_usd=1.80,
        trade_amount_usd=1000,
    )

    # Assertions from requirements
    assert round(bd.net_pct, 3) == Decimal(
        "0.150"
    ), f"Net percent should be 0.150%, got {bd.net_pct:.4f}%"
    assert round(bd.pnl_usd, 2) == Decimal(
        "1.50"
    ), f"PnL should be $1.50, got ${bd.pnl_usd:.2f}"
    assert round(bd.safety_pct, 3) == Decimal(
        "0.02"
    ), f"Safety should be 0.02%, got {bd.safety_pct:.4f}%"

    # Breakeven check from requirements
    breakeven = bd.fee_pct + bd.safety_pct + bd.gas_pct
    expected_breakeven = Decimal("1.10")  # 0.90 + 0.02 + 0.18
    assert (
        round(breakeven, 2) == expected_breakeven
    ), f"Breakeven should be {expected_breakeven}%, got {breakeven:.4f}%"

    logger.info(f"✓ Snapshot validation passed: {bd.format_log()}")


if __name__ == "__main__":
    # Run validation on import to catch regressions
    validate_example_snapshot()
