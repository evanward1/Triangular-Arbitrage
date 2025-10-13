"""
Test solver math and numeric calculations for DEX MEV arbitrage.
"""

import unittest
from decimal import Decimal
from unittest.mock import Mock

from triangular_arbitrage.dex_mev.config_schema import (
    DEXMEVConfig,
    RouteConfig,
    TokenConfig,
)
from triangular_arbitrage.dex_mev.dex_client import DEXClient
from triangular_arbitrage.dex_mev.solver import ArbitrageSolver


class TestSolverMath(unittest.TestCase):
    """Test cases for arbitrage solver mathematical calculations."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock config
        self.config = DEXMEVConfig(
            network="ethereum",
            chain_id=1,
            rpc_url_env="TEST_RPC",
            rpc_primary="",
            rpc_backups=[],
            private_key_env="TEST_KEY",
            base_asset="USDC",
            min_profit_bps=1,  # Very low threshold for tests
            max_slippage_bps=50,
            per_leg_slippage_bps=50,
            cycle_slippage_bps=100,
            max_base_fee_gwei=30,
            max_priority_fee_gwei=2,
            gas_limit_cap=500000,
            private_tx_enabled=False,
            mev_relay="",
            simulation_rpc="",
            exact_in=True,
            use_bundle=False,
            routes=[
                RouteConfig(
                    base="USDC",
                    mid="WETH",
                    alt="USDT",
                    dex_name="Uniswap",
                    pool_addresses=["0x123", "0x456", "0x789"],
                )
            ],
            tokens={
                "USDC": TokenConfig(
                    "USDC", "0xA0b86a33E6417A4b4c0CbC383c5Ef3B0CcC7C9b0", 6
                ),
                "WETH": TokenConfig(
                    "WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 18
                ),
                "USDT": TokenConfig(
                    "USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6
                ),
            },
            use_flashbots=True,
            coinbase_tip_gwei=2,
        )

        # Create fake client
        self.fake_client = Mock(spec=DEXClient)
        self.fake_client.paper_mode = True
        self.fake_client.estimate_swap_output.side_effect = [
            Decimal("0.4985"),  # USDC -> WETH (1000 USDC = ~0.5 ETH with 0.3% fee)
            Decimal("1000.5"),  # WETH -> USDT (0.4985 ETH = ~1000.5 USDT)
            Decimal(
                "1025.0"
            ),  # USDT -> USDC (1000.5 USDT = 1025 USDC) - Creates ~25 bps gross profit
        ]
        self.fake_client.get_gas_price.return_value = 20

        # Create solver
        self.solver = ArbitrageSolver(self.config, self.fake_client)

    def test_solver_finds_opportunities(self):
        """Test that solver finds arbitrage opportunities."""
        opportunities = self.solver.find_arbitrage_opportunities(Decimal("1000"))

        self.assertGreater(
            len(opportunities), 0, "Should find at least one opportunity"
        )

    def test_opportunity_numeric_fields(self):
        """Test that opportunities have correct numeric field types."""
        opportunities = self.solver.find_arbitrage_opportunities(Decimal("1000"))

        self.assertGreater(len(opportunities), 0, "Need opportunities to test")

        opp = opportunities[0]

        # Test that gross_bps and net_bps are floats
        self.assertIsInstance(opp.gross_bps, float, "gross_bps should be float")
        self.assertIsInstance(opp.net_bps, float, "net_bps should be float")

        # Test that numeric fields exist and have reasonable values
        self.assertIsNotNone(opp.gross_bps, "gross_bps should exist")
        self.assertIsNotNone(opp.net_bps, "net_bps should exist")
        self.assertIsNotNone(opp.gas_cost_wei, "gas_cost_wei should exist")
        self.assertIsNotNone(opp.notional_amount, "notional_amount should exist")

        # Test types of other fields
        self.assertIsInstance(opp.gas_cost_wei, int, "gas_cost_wei should be int")
        self.assertIsInstance(
            opp.notional_amount, Decimal, "notional_amount should be Decimal"
        )
        self.assertIsInstance(opp.amounts, list, "amounts should be list")
        self.assertIsInstance(opp.path, list, "path should be list")

        # Test that amounts are all Decimals
        for amount in opp.amounts:
            self.assertIsInstance(amount, Decimal, f"Amount {amount} should be Decimal")

        # Test that path has correct structure
        self.assertEqual(
            len(opp.path), 4, "Path should have 4 tokens (base->mid->alt->base)"
        )
        self.assertEqual(
            opp.path[0], opp.path[3], "Path should start and end with same token"
        )

    def test_profit_calculation_logic(self):
        """Test that profit calculations make sense."""
        opportunities = self.solver.find_arbitrage_opportunities(Decimal("1000"))

        self.assertGreater(len(opportunities), 0, "Need opportunities to test")

        opp = opportunities[0]

        # With our mock data: 1000 USDC -> 0.4985 ETH -> 1000.5 USDT -> 1025 USDC
        # Gross profit should be 25 USDC = 250 bps on 1000 USDC
        expected_gross_bps = 250.0  # (1025 - 1000) / 1000 * 10000

        self.assertAlmostEqual(
            opp.gross_bps,
            expected_gross_bps,
            places=1,
            msg="Gross profit calculation should match expected",
        )

        # Net profit should be less than gross (due to slippage and gas)
        self.assertLess(
            opp.net_bps, opp.gross_bps, "Net profit should be less than gross profit"
        )


if __name__ == "__main__":
    unittest.main()
