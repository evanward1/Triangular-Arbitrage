"""
CEX Trading Constants and Configuration

Extracted from trading_arbitrage.py to centralize exchange-specific
constants and default configuration values.
"""

import os
from typing import Dict

# Exchange-specific fee structures (maker/taker)
EXCHANGE_FEES: Dict[str, Dict[str, float]] = {
    "binanceus": {"maker": 0.001, "taker": 0.001},  # 0.10%
    "binance": {"maker": 0.001, "taker": 0.001},  # 0.10% (0.075% with BNB)
    "kraken": {"maker": 0.0016, "taker": 0.0026},  # 0.16% maker, 0.26% taker
    "kucoin": {"maker": 0.001, "taker": 0.001},  # 0.10%
    "coinbase": {"maker": 0.004, "taker": 0.006},  # 0.40% maker, 0.60% taker
}


class TradingConfig:
    """
    Centralized trading configuration with environment variable support.

    This class provides a single source of truth for all trading parameters,
    making it easier to manage configuration across different deployment environments.
    """

    def __init__(self):
        # Connection settings
        self.connection_timeout_seconds = int(
            os.getenv("CONNECTION_TIMEOUT_SECONDS", "30")
        )
        self.max_connection_retries = int(os.getenv("MAX_CONNECTION_RETRIES", "3"))
        self.initial_retry_delay = 2.0  # seconds

        # Safety limits
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "100"))
        self.min_profit_threshold = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.20"))
        self.max_leg_latency_ms = int(os.getenv("MAX_LEG_LATENCY_MS", "2000"))

        # Sizing configuration
        self.depth_abs_min_usd = float(os.getenv("DEPTH_ABS_MIN_USD", "10.0"))
        self.depth_rel_min_frac = float(os.getenv("DEPTH_REL_MIN_FRAC", "0.002"))
        self.leg_min_notional_usd = float(os.getenv("LEG_MIN_NOTIONAL_USD", "10.0"))

        # Slippage estimation
        self.slippage_pct_estimate = float(os.getenv("SLIPPAGE_PCT_ESTIMATE", "0.05"))
        self.slippage_mode = os.getenv("SLIPPAGE_MODE", "static").lower()
        self.slippage_floor_bps = float(os.getenv("SLIPPAGE_FLOOR_BPS", "2"))
        self.max_slippage_leg_bps = float(os.getenv("MAX_SLIPPAGE_LEG_BPS", "35"))

        # Kill-switch for daily loss
        self.kill_switch_enabled = (
            os.getenv("KILL_SWITCH_ENABLED", "true").lower() == "true"
        )
        self.max_daily_drawdown_pct = float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "2.0"))

        # Display settings
        self.verbosity = os.getenv("VERBOSITY", "normal").lower()
        self.topn = int(os.getenv("TOPN", "3"))
        self.equity_print_every = int(os.getenv("EQUITY_PRINT_EVERY", "5"))
        self.run_min = int(os.getenv("RUN_MIN", "0"))

        # Dedupe settings
        self.change_bps = int(os.getenv("CHANGE_BPS", "3"))
        self.print_every_n = int(os.getenv("PRINT_EVERY_N", "6"))
        self.dedupe = os.getenv("DEDUPE", "true").lower() == "true"

        # Delta display settings
        self.show_delta = os.getenv("SHOW_DELTA", "true").lower() == "true"

        # Reason buckets
        self.reason_buckets = os.getenv("REASON_BUCKETS", "true").lower() == "true"

        # Maker-taker
        self.favor_maker = os.getenv("FAVOR_MAKER", "true").lower() == "true"
        self.maker_depth_fraction = float(os.getenv("MAKER_DEPTH_FRACTION", "0.10"))
        self.maker_fallback_allowed = (
            os.getenv("MAKER_FALLBACK_ALLOWED", "true").lower() == "true"
        )
        self.assume_maker_for_net = (
            os.getenv("ASSUME_MAKER_FOR_NET", "false").lower() == "true"
        )

        # Breakeven guard
        self.breakeven_enabled = (
            os.getenv("BREAKEVEN_ENABLED", "true").lower() == "true"
        )

        # CSV logging
        self.enable_csv_logging = (
            os.getenv("ENABLE_CSV_LOGGING", "false").lower() == "true"
        )
        self.csv_log_path = os.getenv("CSV_LOG_PATH", "arb_scans.csv")

        # Equity tracking
        self.equity_precision = int(os.getenv("EQUITY_PRECISION", "2"))

    def get_exchange_fee(self, exchange_name: str, order_type: str = "taker") -> float:
        """
        Get the fee for a specific exchange and order type.

        Args:
            exchange_name: Name of the exchange (e.g., 'binance', 'kraken')
            order_type: 'maker' or 'taker'

        Returns:
            Fee as a decimal (e.g., 0.001 for 0.1%)
        """
        exchange_name = exchange_name.lower()
        if exchange_name not in EXCHANGE_FEES:
            raise ValueError(f"Unknown exchange: {exchange_name}")

        if order_type not in ["maker", "taker"]:
            raise ValueError(f"Invalid order type: {order_type}")

        return EXCHANGE_FEES[exchange_name][order_type]

    def to_dict(self) -> Dict:
        """Export configuration as dictionary for logging/debugging."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


# Default configuration instance
DEFAULT_CONFIG = TradingConfig()
