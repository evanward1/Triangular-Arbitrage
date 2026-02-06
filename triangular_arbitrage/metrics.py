"""
Prometheus Metrics Server for Triangular Arbitrage Trading

Exposes comprehensive trading metrics for monitoring and alerting.
"""

# asyncio removed - not used in current implementation
import logging
import time
from collections import deque
from typing import Dict, Any, Optional
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    # Summary removed - not used
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    # multiprocess removed - not used
    REGISTRY,
)
from aiohttp import web
import threading

logger = logging.getLogger(__name__)


class TradingMetrics:
    """
    Comprehensive trading metrics collection and exposure

    Provides Prometheus-compatible metrics for:
    - Cycle execution statistics
    - Order fill rates and latency
    - Risk control events
    - P&L tracking
    - System health
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize metrics with custom registry or default"""
        self.registry = registry or REGISTRY
        self._initialize_metrics()

        # Server components
        self._server = None
        self._app = None
        self._runner = None
        self._site = None

        # Thread-safe access
        self._lock = threading.RLock()

    def _initialize_metrics(self):
        """Initialize all Prometheus metrics"""

        # === CYCLE METRICS ===
        self.cycles_started_total = Counter(
            "triangular_arbitrage_cycles_started_total",
            "Total number of arbitrage cycles started",
            ["strategy_name", "execution_mode"],
            registry=self.registry,
        )

        self.cycles_filled_total = Counter(
            "triangular_arbitrage_cycles_filled_total",
            "Total number of cycles successfully filled",
            ["strategy_name", "execution_mode"],
            registry=self.registry,
        )

        self.cycles_canceled_by_slippage_total = Counter(
            "triangular_arbitrage_cycles_canceled_by_slippage_total",
            "Total cycles canceled due to slippage limits",
            ["strategy_name"],
            registry=self.registry,
        )

        self.cycles_canceled_by_latency_total = Counter(
            "triangular_arbitrage_cycles_canceled_by_latency_total",
            "Total cycles canceled due to latency limits",
            ["strategy_name"],
            registry=self.registry,
        )

        self.cycles_partial_filled_total = Counter(
            "triangular_arbitrage_cycles_partial_filled_total",
            "Total cycles with partial fills",
            ["strategy_name", "execution_mode"],
            registry=self.registry,
        )

        # === LATENCY METRICS ===
        self.leg_latency_seconds = Histogram(
            "triangular_arbitrage_leg_latency_seconds",
            "Latency for individual cycle legs",
            ["strategy_name", "leg_number", "market_symbol"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
            registry=self.registry,
        )

        self.cycle_duration_seconds = Histogram(
            "triangular_arbitrage_cycle_duration_seconds",
            "Total duration for complete cycles",
            ["strategy_name", "execution_mode"],
            buckets=[1, 5, 10, 30, 60, 120, 300],
            registry=self.registry,
        )

        self.average_leg_latency_seconds = Gauge(
            "triangular_arbitrage_average_leg_latency_seconds",
            "Average latency across all legs (last 100 cycles)",
            ["strategy_name"],
            registry=self.registry,
        )

        # === P&L METRICS ===
        self.realized_profit_basis_points = Histogram(
            "triangular_arbitrage_realized_profit_basis_points",
            "Realized profit in basis points per cycle",
            ["strategy_name", "execution_mode"],
            buckets=[-100, -50, -20, -10, -5, 0, 5, 10, 20, 50, 100, 200],
            registry=self.registry,
        )

        self.total_profit_loss = Gauge(
            "triangular_arbitrage_total_profit_loss",
            "Cumulative profit/loss across all strategies",
            ["strategy_name", "execution_mode", "currency"],
            registry=self.registry,
        )

        self.unrealized_positions = Gauge(
            "triangular_arbitrage_unrealized_positions",
            "Current unrealized positions by currency",
            ["strategy_name", "currency"],
            registry=self.registry,
        )

        # === RISK CONTROL METRICS ===
        self.cooldown_count = Gauge(
            "triangular_arbitrage_cooldown_count",
            "Number of cycles currently in cooldown",
            ["strategy_name"],
            registry=self.registry,
        )

        self.risk_violations_total = Counter(
            "triangular_arbitrage_risk_violations_total",
            "Total risk control violations",
            ["strategy_name", "violation_type"],
            registry=self.registry,
        )

        self.consecutive_losses = Gauge(
            "triangular_arbitrage_consecutive_losses",
            "Current consecutive loss count",
            ["strategy_name"],
            registry=self.registry,
        )

        # === ORDER EXECUTION METRICS ===
        self.orders_placed_total = Counter(
            "triangular_arbitrage_orders_placed_total",
            "Total orders placed",
            ["strategy_name", "execution_mode", "market_symbol", "side"],
            registry=self.registry,
        )

        self.orders_filled_total = Counter(
            "triangular_arbitrage_orders_filled_total",
            "Total orders filled",
            ["strategy_name", "execution_mode", "market_symbol", "side"],
            registry=self.registry,
        )

        self.order_fill_ratio = Gauge(
            "triangular_arbitrage_order_fill_ratio",
            "Ratio of filled to placed orders (last 100 orders)",
            ["strategy_name", "execution_mode"],
            registry=self.registry,
        )

        self.slippage_basis_points = Histogram(
            "triangular_arbitrage_slippage_basis_points",
            "Order slippage in basis points",
            ["strategy_name", "execution_mode", "market_symbol"],
            buckets=[0, 1, 2, 5, 10, 20, 50, 100, 200],
            registry=self.registry,
        )

        self.execution_fees = Counter(
            "triangular_arbitrage_execution_fees_total",
            "Total execution fees paid",
            ["strategy_name", "execution_mode", "currency"],
            registry=self.registry,
        )

        # === SYSTEM HEALTH METRICS ===
        self.strategy_uptime_seconds = Gauge(
            "triangular_arbitrage_strategy_uptime_seconds",
            "Strategy uptime in seconds",
            ["strategy_name"],
            registry=self.registry,
        )

        self.last_activity_timestamp = Gauge(
            "triangular_arbitrage_last_activity_timestamp",
            "Unix timestamp of last trading activity",
            ["strategy_name"],
            registry=self.registry,
        )

        self.active_balance = Gauge(
            "triangular_arbitrage_active_balance",
            "Current active balance by currency",
            ["strategy_name", "currency", "execution_mode"],
            registry=self.registry,
        )

        self.system_errors_total = Counter(
            "triangular_arbitrage_system_errors_total",
            "Total system errors encountered",
            ["strategy_name", "error_type"],
            registry=self.registry,
        )

    # === METRIC RECORDING METHODS ===

    def record_cycle_started(self, strategy_name: str, execution_mode: str = "live"):
        """Record a cycle start"""
        with self._lock:
            self.cycles_started_total.labels(
                strategy_name=strategy_name, execution_mode=execution_mode
            ).inc()

    def record_cycle_filled(
        self,
        strategy_name: str,
        execution_mode: str = "live",
        profit_bps: float = 0.0,
        duration_seconds: float = 0.0,
    ):
        """Record a successful cycle completion"""
        with self._lock:
            self.cycles_filled_total.labels(
                strategy_name=strategy_name, execution_mode=execution_mode
            ).inc()

            if profit_bps != 0.0:
                self.realized_profit_basis_points.labels(
                    strategy_name=strategy_name, execution_mode=execution_mode
                ).observe(profit_bps)

            if duration_seconds > 0:
                self.cycle_duration_seconds.labels(
                    strategy_name=strategy_name, execution_mode=execution_mode
                ).observe(duration_seconds)

    def record_cycle_canceled(self, strategy_name: str, reason: str):
        """Record a cycle cancellation"""
        with self._lock:
            if "slippage" in reason.lower():
                self.cycles_canceled_by_slippage_total.labels(
                    strategy_name=strategy_name
                ).inc()
            elif "latency" in reason.lower():
                self.cycles_canceled_by_latency_total.labels(
                    strategy_name=strategy_name
                ).inc()

    def record_partial_fill(self, strategy_name: str, execution_mode: str = "live"):
        """Record a partial fill event"""
        with self._lock:
            self.cycles_partial_filled_total.labels(
                strategy_name=strategy_name, execution_mode=execution_mode
            ).inc()

    def record_leg_latency(
        self,
        strategy_name: str,
        leg_number: int,
        market_symbol: str,
        latency_seconds: float,
    ):
        """Record latency for a specific leg"""
        with self._lock:
            self.leg_latency_seconds.labels(
                strategy_name=strategy_name,
                leg_number=leg_number,
                market_symbol=market_symbol,
            ).observe(latency_seconds)

    def record_order_placed(
        self, strategy_name: str, execution_mode: str, market_symbol: str, side: str
    ):
        """Record order placement"""
        with self._lock:
            self.orders_placed_total.labels(
                strategy_name=strategy_name,
                execution_mode=execution_mode,
                market_symbol=market_symbol,
                side=side,
            ).inc()

    def record_order_filled(
        self,
        strategy_name: str,
        execution_mode: str,
        market_symbol: str,
        side: str,
        slippage_bps: float = 0.0,
        fee_amount: float = 0.0,
        fee_currency: str = "USD",
    ):
        """Record order fill"""
        with self._lock:
            self.orders_filled_total.labels(
                strategy_name=strategy_name,
                execution_mode=execution_mode,
                market_symbol=market_symbol,
                side=side,
            ).inc()

            if slippage_bps != 0.0:
                self.slippage_basis_points.labels(
                    strategy_name=strategy_name,
                    execution_mode=execution_mode,
                    market_symbol=market_symbol,
                ).observe(abs(slippage_bps))

            if fee_amount > 0:
                self.execution_fees.labels(
                    strategy_name=strategy_name,
                    execution_mode=execution_mode,
                    currency=fee_currency,
                ).inc(fee_amount)

    def update_cooldown_count(self, strategy_name: str, count: int):
        """Update active cooldown count"""
        with self._lock:
            self.cooldown_count.labels(strategy_name=strategy_name).set(count)

    def record_risk_violation(self, strategy_name: str, violation_type: str):
        """Record risk control violation"""
        with self._lock:
            self.risk_violations_total.labels(
                strategy_name=strategy_name, violation_type=violation_type
            ).inc()

    def update_consecutive_losses(self, strategy_name: str, count: int):
        """Update consecutive loss count"""
        with self._lock:
            self.consecutive_losses.labels(strategy_name=strategy_name).set(count)

    def update_balance(
        self,
        strategy_name: str,
        currency: str,
        balance: float,
        execution_mode: str = "live",
    ):
        """Update active balance"""
        with self._lock:
            self.active_balance.labels(
                strategy_name=strategy_name,
                currency=currency,
                execution_mode=execution_mode,
            ).set(balance)

    def update_pnl(
        self, strategy_name: str, execution_mode: str, currency: str, pnl: float
    ):
        """Update cumulative P&L"""
        with self._lock:
            self.total_profit_loss.labels(
                strategy_name=strategy_name,
                execution_mode=execution_mode,
                currency=currency,
            ).set(pnl)

    def record_system_error(self, strategy_name: str, error_type: str):
        """Record system error"""
        with self._lock:
            self.system_errors_total.labels(
                strategy_name=strategy_name, error_type=error_type
            ).inc()

    def update_last_activity(self, strategy_name: str):
        """Update last activity timestamp"""
        with self._lock:
            self.last_activity_timestamp.labels(strategy_name=strategy_name).set(
                time.time()
            )

    # === SERVER MANAGEMENT ===

    async def start_server(
        self, port: int = 8000, host: str = "0.0.0.0", path: str = "/metrics"
    ):
        """Start Prometheus metrics HTTP server"""
        try:
            self._app = web.Application()
            self._app.router.add_get(path, self._metrics_handler)
            self._app.router.add_get("/health", self._health_handler)

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()

            self._site = web.TCPSite(self._runner, host, port)
            await self._site.start()

            logger.info(
                f"📊 Prometheus metrics server started on http://{host}:{port}{path}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            return False

    async def stop_server(self):
        """Stop the metrics server"""
        try:
            if self._site:
                await self._site.stop()
            if self._runner:
                await self._runner.cleanup()
            logger.info("📊 Metrics server stopped")
        except Exception as e:
            logger.error(f"Error stopping metrics server: {e}")

    async def _metrics_handler(self, request):
        """Handle metrics endpoint requests"""
        try:
            metrics_output = generate_latest(self.registry)
            # Strip charset from content type to avoid conflicts with aiohttp
            content_type = CONTENT_TYPE_LATEST.split(';')[0]  # Remove charset part
            return web.Response(
                text=metrics_output.decode("utf-8"), content_type=content_type
            )
        except Exception as e:
            logger.error(f"Error generating metrics: {e}")
            return web.Response(text="Error generating metrics", status=500)

    async def _health_handler(self, request):
        """Handle health check endpoint"""
        return web.Response(
            text='{"status": "healthy", "service": "triangular_arbitrage_metrics"}',
            content_type="application/json",
        )

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        try:
            # This would ideally parse the current metric values
            # For now, return basic info
            return {
                "metrics_available": True,
                "registry_collectors": len(
                    list(self.registry._collector_to_names.keys())
                ),
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            return {"metrics_available": False, "error": str(e)}


class VolatilityMonitor:
    """
    Rolling-window monitor for net profit volatility.

    Tracks a fixed-size window of net_pct observations and computes
    moving average and standard deviation. Used by DecisionEngine to
    derive dynamic profit thresholds.
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._observations: deque = deque(maxlen=window_size)

    def add_observation(self, net_pct: float) -> None:
        """Record a net profit percentage observation."""
        self._observations.append(float(net_pct))

    @property
    def count(self) -> int:
        """Number of observations currently stored."""
        return len(self._observations)

    @property
    def is_ready(self) -> bool:
        """Whether the window is fully populated."""
        return len(self._observations) >= self.window_size

    def get_moving_average(self) -> Optional[float]:
        """Mean of the rolling window, or None if fewer than 2 observations."""
        if len(self._observations) < 2:
            return None
        return sum(self._observations) / len(self._observations)

    def get_sigma(self) -> Optional[float]:
        """Population standard deviation, or None if fewer than 2 observations."""
        n = len(self._observations)
        if n < 2:
            return None
        mean = sum(self._observations) / n
        variance = sum((x - mean) ** 2 for x in self._observations) / n
        return variance ** 0.5

    def get_dynamic_threshold(self, sigma_multiplier: float) -> Optional[float]:
        """Compute moving_avg + sigma_multiplier * sigma, or None if insufficient data."""
        avg = self.get_moving_average()
        sigma = self.get_sigma()
        if avg is None or sigma is None:
            return None
        return avg + sigma_multiplier * sigma


# Global metrics instance (singleton pattern)
_global_metrics: Optional[TradingMetrics] = None


def get_metrics() -> TradingMetrics:
    """Get or create global metrics instance"""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = TradingMetrics()
    return _global_metrics


def initialize_metrics(registry: Optional[CollectorRegistry] = None) -> TradingMetrics:
    """Initialize global metrics with custom registry"""
    global _global_metrics
    _global_metrics = TradingMetrics(registry)
    return _global_metrics
