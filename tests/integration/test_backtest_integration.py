"""
Integration tests for backtest functionality
"""

import pytest
import asyncio
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from triangular_arbitrage.exchanges import BacktestExchange
from backtests.run_backtest import BacktestRunner


@pytest.fixture
def sample_backtest_data():
    """Create sample backtest data file"""
    data = [
        "timestamp,symbol,bid,ask,last,volume",
        "1700000000.0,BTC/USDT,42000.00,42010.00,42005.00,125.50",
        "1700000000.0,ETH/USDT,2200.00,2202.00,2201.00,850.25",
        "1700000000.0,ETH/BTC,0.05238,0.05240,0.05239,2150.75",
        "1700000001.0,BTC/USDT,42005.00,42015.00,42010.00,126.20",
        "1700000001.0,ETH/USDT,2201.00,2203.00,2202.00,851.50",
        "1700000001.0,ETH/BTC,0.05239,0.05241,0.05240,2152.85",
        "1700000002.0,BTC/USDT,42010.00,42020.00,42015.00,127.65",
        "1700000002.0,ETH/USDT,2202.00,2204.00,2203.00,852.75",
        "1700000002.0,ETH/BTC,0.05240,0.05242,0.05241,2154.60",
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("\n".join(data))
        f.flush()
        yield f.name

    # Cleanup
    os.unlink(f.name)


@pytest.fixture
def sample_cycles_file():
    """Create sample cycles file"""
    cycles = ["BTC,ETH,USDT", "ETH,BTC,USDT", "BTC,USDT,ETH"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("\n".join(cycles))
        f.flush()
        yield f.name

    # Cleanup
    os.unlink(f.name)


@pytest.fixture
def backtest_strategy_config(sample_backtest_data, sample_cycles_file):
    """Create strategy config for backtesting"""
    return {
        "name": "test_backtest_strategy",
        "exchange": "binance",
        "trading_pairs_file": sample_cycles_file,
        "min_profit_bps": 10,
        "max_slippage_bps": 20,
        "max_leg_latency_ms": 500,
        "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
        "risk_controls": {"max_open_cycles": 1, "stop_after_consecutive_losses": 3},
        "fees": {"taker_bps": 10, "maker_bps": 5},
        "execution": {
            "mode": "backtest",
            "backtest": {
                "data_file": sample_backtest_data,
                "random_seed": 42,
                "initial_balances": {"BTC": 1.0, "ETH": 10.0, "USDT": 50000.0},
            },
        },
    }


class TestBacktestIntegration:
    """Integration tests for backtest functionality"""

    @pytest.mark.asyncio
    async def test_backtest_exchange_data_loading(self, sample_backtest_data):
        """Test that backtest exchange loads data correctly"""
        config = {
            "execution_mode": "backtest",
            "data_file": sample_backtest_data,
            "random_seed": 42,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        exchange = BacktestExchange(config)
        await exchange.initialize()

        # Check that markets were loaded
        markets = await exchange.load_markets()
        assert len(markets) > 0
        assert "BTC/USDT" in markets or "ETH/USDT" in markets

        # Check that we can fetch ticker data
        ticker = await exchange.fetch_ticker("BTC/USDT")
        assert ticker.bid > 0
        assert ticker.ask > ticker.bid
        assert ticker.volume > 0

    @pytest.mark.asyncio
    async def test_backtest_order_execution(self, sample_backtest_data):
        """Test order execution in backtest mode"""
        config = {
            "execution_mode": "backtest",
            "data_file": sample_backtest_data,
            "random_seed": 42,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        exchange = BacktestExchange(config)
        await exchange.initialize()

        # Get initial balances
        initial_balances = await exchange.fetch_balance()
        initial_btc = initial_balances.get("BTC", 0)
        initial_usdt = initial_balances.get("USDT", 0)

        # Execute a buy order
        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        result = await exchange.create_market_order("BTC/USDT", OrderSide.BUY, 0.01)

        # Verify order was executed
        assert result.status in ["filled", "partial"]
        assert result.amount_filled > 0

        # Verify balances changed
        final_balances = await exchange.fetch_balance()
        assert final_balances.get("BTC", 0) > initial_btc
        assert final_balances.get("USDT", 0) < initial_usdt

    @pytest.mark.asyncio
    async def test_deterministic_backtest(self, sample_backtest_data):
        """Test that backtests are deterministic with same seed"""
        config_base = {
            "execution_mode": "backtest",
            "data_file": sample_backtest_data,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        # Run same backtest twice with same seed
        config1 = {**config_base, "random_seed": 12345}
        config2 = {**config_base, "random_seed": 12345}

        exchange1 = BacktestExchange(config1)
        exchange2 = BacktestExchange(config2)

        await exchange1.initialize()
        await exchange2.initialize()

        # Execute same order on both
        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        result1 = await exchange1.create_market_order("BTC/USDT", OrderSide.BUY, 0.01)
        result2 = await exchange2.create_market_order("BTC/USDT", OrderSide.BUY, 0.01)

        # Results should be identical
        assert result1.amount_filled == result2.amount_filled
        assert result1.average_price == result2.average_price

    @pytest.mark.asyncio
    async def test_backtest_runner_integration(self, backtest_strategy_config):
        """Test full backtest runner integration"""
        backtest_config = {
            "data_file": backtest_strategy_config["execution"]["backtest"]["data_file"],
            "random_seed": 42,
            "max_cycles": 3,
            "initial_balances": {"BTC": 1.0, "ETH": 10.0, "USDT": 50000.0},
        }

        runner = BacktestRunner(backtest_strategy_config, backtest_config)
        results = await runner.run()

        # Verify results structure
        assert "backtest_id" in results
        assert "strategy_name" in results
        assert "cycles_started" in results
        assert "net_pnl" in results
        assert "wall_clock_duration_seconds" in results

        # Verify some cycles were processed
        assert results["cycles_started"] > 0

    @pytest.mark.asyncio
    async def test_backtest_metrics_collection(self, sample_backtest_data):
        """Test that backtest collects execution metrics"""
        config = {
            "execution_mode": "backtest",
            "data_file": sample_backtest_data,
            "random_seed": 42,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        exchange = BacktestExchange(config)
        await exchange.initialize()

        # Execute some orders
        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        await exchange.create_market_order("BTC/USDT", OrderSide.BUY, 0.01)
        await exchange.create_market_order("BTC/USDT", OrderSide.SELL, 0.005)

        # Get metrics
        metrics = await exchange.get_execution_metrics()

        # Verify metrics structure
        assert metrics["execution_mode"] == "backtest"
        assert "orders_created" in metrics
        assert "orders_filled" in metrics
        assert "fill_rate" in metrics
        assert "total_volume_usd" in metrics

        # Verify metrics have reasonable values
        assert metrics["orders_created"] >= 2
        assert metrics["fill_rate"] <= 1.0

    @pytest.mark.asyncio
    async def test_backtest_time_simulation(self, sample_backtest_data):
        """Test time progression in backtest"""
        config = {
            "execution_mode": "backtest",
            "data_file": sample_backtest_data,
            "random_seed": 42,
            "time_acceleration": 0,  # No real-time delays
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        exchange = BacktestExchange(config)
        await exchange.initialize()

        initial_time = exchange.get_current_simulation_time()

        # Advance time manually
        target_time = initial_time + 100
        exchange.advance_time_to(target_time)

        current_time = exchange.get_current_simulation_time()
        assert current_time >= target_time

    @pytest.mark.asyncio
    async def test_backtest_error_handling(self, backtest_strategy_config):
        """Test error handling in backtest scenarios"""
        # Test with non-existent data file
        bad_config = backtest_strategy_config.copy()
        bad_config["execution"]["backtest"]["data_file"] = "/nonexistent/file.csv"

        runner = BacktestRunner(
            bad_config, {"data_file": "/nonexistent/file.csv", "max_cycles": 1}
        )

        results = await runner.run()

        # Should complete with error recorded
        assert "error" in results or results.get("cycles_started", 0) == 0

    @pytest.mark.asyncio
    async def test_backtest_partial_fills(self, sample_backtest_data):
        """Test partial fill handling in backtest"""
        config = {
            "execution_mode": "backtest",
            "data_file": sample_backtest_data,
            "random_seed": 42,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
            "fill_model": {
                "fill_probability": 0.7,  # Lower probability
                "partial_fill_threshold": 1,  # Low threshold for partials
                "min_fill_ratio": 0.5,
            },
        }

        exchange = BacktestExchange(config)
        await exchange.initialize()

        # Execute multiple orders to trigger partial fills
        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        results = []
        for _ in range(5):
            result = await exchange.create_market_order("BTC/USDT", OrderSide.BUY, 0.1)
            results.append(result)

        # Should have some partial fills or failures due to low probability
        statuses = [r.status for r in results]
        assert "partial" in statuses or "failed" in statuses

    @pytest.mark.asyncio
    async def test_end_to_end_backtest(self, backtest_strategy_config):
        """Test complete end-to-end backtest flow"""
        # This simulates running the backtest script
        backtest_config = {"max_cycles": 5, "random_seed": 42}

        runner = BacktestRunner(backtest_strategy_config, backtest_config)

        # Run complete backtest
        results = await runner.run()

        # Verify comprehensive results
        expected_fields = [
            "backtest_id",
            "strategy_name",
            "cycles_started",
            "cycles_filled",
            "net_pnl",
            "wall_clock_duration_seconds",
            "final_balances",
            "execution_metrics",
        ]

        for field in expected_fields:
            assert field in results, f"Missing required field: {field}"

        # Verify results are reasonable
        assert results["cycles_started"] >= 0
        assert results["wall_clock_duration_seconds"] > 0
        assert isinstance(results["final_balances"], dict)
