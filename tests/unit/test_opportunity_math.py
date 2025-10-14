"""
Unit tests for dex/opportunity_math.py

Verifies that the single source of truth computes correct values
and that logging/UI serialization produce identical results.
"""

import unittest
from decimal import Decimal

from dex.opportunity_math import (
    assert_breakdown_equals,
    bps_to_pct,
    compute_opportunity_breakdown,
    pct_to_bps,
    round_cents,
    round_to_bps,
    validate_example_snapshot,
)


class TestConversionHelpers(unittest.TestCase):
    """Test bps/percent conversion helpers."""

    def test_pct_to_bps(self):
        """Test percent to basis points conversion."""
        self.assertEqual(pct_to_bps(Decimal("0.15")), Decimal("15"))
        self.assertEqual(pct_to_bps(Decimal("1.00")), Decimal("100"))
        self.assertEqual(pct_to_bps(Decimal("0.01")), Decimal("1"))

    def test_bps_to_pct(self):
        """Test basis points to percent conversion."""
        self.assertEqual(bps_to_pct(Decimal("15")), Decimal("0.15"))
        self.assertEqual(bps_to_pct(Decimal("100")), Decimal("1.00"))
        self.assertEqual(bps_to_pct(Decimal("1")), Decimal("0.01"))

    def test_round_to_bps(self):
        """Test rounding to integer basis points."""
        self.assertEqual(round_to_bps(Decimal("15.4")), 15)
        self.assertEqual(round_to_bps(Decimal("15.6")), 16)

    def test_round_cents(self):
        """Test rounding to nearest cent."""
        self.assertEqual(round_cents(Decimal("1.504")), Decimal("1.50"))
        # Note: Decimal uses banker's rounding (round half to even)
        self.assertEqual(
            round_cents(Decimal("1.505")), Decimal("1.50")
        )  # Rounds to even


class TestOpportunityBreakdown(unittest.TestCase):
    """Test compute_opportunity_breakdown function."""

    def test_snapshot_case(self):
        """Test the exact snapshot case from requirements."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Net percent should be 0.150%
        self.assertAlmostEqual(float(bd.net_pct), 0.150, places=3)

        # PnL should be $1.50
        self.assertAlmostEqual(float(bd.pnl_usd), 1.50, places=2)

        # Safety should be 0.02% (not doubled)
        self.assertAlmostEqual(float(bd.safety_pct), 0.02, places=3)

        # Gas should be 0.18%
        self.assertAlmostEqual(float(bd.gas_pct), 0.18, places=2)

        # Breakeven check
        breakeven = bd.fee_pct + bd.safety_pct + bd.gas_pct
        self.assertAlmostEqual(float(breakeven), 1.10, places=2)

    def test_zero_trade_amount(self):
        """Test handling of zero trade amount."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=0,
        )

        # Gas percent should be zero when trade amount is zero
        self.assertEqual(float(bd.gas_pct), 0.0)

    def test_negative_net(self):
        """Test that negative net profit is computed correctly."""
        bd = compute_opportunity_breakdown(
            gross_bps=50,  # Low gross
            fee_bps=90,
            safety_bps=10,
            gas_usd=5.0,
            trade_amount_usd=1000,
        )

        # Net should be negative
        self.assertLess(float(bd.net_pct), 0)

        # PnL should be negative
        self.assertLess(float(bd.pnl_usd), 0)

    def test_high_precision(self):
        """Test that high precision is maintained."""
        bd = compute_opportunity_breakdown(
            gross_bps=125.123456,
            fee_bps=90.654321,
            safety_bps=2.111111,
            gas_usd=1.802345,
            trade_amount_usd=1000.99,
        )

        # Verify that computation preserves reasonable precision
        # Net = (gross - fee - safety) / 100 - gas_pct
        # Net = (125.123456 - 90.654321 - 2.111111) / 100 - (1.802345 / 1000.99)
        gross_minus_costs_bps = (
            Decimal("125.123456") - Decimal("90.654321") - Decimal("2.111111")
        )
        gross_minus_costs_pct = gross_minus_costs_bps / Decimal("100")
        gas_pct = (Decimal("1.802345") / Decimal("1000.99")) * Decimal("100")
        expected_net_pct = gross_minus_costs_pct - gas_pct

        # Should match within reasonable floating point tolerance
        self.assertAlmostEqual(float(bd.net_pct), float(expected_net_pct), places=4)

    def test_to_dict_serialization(self):
        """Test that to_dict produces valid JSON-serializable output."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        d = bd.to_dict()

        # All values should be floats
        self.assertIsInstance(d["gross_pct"], float)
        self.assertIsInstance(d["fee_pct"], float)
        self.assertIsInstance(d["safety_pct"], float)
        self.assertIsInstance(d["gas_usd"], float)
        self.assertIsInstance(d["gas_pct"], float)
        self.assertIsInstance(d["net_pct"], float)
        self.assertIsInstance(d["pnl_usd"], float)
        self.assertIsInstance(d["trade_amount_usd"], float)

    def test_format_log(self):
        """Test that format_log produces readable output."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        log_str = bd.format_log()

        # Should contain all key components
        self.assertIn("Net 0.150%", log_str)
        self.assertIn("Gross 1.250%", log_str)
        self.assertIn("Fees 0.900%", log_str)
        self.assertIn("Safety 0.020%", log_str)
        self.assertIn("Gas 0.180%", log_str)
        self.assertIn("$1.50", log_str)
        self.assertIn("$1000", log_str)


class TestAssertionHelpers(unittest.TestCase):
    """Test assertion helpers for verifying consistency."""

    def test_assert_breakdown_equals_passes(self):
        """Test that identical breakdowns pass assertion."""
        bd1 = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )
        bd2 = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Should not raise
        assert_breakdown_equals(bd1, bd2)

    def test_assert_breakdown_equals_fails_on_mismatch(self):
        """Test that mismatched breakdowns fail assertion."""
        bd1 = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )
        bd2 = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=3.55,  # Different gas -> different net
            trade_amount_usd=1000,
        )

        # Should raise AssertionError
        with self.assertRaises(AssertionError):
            assert_breakdown_equals(bd1, bd2, tolerance_bps=1)


class TestSnapshotValidation(unittest.TestCase):
    """Test the validate_example_snapshot function."""

    def test_validate_example_snapshot(self):
        """Test that example snapshot validation passes."""
        # Should not raise
        validate_example_snapshot()


class TestAcceptanceChecks(unittest.TestCase):
    """Acceptance tests from requirements."""

    def test_acceptance_check_1_net_percent(self):
        """Acceptance check 1: Executor logs Net 0.150% for snapshot case."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Net percent must be 0.150%
        self.assertEqual(round(bd.net_pct, 3), Decimal("0.150"))

    def test_acceptance_check_1_pnl_usd(self):
        """Acceptance check 1: Executor logs PnL $1.50 for snapshot case."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # PnL must be $1.50
        self.assertEqual(round(bd.pnl_usd, 2), Decimal("1.50"))

    def test_acceptance_check_2_ui_matches_executor(self):
        """Acceptance check 2: UI shows same values as executor."""
        # Simulate executor computing breakdown
        executor_bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Simulate UI computing breakdown (same inputs)
        ui_bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Must be identical
        assert_breakdown_equals(executor_bd, ui_bd)

    def test_acceptance_check_3_safety_margin(self):
        """Acceptance check 3: Safety margin shows configured value (0.01% not 0.02%)."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=1,  # Configured as 1 bps = 0.01%
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Safety must be 0.01%
        self.assertEqual(round(bd.safety_pct, 3), Decimal("0.01"))

    def test_acceptance_check_4_breakeven(self):
        """Acceptance check 4: Breakeven equals sum of costs."""
        bd = compute_opportunity_breakdown(
            gross_bps=125,
            fee_bps=90,
            safety_bps=2,
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Breakeven = fees + safety + gas
        breakeven = bd.fee_pct + bd.safety_pct + bd.gas_pct
        expected_breakeven = Decimal("1.10")  # 0.90 + 0.02 + 0.18

        self.assertEqual(round(breakeven, 2), expected_breakeven)


if __name__ == "__main__":
    unittest.main()
