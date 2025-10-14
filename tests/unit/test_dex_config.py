"""
Unit tests for dex/config.py

Verifies that configuration loading and safety margin parsing work correctly.
"""

import unittest

from dex.config import DexConfig


class TestDexConfigSafetyMargin(unittest.TestCase):
    """Test safety margin configuration parsing."""

    def test_price_safety_margin_pct_from_config(self):
        """Test that price_safety_margin_pct is parsed correctly."""
        config_dict = {
            "rpc_url": "https://mainnet.base.org",
            "usd_token": "USDC",
            "price_safety_margin_pct": 0.02,
            "tokens": {"USDC": {"address": "0x123", "decimals": 6}},
            "dexes": [
                {
                    "name": "test_dex",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "USDC/WETH",
                            "address": "0x456",
                            "base": "USDC",
                            "quote": "WETH",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_dict)

        # Should be exactly 0.02%
        self.assertEqual(config.price_safety_margin_pct, 0.02)

    def test_legacy_slippage_bps_conversion(self):
        """Test that legacy slippage_bps is converted to price_safety_margin_pct."""
        config_dict = {
            "rpc_url": "https://mainnet.base.org",
            "usd_token": "USDC",
            "slippage_bps": 5,  # 5 bps = 0.05%
            "tokens": {"USDC": {"address": "0x123", "decimals": 6}},
            "dexes": [
                {
                    "name": "test_dex",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "USDC/WETH",
                            "address": "0x456",
                            "base": "USDC",
                            "quote": "WETH",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_dict)

        # 5 bps should be converted to 0.05%
        self.assertEqual(config.price_safety_margin_pct, 0.05)

    def test_default_safety_margin(self):
        """Test that default safety margin is used when not specified."""
        config_dict = {
            "rpc_url": "https://mainnet.base.org",
            "usd_token": "USDC",
            # No safety margin specified
            "tokens": {"USDC": {"address": "0x123", "decimals": 6}},
            "dexes": [
                {
                    "name": "test_dex",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "USDC/WETH",
                            "address": "0x456",
                            "base": "USDC",
                            "quote": "WETH",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_dict)

        # Should default to 0.02% (2 bps)
        self.assertEqual(config.price_safety_margin_pct, 0.02)

    def test_apply_safety_per_leg_default(self):
        """Test that apply_safety_per_leg defaults to False."""
        config_dict = {
            "rpc_url": "https://mainnet.base.org",
            "usd_token": "USDC",
            "price_safety_margin_pct": 0.01,
            "tokens": {"USDC": {"address": "0x123", "decimals": 6}},
            "dexes": [
                {
                    "name": "test_dex",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "USDC/WETH",
                            "address": "0x456",
                            "base": "USDC",
                            "quote": "WETH",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_dict)

        # Should default to False
        self.assertEqual(config.apply_safety_per_leg, False)

    def test_apply_safety_per_leg_true(self):
        """Test that apply_safety_per_leg can be set to True."""
        config_dict = {
            "rpc_url": "https://mainnet.base.org",
            "usd_token": "USDC",
            "price_safety_margin_pct": 0.01,
            "apply_safety_per_leg": True,
            "tokens": {"USDC": {"address": "0x123", "decimals": 6}},
            "dexes": [
                {
                    "name": "test_dex",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "USDC/WETH",
                            "address": "0x456",
                            "base": "USDC",
                            "quote": "WETH",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_dict)

        # Should be True
        self.assertEqual(config.apply_safety_per_leg, True)

    def test_safety_bps_property(self):
        """Test that safety_bps property converts pct to bps correctly."""
        config_dict = {
            "rpc_url": "https://mainnet.base.org",
            "usd_token": "USDC",
            "price_safety_margin_pct": 0.02,
            "tokens": {"USDC": {"address": "0x123", "decimals": 6}},
            "dexes": [
                {
                    "name": "test_dex",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "USDC/WETH",
                            "address": "0x456",
                            "base": "USDC",
                            "quote": "WETH",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_dict)

        # 0.02% should be 2 bps
        self.assertAlmostEqual(config.safety_bps, 2.0, places=5)

    def test_safety_reduces_net_by_exact_amount(self):
        """Test that configured safety reduces net profit by exact amount."""
        from decimal import Decimal

        from dex.opportunity_math import compute_opportunity_breakdown

        # Configure 0.01% safety
        # Compute breakdown with this safety
        bd = compute_opportunity_breakdown(
            gross_bps=125,  # 1.25%
            fee_bps=90,  # 0.90%
            safety_bps=1,  # 0.01% configured safety
            gas_usd=1.80,
            trade_amount_usd=1000,
        )

        # Net should be exactly:
        # 1.25% - 0.90% - 0.01% - 0.18% = 0.16%
        expected_net_pct = Decimal("0.16")
        self.assertEqual(round(bd.net_pct, 2), expected_net_pct)

        # Safety should be exactly 0.01%
        expected_safety_pct = Decimal("0.01")
        self.assertEqual(round(bd.safety_pct, 3), expected_safety_pct)


if __name__ == "__main__":
    unittest.main()
