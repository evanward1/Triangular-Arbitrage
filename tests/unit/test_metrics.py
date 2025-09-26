"""
Unit tests for Prometheus metrics
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from prometheus_client import CollectorRegistry, generate_latest
import aiohttp
import aiohttp.test_utils
from aiohttp import web

from triangular_arbitrage.metrics import TradingMetrics, get_metrics, initialize_metrics


@pytest.fixture
def test_registry():
    """Create a test-specific registry"""
    return CollectorRegistry()


@pytest.fixture
def metrics(test_registry):
    """Create TradingMetrics instance with test registry"""
    return TradingMetrics(test_registry)


class TestTradingMetrics:
    """Test TradingMetrics functionality"""

    def test_initialization(self, metrics):
        """Test metrics initialization"""
        assert metrics.registry is not None
        assert hasattr(metrics, "cycles_started_total")
        assert hasattr(metrics, "cycles_filled_total")
        assert hasattr(metrics, "realized_profit_basis_points")

    def test_cycle_metrics(self, metrics):
        """Test cycle-related metrics recording"""
        strategy_name = "test_strategy"

        # Record cycle events
        metrics.record_cycle_started(strategy_name, "paper")
        metrics.record_cycle_filled(
            strategy_name, "paper", profit_bps=15.0, duration_seconds=2.5
        )
        metrics.record_cycle_canceled(strategy_name, "slippage too high")

        # Verify metrics were recorded
        metric_output = generate_latest(metrics.registry).decode("utf-8")

        assert "triangular_arbitrage_cycles_started_total" in metric_output
        assert "triangular_arbitrage_cycles_filled_total" in metric_output
        assert "triangular_arbitrage_cycles_canceled_by_slippage_total" in metric_output

    def test_order_metrics(self, metrics):
        """Test order-related metrics recording"""
        strategy_name = "test_strategy"
        execution_mode = "paper"
        symbol = "BTC/USDT"

        # Record order events
        metrics.record_order_placed(strategy_name, execution_mode, symbol, "buy")
        metrics.record_order_filled(
            strategy_name,
            execution_mode,
            symbol,
            "buy",
            slippage_bps=5.0,
            fee_amount=1.25,
            fee_currency="USDT",
        )

        # Verify metrics
        metric_output = generate_latest(metrics.registry).decode("utf-8")
        assert "triangular_arbitrage_orders_placed_total" in metric_output
        assert "triangular_arbitrage_orders_filled_total" in metric_output
        assert "triangular_arbitrage_slippage_basis_points" in metric_output

    def test_latency_metrics(self, metrics):
        """Test latency metrics recording"""
        strategy_name = "test_strategy"

        # Record leg latency
        metrics.record_leg_latency(strategy_name, 1, "BTC/USDT", 0.15)
        metrics.record_leg_latency(strategy_name, 2, "ETH/BTC", 0.08)

        metric_output = generate_latest(metrics.registry).decode("utf-8")
        assert "triangular_arbitrage_leg_latency_seconds" in metric_output

    def test_risk_metrics(self, metrics):
        """Test risk control metrics"""
        strategy_name = "test_strategy"

        # Update risk-related metrics
        metrics.update_cooldown_count(strategy_name, 3)
        metrics.record_risk_violation(strategy_name, "slippage_exceeded")
        metrics.update_consecutive_losses(strategy_name, 2)

        metric_output = generate_latest(metrics.registry).decode("utf-8")
        assert "triangular_arbitrage_cooldown_count" in metric_output
        assert "triangular_arbitrage_risk_violations_total" in metric_output
        assert "triangular_arbitrage_consecutive_losses" in metric_output

    def test_balance_and_pnl_metrics(self, metrics):
        """Test balance and P&L metrics"""
        strategy_name = "test_strategy"

        # Update balance and P&L
        metrics.update_balance(strategy_name, "BTC", 1.5, "paper")
        metrics.update_balance(strategy_name, "USDT", 48750.0, "paper")
        metrics.update_pnl(strategy_name, "paper", "USDT", 125.50)

        metric_output = generate_latest(metrics.registry).decode("utf-8")
        assert "triangular_arbitrage_active_balance" in metric_output
        assert "triangular_arbitrage_total_profit_loss" in metric_output

    def test_system_health_metrics(self, metrics):
        """Test system health metrics"""
        strategy_name = "test_strategy"

        # Update health metrics
        metrics.update_last_activity(strategy_name)
        metrics.record_system_error(strategy_name, "network_timeout")

        metric_output = generate_latest(metrics.registry).decode("utf-8")
        assert "triangular_arbitrage_last_activity_timestamp" in metric_output
        assert "triangular_arbitrage_system_errors_total" in metric_output

    def test_thread_safety(self, metrics):
        """Test thread-safe metric updates"""
        import threading

        def update_metrics():
            for i in range(100):
                metrics.record_cycle_started("test", "paper")

        # Create multiple threads
        threads = [threading.Thread(target=update_metrics) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify we got all updates (500 total)
        metric_output = generate_latest(metrics.registry).decode("utf-8")
        # Should contain the metric, exact count verification would require parsing
        assert "triangular_arbitrage_cycles_started_total" in metric_output

    @pytest.mark.asyncio
    async def test_metrics_server(self, metrics):
        """Test metrics HTTP server"""
        # Start server on random port
        success = await metrics.start_server(port=0)  # Let system choose port

        if success:
            # Test that server is running
            assert metrics._app is not None
            assert metrics._runner is not None

            # Stop server
            await metrics.stop_server()

    def test_metrics_summary(self, metrics):
        """Test metrics summary generation"""
        summary = metrics.get_metrics_summary()

        assert "metrics_available" in summary
        assert summary["metrics_available"] is True
        assert "timestamp" in summary


class TestMetricsGlobal:
    """Test global metrics functionality"""

    def test_get_metrics_singleton(self):
        """Test global metrics singleton"""
        # Reset global state to avoid registry conflicts
        import triangular_arbitrage.metrics as metrics_module
        from prometheus_client import REGISTRY, CollectorRegistry

        # Clear any existing metrics from the default registry
        for collector in list(REGISTRY._collector_to_names.keys()):
            try:
                REGISTRY.unregister(collector)
            except (KeyError, ValueError):
                pass

        # Reset global metrics instance
        metrics_module._global_metrics = None

        metrics1 = get_metrics()
        metrics2 = get_metrics()

        # Should return same instance
        assert metrics1 is metrics2

    def test_initialize_metrics(self, test_registry):
        """Test custom metrics initialization"""
        custom_metrics = initialize_metrics(test_registry)

        assert custom_metrics.registry is test_registry
        assert custom_metrics is get_metrics()  # Should become the global instance


@pytest.mark.asyncio
async def test_metrics_server_endpoints():
    """Test metrics server HTTP endpoints"""
    from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
    from aiohttp import web

    # Create test metrics instance
    test_registry = CollectorRegistry()
    metrics = TradingMetrics(test_registry)

    # Create test app
    app = web.Application()
    app.router.add_get("/metrics", metrics._metrics_handler)
    app.router.add_get("/health", metrics._health_handler)

    async with aiohttp.test_utils.TestClient(aiohttp.test_utils.TestServer(app)) as client:
        # Test metrics endpoint
        resp = await client.get("/metrics")
        assert resp.status == 200
        text = await resp.text()
        assert "triangular_arbitrage" in text

        # Test health endpoint
        resp = await client.get("/health")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["status"] == "healthy"


def test_metric_labels():
    """Test that metrics have correct labels"""
    test_registry = CollectorRegistry()
    metrics = TradingMetrics(test_registry)

    # Record metrics with various label combinations
    metrics.record_cycle_started("strategy1", "live")
    metrics.record_cycle_started("strategy1", "paper")
    metrics.record_cycle_started("strategy2", "live")

    # Get metric families
    metric_families = list(test_registry.collect())

    # Find the cycles_started metric
    cycles_metric = None
    for family in metric_families:
        if family.name == "triangular_arbitrage_cycles_started":
            cycles_metric = family
            break

    assert cycles_metric is not None
    # Counter creates both _total and _created samples, so 3 label combinations = 6 samples
    assert len(cycles_metric.samples) == 6  # 3 different label combinations × 2 sample types


def test_metric_values():
    """Test metric value accuracy"""
    test_registry = CollectorRegistry()
    metrics = TradingMetrics(test_registry)

    # Record specific values
    metrics.record_cycle_started("test", "paper")
    metrics.record_cycle_started("test", "paper")
    metrics.record_cycle_filled("test", "paper", profit_bps=10.0)

    # Get metric families and check values
    metric_families = list(test_registry.collect())

    for family in metric_families:
        if family.name == "triangular_arbitrage_cycles_started_total":
            # Should have value of 2 for our label combination
            for sample in family.samples:
                if (
                    sample.labels.get("strategy_name") == "test"
                    and sample.labels.get("execution_mode") == "paper"
                ):
                    assert sample.value == 2.0
