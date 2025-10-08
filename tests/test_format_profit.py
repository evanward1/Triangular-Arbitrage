#!/usr/bin/env python3
"""
Unit tests for the format_profit utility function.

Tests the format_profit function which converts decimal profit values
to formatted percentage strings.
"""

import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triangular_arbitrage.utils import format_profit  # noqa: E402


class TestFormatProfit(unittest.TestCase):
    """Test suite for the format_profit function."""

    def test_positive_profit(self):
        """Test formatting of positive profit values."""
        self.assertEqual(format_profit(0.0123), "+1.23%")
        self.assertEqual(format_profit(0.05), "+5.00%")
        self.assertEqual(format_profit(0.1), "+10.00%")
        self.assertEqual(format_profit(0.999), "+99.90%")
        self.assertEqual(format_profit(1.0), "+100.00%")
        self.assertEqual(format_profit(2.5), "+250.00%")

    def test_negative_profit(self):
        """Test formatting of negative profit (loss) values."""
        self.assertEqual(format_profit(-0.0123), "-1.23%")
        self.assertEqual(format_profit(-0.05), "-5.00%")
        self.assertEqual(format_profit(-0.1), "-10.00%")
        self.assertEqual(format_profit(-0.999), "-99.90%")
        self.assertEqual(format_profit(-1.0), "-100.00%")

    def test_zero_profit(self):
        """Test formatting of zero profit."""
        self.assertEqual(format_profit(0.0), "+0.00%")
        self.assertEqual(format_profit(0), "+0.00%")

    def test_small_values(self):
        """Test formatting of very small profit values."""
        self.assertEqual(format_profit(0.0001), "+0.01%")
        self.assertEqual(format_profit(0.00001), "+0.00%")  # Rounds to 2 decimal places
        self.assertEqual(format_profit(-0.0001), "-0.01%")
        self.assertEqual(format_profit(-0.00001), "-0.00%")

    def test_rounding(self):
        """Test that values are properly rounded to 2 decimal places."""
        self.assertEqual(format_profit(0.01234), "+1.23%")  # Rounds down
        self.assertEqual(
            format_profit(0.01235), "+1.23%"
        )  # Python rounds to nearest even
        self.assertEqual(
            format_profit(0.01245), "+1.24%"
        )  # Python rounds to nearest even
        self.assertEqual(format_profit(0.01236), "+1.24%")  # Rounds up
        self.assertEqual(format_profit(-0.01234), "-1.23%")  # Rounds toward zero
        self.assertEqual(
            format_profit(-0.01235), "-1.23%"
        )  # Python rounds to nearest even

    def test_edge_cases(self):
        """Test edge cases and boundary values."""
        # Very large values
        self.assertEqual(format_profit(10.0), "+1000.00%")
        self.assertEqual(format_profit(100.0), "+10000.00%")

        # Values near zero
        self.assertEqual(format_profit(0.00004), "+0.00%")  # Less than 0.005%
        self.assertEqual(format_profit(0.00005), "+0.01%")  # Exactly 0.005%, rounds up
        self.assertEqual(format_profit(-0.00004), "-0.00%")
        self.assertEqual(format_profit(-0.00005), "-0.01%")

    def test_type_handling(self):
        """Test that the function handles different numeric types."""
        # Integer input
        self.assertEqual(format_profit(1), "+100.00%")
        self.assertEqual(format_profit(-1), "-100.00%")

        # Float input (already tested above, but explicit here)
        self.assertEqual(format_profit(0.5), "+50.00%")

        # Should work with any numeric type
        from decimal import Decimal

        self.assertEqual(format_profit(Decimal("0.0123")), "+1.23%")

    def test_sign_consistency(self):
        """Test that positive values always have '+' and negatives have '-'."""
        # Positive values should always have '+'
        for value in [0.0, 0.001, 0.01, 0.1, 1.0]:
            result = format_profit(value)
            self.assertTrue(
                result.startswith("+"), f"Expected '+' prefix for {value}, got {result}"
            )

        # Negative values should always have '-'
        for value in [-0.001, -0.01, -0.1, -1.0]:
            result = format_profit(value)
            self.assertTrue(
                result.startswith("-"), f"Expected '-' prefix for {value}, got {result}"
            )

    def test_percentage_suffix(self):
        """Test that all results end with '%'."""
        test_values = [0.0, 0.01, -0.01, 1.0, -1.0, 0.12345, -0.54321]
        for value in test_values:
            result = format_profit(value)
            self.assertTrue(
                result.endswith("%"), f"Expected '%' suffix for {value}, got {result}"
            )

    def test_decimal_places(self):
        """Test that results always have exactly 2 decimal places."""
        test_values = [0.0, 0.1, 0.01, 0.001, 1.0, 10.0, -0.5, -0.123456]
        for value in test_values:
            result = format_profit(value)
            # Remove sign and '%', then check decimal places
            numeric_part = result.lstrip("+-").rstrip("%")
            if "." in numeric_part:
                decimal_part = numeric_part.split(".")[1]
                self.assertEqual(
                    len(decimal_part),
                    2,
                    f"Expected 2 decimal places for {value}, got {result}",
                )


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
