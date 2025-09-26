"""
Constants and enums for the triangular arbitrage system.

Centralizes string literals, magic numbers, and configuration constants
to reduce duplication and improve maintainability.
"""

from enum import Enum, IntEnum


class ExecutionMode(Enum):
    """Execution modes for the trading system."""

    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"


class OrderSide(Enum):
    """Order side enumeration."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status enumeration."""

    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(Enum):
    """Order type enumeration."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class PositionStatus(Enum):
    """Position status enumeration."""

    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


class RiskLevel(Enum):
    """Risk level enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MetricType(Enum):
    """Metric type enumeration for observability."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class LogLevel(IntEnum):
    """Log level enumeration."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class ExchangeStatus(Enum):
    """Exchange connection status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class StrategyState(Enum):
    """Strategy execution state."""

    IDLE = "idle"
    SCANNING = "scanning"
    EXECUTING = "executing"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class CyclePhase(Enum):
    """Triangular arbitrage cycle phases."""

    DETECTION = "detection"
    VALIDATION = "validation"
    EXECUTION = "execution"
    RECONCILIATION = "reconciliation"
    COMPLETED = "completed"
    FAILED = "failed"


# Default configuration constants
DEFAULT_CONFIG = {
    "MIN_PROFIT_THRESHOLD": 0.001,
    "MAX_TRADE_AMOUNT_BTC": 0.1,
    "FEE_RATE": 0.001,
    "POSITION_TIMEOUT_SECONDS": 300,
    "MAX_OPEN_POSITIONS": 3,
    "RATE_LIMIT_REQUESTS_PER_MINUTE": 60,
    "CONNECTION_TIMEOUT_SECONDS": 30,
    "RETRY_MAX_ATTEMPTS": 3,
    "RETRY_BACKOFF_SECONDS": 1.0,
}

# Network and API constants
NETWORK_CONFIG = {
    "DEFAULT_PROMETHEUS_PORT": 8000,
    "DEFAULT_GRAFANA_PORT": 3000,
    "DEFAULT_API_TIMEOUT": 30,
    "DEFAULT_WEBSOCKET_TIMEOUT": 10,
    "MAX_RECONNECTION_ATTEMPTS": 5,
    "RECONNECTION_DELAY_SECONDS": 5,
}

# Trading constants
TRADING_CONSTANTS = {
    "MIN_ORDER_SIZE_BTC": 0.00001,
    "MIN_ORDER_SIZE_ETH": 0.001,
    "MIN_ORDER_SIZE_USDT": 1.0,
    "PRICE_PRECISION": 8,
    "QUANTITY_PRECISION": 8,
    "SLIPPAGE_TOLERANCE": 0.001,
    "EXECUTION_TIMEOUT_SECONDS": 60,
}

# Risk management constants
RISK_CONSTANTS = {
    "MAX_POSITION_SIZE_RATIO": 0.1,
    "MAX_DAILY_LOSS_RATIO": 0.05,
    "MAX_DRAWDOWN_RATIO": 0.1,
    "STOP_LOSS_RATIO": 0.02,
    "TAKE_PROFIT_RATIO": 0.01,
    "VOLATILITY_THRESHOLD": 0.05,
}

# Observability constants
METRICS_CONSTANTS = {
    "METRIC_PREFIX": "triangular_arbitrage",
    "DEFAULT_BUCKETS": [0.001, 0.01, 0.1, 1.0, 10.0],
    "HISTOGRAM_BUCKETS_LATENCY": [
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ],
    "HISTOGRAM_BUCKETS_PROFIT": [0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
    "METRIC_RETENTION_SECONDS": 86400 * 30,  # 30 days
}

# File and path constants
PATH_CONSTANTS = {
    "DEFAULT_CONFIG_DIR": "configs",
    "DEFAULT_STRATEGY_DIR": "configs/strategies",
    "DEFAULT_DATA_DIR": "data",
    "DEFAULT_BACKTEST_DIR": "backtests",
    "DEFAULT_LOG_DIR": "logs",
    "DEFAULT_METRICS_DIR": "metrics",
    "CONFIG_FILE_EXTENSION": ".yaml",
    "LOG_FILE_EXTENSION": ".log",
}

# Time constants
TIME_CONSTANTS = {
    "MILLISECONDS_PER_SECOND": 1000,
    "SECONDS_PER_MINUTE": 60,
    "MINUTES_PER_HOUR": 60,
    "HOURS_PER_DAY": 24,
    "SECONDS_PER_DAY": 86400,
    "DEFAULT_TIMEZONE": "UTC",
    "TIMESTAMP_FORMAT": "%Y-%m-%d %H:%M:%S.%f",
    "DATE_FORMAT": "%Y-%m-%d",
}

# Exchange-specific constants
EXCHANGE_CONSTANTS = {
    "BINANCE": {
        "NAME": "binance",
        "BASE_URL_MAINNET": "https://api.binance.com",
        "BASE_URL_TESTNET": "https://testnet.binance.vision",
        "WEBSOCKET_URL_MAINNET": "wss://stream.binance.com:9443/ws",
        "WEBSOCKET_URL_TESTNET": "wss://testnet.binance.vision/ws",
        "RATE_LIMIT_WEIGHT": 1200,
        "RATE_LIMIT_ORDERS": 100,
    },
    "COINBASE": {
        "NAME": "coinbase",
        "BASE_URL_MAINNET": "https://api.exchange.coinbase.com",
        "BASE_URL_SANDBOX": "https://api-public.sandbox.exchange.coinbase.com",
        "WEBSOCKET_URL_MAINNET": "wss://ws-feed.exchange.coinbase.com",
        "WEBSOCKET_URL_SANDBOX": "wss://ws-feed-public.sandbox.exchange.coinbase.com",
        "RATE_LIMIT_REQUESTS": 10,
    },
}

# Validation constants
VALIDATION_CONSTANTS = {
    "MIN_STRATEGY_NAME_LENGTH": 1,
    "MAX_STRATEGY_NAME_LENGTH": 100,
    "MIN_SYMBOL_LENGTH": 6,
    "MAX_SYMBOL_LENGTH": 20,
    "MIN_PROFIT_THRESHOLD": 0.0001,
    "MAX_PROFIT_THRESHOLD": 0.1,
    "MIN_FEE_RATE": 0.0,
    "MAX_FEE_RATE": 0.01,
}
