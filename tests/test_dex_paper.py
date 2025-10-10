"""
Unit tests for DEX paper trading scanner.

Tests cover:
- V2 constant-product math
- Config loading and validation
- Reserve normalization
- Mocked scanning with Web3
"""

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import modules to test
from dex.adapters.v2 import price_quote_in_out, swap_out
from dex.config import ConfigError, DexConfig, load_config
from dex.runner import DexRunner

# ===== V2 Math Tests =====


class TestV2Math:
    """Test Uniswap V2 constant-product formulas."""

    def test_swap_out_no_fee(self):
        """Test basic swap without fee."""
        # Simple case: equal reserves, no fee
        amount_in = Decimal("100")
        reserve_in = Decimal("1000")
        reserve_out = Decimal("1000")
        fee = Decimal("0")

        # Formula: out = (100 * 1000) / (1000 + 100) = 100000 / 1100 ≈ 90.909
        result = swap_out(amount_in, reserve_in, reserve_out, fee)
        expected = Decimal("100000") / Decimal("1100")

        assert abs(result - expected) < Decimal("0.001")

    def test_swap_out_with_30bps_fee(self):
        """Test swap with 0.3% fee."""
        amount_in = Decimal("100")
        reserve_in = Decimal("1000")
        reserve_out = Decimal("1000")
        fee = Decimal("0.003")  # 30 bps

        # With fee: in_with_fee = 100 * (1 - 0.003) = 99.7
        # out = (99.7 * 1000) / (1000 + 99.7) = 99700 / 1099.7 ≈ 90.636
        result = swap_out(amount_in, reserve_in, reserve_out, fee)
        expected = (
            Decimal("99.7") * Decimal("1000") / (Decimal("1000") + Decimal("99.7"))
        )

        assert abs(result - expected) < Decimal("0.001")

    def test_swap_out_asymmetric_reserves(self):
        """Test swap with unequal reserves."""
        amount_in = Decimal("100")
        reserve_in = Decimal("10000")  # Large reserve
        reserve_out = Decimal("100")  # Small reserve
        fee = Decimal("0.003")

        result = swap_out(amount_in, reserve_in, reserve_out, fee)

        # With large in-reserve, price should be worse
        # in_with_fee = 100 * 0.997 = 99.7
        # out = (99.7 * 100) / (10000 + 99.7) ≈ 0.987
        assert result < Decimal("1.0")  # Should get less than 1 out for 100 in

    def test_swap_out_invalid_inputs(self):
        """Test that invalid inputs raise errors."""
        # Negative amount
        with pytest.raises(ValueError):
            swap_out(Decimal("-10"), Decimal("1000"), Decimal("1000"), Decimal("0.003"))

        # Zero reserves
        with pytest.raises(ValueError):
            swap_out(Decimal("10"), Decimal("0"), Decimal("1000"), Decimal("0.003"))

        # Invalid fee
        with pytest.raises(ValueError):
            swap_out(Decimal("10"), Decimal("1000"), Decimal("1000"), Decimal("1.5"))

    def test_price_quote_in_out(self):
        """Test price calculation."""
        amount_in = Decimal("100")
        reserve_in = Decimal("1000")
        reserve_out = Decimal("2000")
        fee = Decimal("0.003")

        amount_out, price = price_quote_in_out(amount_in, reserve_in, reserve_out, fee)

        # Price should be amount_out / amount_in
        expected_price = amount_out / amount_in
        assert abs(price - expected_price) < Decimal("0.00001")

        # With 2x reserve_out, price should be roughly 2:1 for small trades
        assert price > Decimal(
            "1.8"
        )  # Should be close to 2 but slightly worse due to slippage


# ===== Config Tests =====


class TestConfig:
    """Test configuration loading and validation."""

    def test_load_valid_config(self):
        """Test loading a valid config file."""
        config_data = {
            "rpc_url": "https://mainnet.base.org",
            "poll_sec": 10,
            "usd_token": "USDC",
            "max_position_usd": 500,
            "slippage_bps": 10,
            "threshold_net_pct": 0.5,
            "tokens": {
                "USDC": {
                    "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    "decimals": 6,
                },
                "WETH": {
                    "address": "0x4200000000000000000000000000000000000006",
                    "decimals": 18,
                },
            },
            "dexes": [
                {
                    "name": "uniswap",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "WETH/USDC",
                            "address": "0x1111111111111111111111111111111111111111",
                            "base": "WETH",
                            "quote": "USDC",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_data)

        assert config.rpc_url == "https://mainnet.base.org"
        assert config.poll_sec == 10
        assert config.usd_token == "USDC"
        assert config.max_position_usd == Decimal("500")
        assert config.slippage_bps == 10
        assert config.slippage_pct == 0.1
        assert len(config.tokens) == 2
        assert len(config.dexes) == 1

    def test_config_defaults(self):
        """Test that config applies sensible defaults."""
        config_data = {
            "rpc_url": "https://test.com",
            "usd_token": "USDC",
            "tokens": {"USDC": {"address": "0x" + "0" * 40, "decimals": 6}},
            "dexes": [
                {
                    "name": "test",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "TEST/USDC",
                            "address": "0x" + "1" * 40,
                            "base": "TEST",
                            "quote": "USDC",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_data)

        assert config.poll_sec == 6  # Default
        assert config.once is False  # Default
        assert config.slippage_bps == 5  # Default

    def test_config_missing_required_field(self):
        """Test that missing required fields raise errors."""
        # Missing rpc_url
        config_data = {
            "usd_token": "USDC",
            "tokens": {"USDC": {"address": "0x" + "0" * 40, "decimals": 6}},
            "dexes": [],
        }

        with pytest.raises(ConfigError, match="rpc_url"):
            DexConfig(config_data)

    def test_config_invalid_usd_token(self):
        """Test that USD token must be defined in tokens."""
        config_data = {
            "rpc_url": "https://test.com",
            "usd_token": "DAI",  # Not in tokens
            "tokens": {"USDC": {"address": "0x" + "0" * 40, "decimals": 6}},
            "dexes": [],
        }

        with pytest.raises(ConfigError, match="not found in tokens"):
            DexConfig(config_data)

    def test_config_breakeven_calculation(self):
        """Test breakeven percentage calculation."""
        config_data = {
            "rpc_url": "https://test.com",
            "usd_token": "USDC",
            "max_position_usd": 1000,
            "slippage_bps": 5,
            "threshold_net_pct": 0.1,
            "gas_cost_usd_override": 0.5,
            "tokens": {"USDC": {"address": "0x" + "0" * 40, "decimals": 6}},
            "dexes": [
                {
                    "name": "test",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "TEST/USDC",
                            "address": "0x" + "1" * 40,
                            "base": "TEST",
                            "quote": "USDC",
                        }
                    ],
                }
            ],
        }

        config = DexConfig(config_data)

        # slippage_pct = 0.05%
        # gas_pct = 0.5 / 1000 * 100 = 0.05%
        # breakeven = 0.1 + 0.05 + 0.05 = 0.2%
        assert abs(config.breakeven_pct - 0.2) < 0.001

    def test_load_config_from_file(self):
        """Test loading config from YAML file."""
        config_data = {
            "rpc_url": "https://test.com",
            "usd_token": "USDC",
            "tokens": {"USDC": {"address": "0x" + "0" * 40, "decimals": 6}},
            "dexes": [
                {
                    "name": "test",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "TEST/USDC",
                            "address": "0x" + "1" * 40,
                            "base": "TEST",
                            "quote": "USDC",
                        }
                    ],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.rpc_url == "https://test.com"
        finally:
            Path(temp_path).unlink()

    def test_load_config_file_not_found(self):
        """Test that missing config file raises error."""
        with pytest.raises(ConfigError, match="not found"):
            load_config("/nonexistent/path.yaml")


# ===== Runner Tests =====


class TestRunner:
    """Test DexRunner with mocked Web3."""

    @pytest.fixture
    def mock_config(self):
        """Create a minimal test config."""
        config_data = {
            "rpc_url": "https://test.com",
            "poll_sec": 1,
            "once": True,
            "usd_token": "USDC",
            "max_position_usd": 1000,
            "slippage_bps": 5,
            "threshold_net_pct": 0.1,
            "tokens": {
                "USDC": {
                    "address": "0x0000000000000000000000000000000000000001",
                    "decimals": 6,
                },
                "WETH": {
                    "address": "0x0000000000000000000000000000000000000002",
                    "decimals": 18,
                },
            },
            "dexes": [
                {
                    "name": "dexA",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "WETH/USDC",
                            "address": "0x1111111111111111111111111111111111111111",
                            "base": "WETH",
                            "quote": "USDC",
                        }
                    ],
                },
                {
                    "name": "dexB",
                    "kind": "v2",
                    "fee_bps": 30,
                    "pairs": [
                        {
                            "name": "WETH/USDC",
                            "address": "0x2222222222222222222222222222222222222222",
                            "base": "WETH",
                            "quote": "USDC",
                        }
                    ],
                },
            ],
        }
        return DexConfig(config_data)

    @patch("dex.runner.Web3")
    def test_runner_init(self, mock_web3, mock_config):
        """Test runner initialization."""
        runner = DexRunner(mock_config)
        assert runner.config == mock_config
        assert runner.scan_count == 0
        assert runner.ema_gross is None

    @patch("dex.runner.Web3")
    def test_runner_connect(self, mock_web3_class, mock_config):
        """Test RPC connection."""
        # Mock Web3 instance
        mock_web3 = MagicMock()
        mock_web3.is_connected.return_value = True
        mock_web3.eth.chain_id = 1
        mock_web3.eth.block_number = 12345678
        mock_web3_class.return_value = mock_web3

        runner = DexRunner(mock_config)
        runner.connect()

        assert runner.web3 is not None
        mock_web3.is_connected.assert_called_once()

    @patch("dex.runner.Web3")
    def test_runner_build_token_maps(self, mock_web3, mock_config):
        """Test token address mapping."""
        runner = DexRunner(mock_config)
        runner.build_token_maps()

        assert "USDC" in runner.addr_of
        assert "WETH" in runner.addr_of
        assert runner.decimals_of["USDC"] == 6
        assert runner.decimals_of["WETH"] == 18

    @patch("dex.runner.fetch_pool")
    def test_runner_fetch_pools_normalization(self, mock_fetch_pool, mock_config):
        """Test that reserves are normalized correctly."""
        # Token addresses from config
        usdc_addr = "0x0000000000000000000000000000000000000001"
        weth_addr = "0x0000000000000000000000000000000000000002"

        # Mock fetch_pool to return USDC as token0, WETH as token1
        # But config has WETH as base, USDC as quote - should flip!
        mock_fetch_pool.return_value = (
            usdc_addr,  # token0
            weth_addr,  # token1
            Decimal("1000000000"),  # r0 (USDC)
            Decimal("500000000000000000000"),  # r1 (WETH)
        )

        # Create a real Web3 mock that doesn't break checksumming
        runner = DexRunner(mock_config)
        runner.web3 = MagicMock()  # Just need a truthy object
        runner.build_token_maps()
        runner.fetch_pools()

        # Should have 2 pools (one from each DEX)
        assert len(runner.pools) == 2

        # Check first pool - reserves should be flipped since config says base=WETH
        pool = runner.pools[0]
        assert pool.base_symbol == "WETH"
        assert pool.quote_symbol == "USDC"
        # After flip: r0 should be WETH reserve, r1 should be USDC reserve
        assert pool.r0 == Decimal("500000000000000000000")
        assert pool.r1 == Decimal("1000000000")

    @patch("dex.runner.fetch_pool")
    def test_runner_scan_with_mock_pools(self, mock_fetch_pool, mock_config):
        """Test full scan with mocked pool data."""
        usdc_addr = "0x0000000000000000000000000000000000000001"
        weth_addr = "0x0000000000000000000000000000000000000002"

        # DexA: Price favorable for buying WETH
        # DexB: Price favorable for selling WETH
        # This creates an arbitrage opportunity

        def fetch_side_effect(web3, pair_addr):
            if "1111" in pair_addr:  # DexA
                return (
                    weth_addr,
                    usdc_addr,
                    Decimal("100000000000000000000"),  # 100 WETH
                    Decimal("250000000000"),  # 250k USDC (cheap WETH)
                )
            else:  # DexB
                return (
                    weth_addr,
                    usdc_addr,
                    Decimal("100000000000000000000"),  # 100 WETH
                    Decimal("200000000000"),  # 200k USDC (expensive WETH)
                )

        mock_fetch_pool.side_effect = fetch_side_effect

        runner = DexRunner(mock_config)
        runner.web3 = MagicMock()  # Just need a truthy object
        runner.build_token_maps()
        runner.fetch_pools()

        # Run scan
        rows = runner.scan()

        # Should find arbitrage opportunities
        assert len(rows) > 0
        assert runner.scan_count == 1


# ===== Integration Test =====


def test_cli_help():
    """Test that CLI script can be imported."""
    # This is a smoke test - just ensure the module loads
    import run_dex_paper

    assert run_dex_paper.main is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
