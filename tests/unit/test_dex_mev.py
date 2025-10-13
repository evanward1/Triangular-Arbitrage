"""
Comprehensive unit tests for DEX MEV arbitrage module.

Tests cover:
- Uniswap V2 output calculation
- Slippage cap enforcement
- Monotonic output behavior
- Breakeven calculation
- Gas cost estimation
- Property-based tests
"""

import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

try:
    from hypothesis import given
    from hypothesis import strategies as st

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    st = None

    # Create dummy decorators if hypothesis not available
    def given(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


from triangular_arbitrage.dex_mev.config_schema import (
    DEXMEVConfig,
    RouteConfig,
    TokenConfig,
)
from triangular_arbitrage.dex_mev.dex_client import DEXClient
from triangular_arbitrage.dex_mev.solver import ArbitrageSolver


class TestUniswapV2Math(unittest.TestCase):
    """Test Uniswap V2 constant product formula calculations."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = self._create_test_config()
        self.dex_client = DEXClient(self.config, paper_mode=True)

    def _create_test_config(self) -> DEXMEVConfig:
        """Create a minimal test configuration."""
        return DEXMEVConfig(
            network="ethereum",
            chain_id=1,
            rpc_url_env="TEST_RPC",
            rpc_primary="",
            rpc_backups=[],
            private_key_env="TEST_KEY",
            base_asset="USDC",
            min_profit_bps=10,
            max_slippage_bps=50,
            per_leg_slippage_bps=50,
            cycle_slippage_bps=100,
            max_base_fee_gwei=50,
            max_priority_fee_gwei=2,
            gas_limit_cap=500000,
            private_tx_enabled=False,
            mev_relay="",
            simulation_rpc="",
            exact_in=True,
            use_bundle=False,
            routes=[],
            tokens={},
            use_flashbots=False,
            coinbase_tip_gwei=0,
        )

    def test_v2_output_basic(self):
        """Test basic Uniswap V2 output calculation."""
        # Given: 1M USDC reserve, 500 WETH reserve, 30 bps fee
        reserve_in = Decimal("1000000")
        reserve_out = Decimal("500")
        amount_in = Decimal("1000")  # 1k USDC in
        fee_bps = 30

        amount_out = self.dex_client.calculate_v2_output(
            amount_in, reserve_in, reserve_out, fee_bps
        )

        # Expected: roughly 0.4985 WETH out (with 0.3% fee)
        # Formula: (1000 * 0.997 * 500) / (1000000 + 1000 * 0.997) = 0.4985...
        expected = Decimal("0.4985")
        self.assertAlmostEqual(float(amount_out), float(expected), places=3)

    def test_v2_output_zero_input(self):
        """Test that zero input returns zero output."""
        amount_out = self.dex_client.calculate_v2_output(
            Decimal("0"), Decimal("1000000"), Decimal("500"), 30
        )
        self.assertEqual(amount_out, Decimal("0"))

    def test_v2_output_zero_reserves(self):
        """Test that zero reserves return zero output."""
        amount_out = self.dex_client.calculate_v2_output(
            Decimal("1000"), Decimal("0"), Decimal("500"), 30
        )
        self.assertEqual(amount_out, Decimal("0"))

        amount_out = self.dex_client.calculate_v2_output(
            Decimal("1000"), Decimal("1000000"), Decimal("0"), 30
        )
        self.assertEqual(amount_out, Decimal("0"))

    def test_v2_output_is_monotonic(self):
        """Test that output increases monotonically with input."""
        reserve_in = Decimal("1000000")
        reserve_out = Decimal("500")
        fee_bps = 30

        amounts_in = [Decimal(str(x)) for x in [100, 500, 1000, 5000, 10000]]
        amounts_out = [
            self.dex_client.calculate_v2_output(amt, reserve_in, reserve_out, fee_bps)
            for amt in amounts_in
        ]

        # Each output should be greater than the previous
        for i in range(1, len(amounts_out)):
            self.assertGreater(
                amounts_out[i],
                amounts_out[i - 1],
                f"Output not monotonic: {amounts_out[i]} <= {amounts_out[i-1]}",
            )

    def test_v2_output_respects_fee(self):
        """Test that higher fees result in lower output."""
        reserve_in = Decimal("1000000")
        reserve_out = Decimal("500")
        amount_in = Decimal("1000")

        # Calculate outputs with different fees
        out_30bps = self.dex_client.calculate_v2_output(
            amount_in, reserve_in, reserve_out, 30
        )
        out_100bps = self.dex_client.calculate_v2_output(
            amount_in, reserve_in, reserve_out, 100
        )

        # Higher fee should give less output
        self.assertGreater(out_30bps, out_100bps)

    def test_v2_input_for_output(self):
        """Test calculation of required input for desired output."""
        reserve_in = Decimal("1000000")
        reserve_out = Decimal("500")
        amount_out = Decimal("1")  # Want 1 WETH out
        fee_bps = 30

        amount_in = self.dex_client.calculate_v2_input_for_output(
            amount_out, reserve_in, reserve_out, fee_bps
        )

        # Verify by calculating output from this input
        calculated_out = self.dex_client.calculate_v2_output(
            amount_in, reserve_in, reserve_out, fee_bps
        )

        # Should get approximately the desired output (within 0.01%)
        self.assertAlmostEqual(float(calculated_out), float(amount_out), delta=0.01)

    def test_v2_roundtrip_consistency(self):
        """Test that input->output->input calculation is consistent."""
        reserve_in = Decimal("1000000")
        reserve_out = Decimal("500")
        amount_in = Decimal("1000")
        fee_bps = 30

        # Calculate output from input
        amount_out = self.dex_client.calculate_v2_output(
            amount_in, reserve_in, reserve_out, fee_bps
        )

        # Calculate required input for that output
        calculated_in = self.dex_client.calculate_v2_input_for_output(
            amount_out, reserve_in, reserve_out, fee_bps
        )

        # Should get approximately the same input back
        self.assertAlmostEqual(float(calculated_in), float(amount_in), delta=1.0)


class TestSlippageEnforcement(unittest.TestCase):
    """Test slippage cap enforcement logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = DEXMEVConfig(
            network="ethereum",
            chain_id=1,
            rpc_url_env="TEST_RPC",
            rpc_primary="",
            rpc_backups=[],
            private_key_env="TEST_KEY",
            base_asset="USDC",
            min_profit_bps=10,
            max_slippage_bps=50,
            per_leg_slippage_bps=30,  # 30 bps per leg max
            cycle_slippage_bps=80,  # 80 bps total max
            max_base_fee_gwei=50,
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
                    "USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6
                ),
                "WETH": TokenConfig(
                    "WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 18
                ),
                "USDT": TokenConfig(
                    "USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6
                ),
            },
            use_flashbots=False,
            coinbase_tip_gwei=0,
        )

        self.fake_client = Mock(spec=DEXClient)
        self.fake_client.paper_mode = True
        self.fake_client.get_gas_price.return_value = 20
        self.solver = ArbitrageSolver(self.config, self.fake_client)

    def test_per_leg_slippage_calculation(self):
        """Test that per-leg slippage is calculated correctly."""
        amount_in = Decimal("1000")
        amount_out = Decimal("999")  # Small loss

        slippage = self.solver._calculate_per_leg_slippage(amount_in, amount_out)

        # Should return base slippage (5 bps) for this test
        self.assertGreater(slippage, 0)
        self.assertIsInstance(slippage, float)

    def test_route_rejected_if_per_leg_exceeds_cap(self):
        """Test that routes are rejected if any leg exceeds per-leg slippage cap."""
        # Mock high slippage on one leg
        with patch.object(
            self.solver, "_calculate_per_leg_slippage", return_value=100.0
        ):
            self.fake_client.estimate_swap_output.side_effect = [
                Decimal("0.5"),  # USDC -> WETH
                Decimal("1000"),  # WETH -> USDT
                Decimal("1020"),  # USDT -> USDC
            ]

            opportunity = self.solver._evaluate_route(
                self.config.routes[0], Decimal("1000")
            )

            # Should be rejected due to high slippage
            self.assertIsNone(opportunity)

    def test_route_rejected_if_cycle_exceeds_cap(self):
        """Test that routes are rejected if total slippage exceeds cycle cap."""
        # Mock moderate slippage per leg that adds up to exceed cycle cap
        with patch.object(
            self.solver, "_calculate_per_leg_slippage", return_value=35.0
        ):
            self.fake_client.estimate_swap_output.side_effect = [
                Decimal("0.5"),  # USDC -> WETH
                Decimal("1000"),  # WETH -> USDT
                Decimal("1020"),  # USDT -> USDC
            ]

            opportunity = self.solver._evaluate_route(
                self.config.routes[0], Decimal("1000")
            )

            # Should be rejected: 3 legs * 35 bps = 105 bps > 80 bps cap
            self.assertIsNone(opportunity)

    def test_route_accepted_within_caps(self):
        """Test that routes are accepted when slippage is within caps."""
        # Use a very low min profit threshold to ensure we pass breakeven checks
        self.config.min_profit_bps = 1  # 0.01% threshold

        # Mock low slippage
        with patch.object(
            self.solver, "_calculate_per_leg_slippage", return_value=20.0
        ):
            self.fake_client.estimate_swap_output.side_effect = [
                Decimal("0.5"),  # USDC -> WETH
                Decimal("1000"),  # WETH -> USDT
                Decimal("1030"),  # USDT -> USDC (3% gross profit to cover gas)
            ]

            opportunity = self.solver._evaluate_route(
                self.config.routes[0], Decimal("1000")
            )

            # Should be accepted: 3 legs * 20 bps = 60 bps < 80 bps cap
            # And each leg 20 bps < 30 bps per-leg cap
            self.assertIsNotNone(
                opportunity,
                "Route should be accepted with low slippage and good profit",
            )
            self.assertEqual(len(opportunity.per_leg_slippage_bps), 3)
            self.assertLessEqual(max(opportunity.per_leg_slippage_bps), 30)
            self.assertLessEqual(opportunity.total_slippage_bps, 80)


class TestBreakevenCalculation(unittest.TestCase):
    """Test breakeven and profit calculation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = DEXMEVConfig(
            network="ethereum",
            chain_id=1,
            rpc_url_env="TEST_RPC",
            rpc_primary="",
            rpc_backups=[],
            private_key_env="TEST_KEY",
            base_asset="USDC",
            min_profit_bps=10,
            max_slippage_bps=50,
            per_leg_slippage_bps=50,
            cycle_slippage_bps=100,
            max_base_fee_gwei=50,
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
                    "USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6
                ),
                "WETH": TokenConfig(
                    "WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 18
                ),
                "USDT": TokenConfig(
                    "USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6
                ),
            },
            use_flashbots=False,
            coinbase_tip_gwei=0,
        )

        self.fake_client = Mock(spec=DEXClient)
        self.fake_client.paper_mode = True
        self.fake_client.get_gas_price.return_value = 20
        self.solver = ArbitrageSolver(self.config, self.fake_client)

    def test_gas_cost_estimation_usd(self):
        """Test that gas cost is correctly estimated in USD."""
        gas_limit = 300000
        gas_price_gwei = 50
        eth_price = Decimal("2000")

        self.solver.eth_price_usd = eth_price
        gas_cost_usd = self.solver._estimate_gas_cost_usd(gas_limit, gas_price_gwei)

        # Expected: 300000 * 50 * 10^9 wei = 1.5 * 10^16 wei = 0.015 ETH
        # 0.015 ETH * $2000 = $30
        expected_cost = Decimal("30")
        self.assertAlmostEqual(float(gas_cost_usd), float(expected_cost), places=2)

    def test_breakeven_includes_all_costs(self):
        """Test that breakeven calculation includes gas and slippage."""
        self.fake_client.estimate_swap_output.side_effect = [
            Decimal("0.5"),  # USDC -> WETH
            Decimal("1000"),  # WETH -> USDT
            Decimal("1030"),  # USDT -> USDC (3% gross profit = $30)
        ]

        opportunity = self.solver._evaluate_route(
            self.config.routes[0], Decimal("1000")
        )

        self.assertIsNotNone(opportunity)

        # Breakeven before gas should be gross profit minus slippage cost
        # Gross profit = $30
        # Slippage cost = notional * total_slippage_bps / 10000
        expected_slippage_cost = float(
            Decimal("1000") * Decimal(opportunity.total_slippage_bps) / 10000
        )
        expected_breakeven_before = 30.0 - expected_slippage_cost

        self.assertAlmostEqual(
            float(opportunity.breakeven_before_gas),
            expected_breakeven_before,
            places=1,
        )

        # Breakeven after gas should additionally subtract gas cost
        expected_breakeven_after = expected_breakeven_before - float(
            opportunity.gas_cost_usd
        )
        self.assertAlmostEqual(
            float(opportunity.breakeven_after_gas),
            expected_breakeven_after,
            places=1,
        )

    def test_route_rejected_below_min_profit(self):
        """Test that routes below min profit threshold are rejected."""
        # Set high minimum profit
        self.config.min_profit_bps = 200  # 2%

        self.fake_client.estimate_swap_output.side_effect = [
            Decimal("0.5"),  # USDC -> WETH
            Decimal("1000"),  # WETH -> USDT
            Decimal("1005"),  # USDT -> USDC (0.5% gross, won't meet 2% threshold)
        ]

        opportunity = self.solver._evaluate_route(
            self.config.routes[0], Decimal("1000")
        )

        # Should be rejected due to insufficient profit
        self.assertIsNone(opportunity)


if HYPOTHESIS_AVAILABLE:

    class TestPropertyBasedTests(unittest.TestCase):
        """Property-based tests using Hypothesis."""

        def setUp(self):
            """Set up test fixtures."""
            self.config = DEXMEVConfig(
                network="ethereum",
                chain_id=1,
                rpc_url_env="TEST_RPC",
                rpc_primary="",
                rpc_backups=[],
                private_key_env="TEST_KEY",
                base_asset="USDC",
                min_profit_bps=10,
                max_slippage_bps=50,
                per_leg_slippage_bps=50,
                cycle_slippage_bps=100,
                max_base_fee_gwei=50,
                max_priority_fee_gwei=2,
                gas_limit_cap=500000,
                private_tx_enabled=False,
                mev_relay="",
                simulation_rpc="",
                exact_in=True,
                use_bundle=False,
                routes=[],
                tokens={},
                use_flashbots=False,
                coinbase_tip_gwei=0,
            )
            self.dex_client = DEXClient(self.config, paper_mode=True)

        @given(
            amount_in=st.decimals(min_value=1, max_value=1000000, places=2),
            reserve_in=st.decimals(min_value=1000, max_value=10000000, places=2),
            reserve_out=st.decimals(min_value=1000, max_value=10000000, places=2),
        )
        def test_v2_output_always_positive(self, amount_in, reserve_in, reserve_out):
            """Property: V2 output should always be positive for positive inputs."""
            amount_out = self.dex_client.calculate_v2_output(
                amount_in, reserve_in, reserve_out, 30
            )
            self.assertGreaterEqual(amount_out, Decimal("0"))

        @given(
            amount_in=st.decimals(min_value=1, max_value=100000, places=2),
            reserve_in=st.decimals(min_value=100000, max_value=10000000, places=2),
            reserve_out=st.decimals(min_value=100000, max_value=10000000, places=2),
        )
        def test_v2_output_less_than_reserve(self, amount_in, reserve_in, reserve_out):
            """Property: Output should never exceed output reserve."""
            amount_out = self.dex_client.calculate_v2_output(
                amount_in, reserve_in, reserve_out, 30
            )
            self.assertLess(amount_out, reserve_out)

        @given(
            amount_in_1=st.decimals(min_value=100, max_value=10000, places=2),
            amount_in_2=st.decimals(min_value=100, max_value=10000, places=2),
            reserve_in=st.decimals(min_value=100000, max_value=1000000, places=2),
            reserve_out=st.decimals(min_value=100000, max_value=1000000, places=2),
        )
        def test_v2_output_monotonicity(
            self, amount_in_1, amount_in_2, reserve_in, reserve_out
        ):
            """Property: More input should always give more output."""
            if amount_in_1 >= amount_in_2:
                return  # Skip if not ordered

            out_1 = self.dex_client.calculate_v2_output(
                amount_in_1, reserve_in, reserve_out, 30
            )
            out_2 = self.dex_client.calculate_v2_output(
                amount_in_2, reserve_in, reserve_out, 30
            )

            self.assertGreater(out_2, out_1)


class TestConfigSchema(unittest.TestCase):
    """Test configuration schema validation."""

    def test_config_from_dict_with_all_fields(self):
        """Test that config can be created from dictionary with all fields."""
        config_dict = {
            "network": "ethereum",
            "chain_id": 1,
            "rpc_url_env": "RPC_URL",
            "rpc_primary": "https://eth.llamarpc.com",
            "rpc_backups": ["https://rpc.ankr.com/eth"],
            "private_key_env": "PRIVATE_KEY",
            "base_asset": "USDC",
            "min_profit_bps": 10,
            "max_slippage_bps": 50,
            "per_leg_slippage_bps": 30,
            "cycle_slippage_bps": 80,
            "max_base_fee_gwei": 50,
            "max_priority_fee_gwei": 2,
            "gas_limit_cap": 500000,
            "private_tx_enabled": True,
            "mev_relay": "https://relay.flashbots.net",
            "simulation_rpc": "",
            "exact_in": True,
            "use_bundle": False,
            "routes": [],
            "tokens": {},
            "use_flashbots": False,
            "coinbase_tip_gwei": 0,
        }

        config = DEXMEVConfig.from_dict(config_dict)

        self.assertEqual(config.network, "ethereum")
        self.assertEqual(config.chain_id, 1)
        self.assertEqual(config.per_leg_slippage_bps, 30)
        self.assertEqual(config.cycle_slippage_bps, 80)
        self.assertTrue(config.private_tx_enabled)
        self.assertTrue(config.exact_in)

    def test_config_from_dict_with_defaults(self):
        """Test that config uses sensible defaults for missing fields."""
        config_dict = {
            "chain_id": 1,
            "base_asset": "USDC",
            "routes": [],
            "tokens": {},
        }

        config = DEXMEVConfig.from_dict(config_dict)

        self.assertEqual(config.network, "ethereum")  # default
        self.assertEqual(config.per_leg_slippage_bps, 50)  # default
        self.assertEqual(config.cycle_slippage_bps, 100)  # default
        self.assertFalse(config.private_tx_enabled)  # default


if __name__ == "__main__":
    unittest.main()
