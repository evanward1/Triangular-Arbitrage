"""
Performance benchmarks for triangular arbitrage components
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock

from triangular_arbitrage.exchanges import PaperExchange, BacktestExchange
from triangular_arbitrage.metrics import TradingMetrics


@pytest.fixture
def mock_live_exchange():
    """Fast mock exchange for benchmarking"""
    mock_exchange = Mock()
    mock_exchange.load_markets = AsyncMock(return_value={"BTC/USDT": {}})
    mock_exchange.fetch_ticker = AsyncMock(
        return_value={"bid": 42000, "ask": 42010, "last": 42005, "quoteVolume": 1000}
    )
    return mock_exchange


@pytest.fixture
def paper_exchange_config():
    """Paper exchange config for benchmarks"""
    return {
        "execution_mode": "paper",
        "fee_bps": 30,
        "fill_ratio": 0.95,
        "random_seed": 42,
        "initial_balances": {"BTC": 10.0, "USDT": 500000.0},
    }


class TestPerformanceBenchmarks:
    """Performance benchmarks for critical components"""

    @pytest.mark.benchmark(group="exchange")
    @pytest.mark.asyncio
    async def test_paper_exchange_order_throughput(
        self, benchmark, mock_live_exchange, paper_exchange_config
    ):
        """Benchmark paper exchange order processing speed"""
        exchange = PaperExchange(mock_live_exchange, paper_exchange_config)
        await exchange.initialize()

        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        async def place_order():
            return await exchange.create_market_order("BTC/USDT", OrderSide.BUY, 0.01)

        # Benchmark single order execution
        result = benchmark(asyncio.run, place_order())
        assert result.status in ["filled", "partial"]

    @pytest.mark.benchmark(group="exchange")
    @pytest.mark.asyncio
    async def test_paper_exchange_batch_orders(
        self, benchmark, mock_live_exchange, paper_exchange_config
    ):
        """Benchmark batch order processing"""
        exchange = PaperExchange(mock_live_exchange, paper_exchange_config)
        await exchange.initialize()

        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        async def place_batch_orders():
            tasks = []
            for i in range(10):
                task = exchange.create_market_order("BTC/USDT", OrderSide.BUY, 0.001)
                tasks.append(task)
            return await asyncio.gather(*tasks)

        # Benchmark batch execution
        results = benchmark(asyncio.run, place_batch_orders())
        assert len(results) == 10
        assert all(r.status in ["filled", "partial"] for r in results)

    @pytest.mark.benchmark(group="metrics")
    def test_metrics_recording_speed(self, benchmark):
        """Benchmark metrics recording performance"""
        metrics = TradingMetrics()

        def record_metrics_batch():
            for i in range(100):
                metrics.record_cycle_started("test_strategy", "paper")
                metrics.record_cycle_filled("test_strategy", "paper", profit_bps=10.0)
                metrics.record_order_placed("test_strategy", "paper", "BTC/USDT", "buy")

        # Benchmark metrics recording
        benchmark(record_metrics_batch)

    @pytest.mark.benchmark(group="metrics")
    def test_metrics_concurrent_updates(self, benchmark):
        """Benchmark concurrent metrics updates"""
        metrics = TradingMetrics()

        import threading

        def concurrent_updates():
            def update_worker():
                for i in range(50):
                    metrics.record_cycle_started("test_strategy", "paper")

            threads = [threading.Thread(target=update_worker) for _ in range(4)]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join()

        # Benchmark concurrent access
        benchmark(concurrent_updates)

    @pytest.mark.benchmark(group="backtest", min_rounds=1)
    @pytest.mark.asyncio
    async def test_backtest_data_processing_speed(self, benchmark):
        """Benchmark backtest data loading and processing"""
        config = {
            "execution_mode": "backtest",
            "data_file": "data/backtests/sample_feed.csv",
            "random_seed": 42,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        async def initialize_backtest():
            exchange = BacktestExchange(config)
            await exchange.initialize()
            return exchange

        # Benchmark backtest initialization
        exchange = benchmark(asyncio.run, initialize_backtest())
        assert exchange is not None

    @pytest.mark.benchmark(group="backtest")
    @pytest.mark.asyncio
    async def test_backtest_order_simulation_speed(self, benchmark):
        """Benchmark backtest order simulation"""
        config = {
            "execution_mode": "backtest",
            "data_file": "data/backtests/sample_feed.csv",
            "random_seed": 42,
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        exchange = BacktestExchange(config)
        await exchange.initialize()

        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        async def simulate_order():
            return await exchange.create_market_order("BTC/USDT", OrderSide.BUY, 0.01)

        # Benchmark single order simulation
        result = benchmark(asyncio.run, simulate_order())
        assert result.status in ["filled", "partial", "failed"]

    @pytest.mark.benchmark(group="calculation", min_rounds=5)
    def test_profit_calculation_speed(self, benchmark):
        """Benchmark profit calculation algorithms"""

        def calculate_triangular_profit():
            # Simulate profit calculation
            prices = {
                "BTC/USDT": {"bid": 42000, "ask": 42010},
                "ETH/USDT": {"bid": 2200, "ask": 2205},
                "ETH/BTC": {"bid": 0.05235, "ask": 0.05240},
            }

            initial_amount = 1.0  # 1 BTC

            # Step 1: BTC -> ETH
            btc_to_eth_rate = 1 / prices["ETH/BTC"]["ask"]
            eth_amount = initial_amount * btc_to_eth_rate

            # Step 2: ETH -> USDT
            usdt_amount = eth_amount * prices["ETH/USDT"]["bid"]

            # Step 3: USDT -> BTC
            final_btc = usdt_amount / prices["BTC/USDT"]["ask"]

            profit = final_btc - initial_amount
            profit_bps = (profit / initial_amount) * 10000

            return profit_bps

        # Benchmark profit calculation
        profit_bps = benchmark(calculate_triangular_profit)
        assert isinstance(profit_bps, (int, float))

    @pytest.mark.benchmark(group="memory")
    def test_memory_usage_metrics(self, benchmark):
        """Monitor memory usage during operations"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        def memory_intensive_operation():
            metrics = TradingMetrics()

            # Create many metric updates
            for i in range(1000):
                metrics.record_cycle_started(f"strategy_{i % 10}", "paper")
                metrics.record_order_placed(
                    f"strategy_{i % 10}", "paper", "BTC/USDT", "buy"
                )

            return metrics

        # Run benchmark
        metrics = benchmark(memory_intensive_operation)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Log memory usage (pytest-benchmark will capture this)
        print(f"Memory increase: {memory_increase:.2f} MB")

        # Assert reasonable memory usage (less than 100MB increase)
        assert memory_increase < 100, f"Memory usage too high: {memory_increase}MB"

    @pytest.mark.benchmark(group="scaling")
    def test_metrics_label_scaling(self, benchmark):
        """Test performance with high cardinality metrics"""
        metrics = TradingMetrics()

        def high_cardinality_updates():
            # Simulate many different label combinations
            for strategy_id in range(20):
                for mode in ["live", "paper", "backtest"]:
                    for symbol in ["BTC/USDT", "ETH/USDT", "ETH/BTC"]:
                        metrics.record_order_placed(
                            f"strategy_{strategy_id}", mode, symbol, "buy"
                        )

        # Benchmark with many label combinations
        benchmark(high_cardinality_updates)


@pytest.mark.benchmark(group="integration", min_rounds=1)
class TestIntegrationBenchmarks:
    """End-to-end performance tests"""

    @pytest.mark.asyncio
    async def test_complete_cycle_simulation_speed(
        self, benchmark, mock_live_exchange, paper_exchange_config
    ):
        """Benchmark complete arbitrage cycle simulation"""
        exchange = PaperExchange(mock_live_exchange, paper_exchange_config)
        await exchange.initialize()

        from triangular_arbitrage.exchanges.base_adapter import OrderSide

        async def simulate_arbitrage_cycle():
            # Simulate 3-leg arbitrage cycle
            order1 = await exchange.create_market_order("BTC/USDT", OrderSide.SELL, 0.1)
            order2 = await exchange.create_market_order(
                "ETH/USDT", OrderSide.BUY, 200.0
            )
            order3 = await exchange.create_market_order("ETH/BTC", OrderSide.SELL, 4.0)

            return [order1, order2, order3]

        # Benchmark complete cycle
        results = benchmark(asyncio.run, simulate_arbitrage_cycle())
        assert len(results) == 3
        assert all(r.status in ["filled", "partial"] for r in results)
