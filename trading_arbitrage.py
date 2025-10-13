#!/usr/bin/env python3
"""
Real Trading Triangular Arbitrage Implementation
WARNING: This trades with real money. Use at your own risk.
"""

import asyncio
import logging
import os
import platform
import random
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional

import ccxt
import networkx as nx

from decision_engine import DecisionEngine
from equity_tracker import EquityTracker
from triangular_arbitrage.execution_helpers import (
    depth_fill_price,
    depth_limited_size,
    leg_timed,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Windows compatibility
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class SlippageMonitor:
    """
    Monitors per-symbol slippage over a rolling window to detect chronic offenders.
    Tracks median slippage and identifies pairs that consistently exceed caps.
    """

    def __init__(self, window: int = 20):
        """
        Initialize slippage monitor.

        Args:
            window: Number of samples to track per symbol (default 20)
        """
        self.window = window
        self.data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window))

    def record(self, symbol: str, slippage_pct: float):
        """
        Record a slippage observation for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BONK/USD")
            slippage_pct: Observed slippage percentage (e.g., 1.23 for 1.23%)
        """
        self.data[symbol].append(slippage_pct)

    def median(self, symbol: str) -> float:
        """
        Calculate median slippage for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Median slippage percentage, or 0.0 if no data
        """
        if symbol not in self.data or not self.data[symbol]:
            return 0.0

        sorted_data = sorted(self.data[symbol])
        n = len(sorted_data)
        if n % 2 == 1:
            return sorted_data[n // 2]
        else:
            return 0.5 * (sorted_data[n // 2 - 1] + sorted_data[n // 2])

    def is_chronic(self, symbol: str, cap: float) -> bool:
        """
        Check if a symbol is a chronic slippage offender.

        Args:
            symbol: Trading pair symbol
            cap: Slippage cap percentage to compare against

        Returns:
            True if median slippage exceeds cap, False otherwise
        """
        # Need at least half the window filled to make a determination
        if symbol not in self.data or len(self.data[symbol]) < self.window // 2:
            return False

        return self.median(symbol) > cap

    def get_stats(self, symbol: str) -> Dict[str, float]:
        """
        Get statistics for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary with 'median', 'count', 'min', 'max' keys
        """
        if symbol not in self.data or not self.data[symbol]:
            return {"median": 0.0, "count": 0, "min": 0.0, "max": 0.0}

        data_list = list(self.data[symbol])
        return {
            "median": self.median(symbol),
            "count": len(data_list),
            "min": min(data_list),
            "max": max(data_list),
        }


class RealTriangularArbitrage:
    # Exchange-specific fee structures (maker/taker)
    EXCHANGE_FEES = {
        "binanceus": {"maker": 0.001, "taker": 0.001},  # 0.10%
        "binance": {"maker": 0.001, "taker": 0.001},  # 0.10% (0.075% with BNB)
        "kraken": {"maker": 0.0016, "taker": 0.0026},  # 0.16%/0.26%
        "kucoin": {"maker": 0.001, "taker": 0.001},  # 0.10%
        "coinbase": {"maker": 0.004, "taker": 0.006},  # 0.40%/0.60%
    }

    def __init__(self, exchange_name: str = "binanceus", trading_mode: str = "paper"):
        """Initialize real trading arbitrage system"""
        self.exchange_name = exchange_name.lower()
        self.trading_mode = trading_mode  # 'paper' or 'live'
        self.exchange = None
        self.symbols = []
        self.tickers = {}
        self.graph = nx.DiGraph()
        self.balances = {}
        self.paper_balances = {}  # Track paper trading balances separately

        # Connection timeout and retry configuration
        self.connection_timeout_seconds = int(
            os.getenv("CONNECTION_TIMEOUT_SECONDS", "30")
        )
        self.max_connection_retries = int(os.getenv("MAX_CONNECTION_RETRIES", "3"))
        self.initial_retry_delay = (
            2.0  # Initial delay in seconds for exponential backoff
        )

        # Safety limits
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "100"))
        self.min_profit_threshold = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.20"))
        self.max_leg_latency_ms = int(os.getenv("MAX_LEG_LATENCY_MS", "2000"))

        # Sizing configuration (smarter depth gating)
        self.depth_abs_min_usd = float(
            os.getenv("DEPTH_ABS_MIN_USD", "10.0")
        )  # Absolute minimum
        self.depth_rel_min_frac = float(
            os.getenv("DEPTH_REL_MIN_FRAC", "0.002")
        )  # 0.2% of balance
        self.leg_min_notional_usd = float(
            os.getenv("LEG_MIN_NOTIONAL_USD", "10.0")
        )  # Per-leg minimum

        # Slippage estimation
        self.slippage_pct_estimate = float(os.getenv("SLIPPAGE_PCT_ESTIMATE", "0.05"))
        self.slippage_mode = os.getenv(
            "SLIPPAGE_MODE", "static"
        ).lower()  # 'static' or 'dynamic'
        self.slippage_floor_bps = float(
            os.getenv("SLIPPAGE_FLOOR_BPS", "2")
        )  # Minimum slippage in basis points

        # Per-leg slippage caps
        self.max_slippage_leg_bps = float(
            os.getenv("MAX_SLIPPAGE_LEG_BPS", "35")
        )  # Max slippage per leg (35 bps = 0.35%)

        # Kill-switch for daily loss
        self.kill_switch_enabled = (
            os.getenv("KILL_SWITCH_ENABLED", "true").lower() == "true"
        )
        self.max_daily_drawdown_pct = float(
            os.getenv("MAX_DAILY_DRAWDOWN_PCT", "2.0")
        )  # Max daily loss % (2.0 = 2%)
        self.kill_switch_active = False  # Will be set if threshold breached

        # Display settings
        self.verbosity = os.getenv("VERBOSITY", "normal").lower()
        self.topn = int(os.getenv("TOPN", "3"))
        self.equity_print_every = int(
            os.getenv("EQUITY_PRINT_EVERY", "5")
        )  # Print equity every N scans
        self.run_min = int(os.getenv("RUN_MIN", "0"))

        # Dedupe settings
        self.change_bps = int(os.getenv("CHANGE_BPS", "3"))
        self.print_every_n = int(os.getenv("PRINT_EVERY_N", "6"))
        self.dedupe = os.getenv("DEDUPE", "true").lower() == "true"
        self._last_key = None
        self._last_net = None
        self._repeat = 0

        # Delta display settings
        self.show_delta = os.getenv("SHOW_DELTA", "true").lower() == "true"
        self._last_print_key = None
        self._last_print_net = None
        self._last_print_gross = None

        # Reason buckets
        self.reason_buckets = os.getenv("REASON_BUCKETS", "true").lower() == "true"
        self.reject_by_threshold = 0
        self.reject_by_fees = 0
        self.reject_by_slip = 0
        self.reject_by_depth = 0

        # USD P&L and EV accounting
        self.show_usd = os.getenv("SHOW_USD", "true").lower() == "true"
        self.ev_window = int(os.getenv("EV_WINDOW", "30"))
        self.ev_only_above_thr = (
            os.getenv("EV_ONLY_ABOVE_THR", "true").lower() == "true"
        )
        self.ev_day_factor = os.getenv("EV_DAY_FACTOR", "true").lower() == "true"
        self.realized_pnl_usd = 0.0
        self.hyp_best_pnl_usd_sum = 0.0
        self.hyp_best_count = 0
        self.evs = []

        # Equity accounting
        self.equity_precision = int(os.getenv("EQUITY_PRECISION", "2"))
        self.equity_every_n = int(os.getenv("EQUITY_EVERY_N", "3"))
        self.start_equity_usd = None
        self.last_equity_usd = None
        self.equity_curve = []  # [(ts, equity_usd)]

        # Initialize EquityTracker
        self.equity_tracker = EquityTracker(out_dir="logs")

        # Initialize SlippageMonitor for chronic offender detection
        slippage_monitor_window = int(os.getenv("SLIPPAGE_MONITOR_WINDOW", "20"))
        self.slippage_monitor = SlippageMonitor(window=slippage_monitor_window)

        # Near-miss detection
        self.near_miss_bps = (
            float(os.getenv("NEAR_MISS_BPS", "5")) / 100
        )  # Convert to percent

        # Test execution mode (paper only) - force small fills on near-miss opportunities
        self.test_execute_near_miss = (
            os.getenv("TEST_EXECUTE_NEAR_MISS", "false").lower() == "true"
        )
        self.test_near_miss_gap_bps = (
            float(os.getenv("TEST_NEAR_MISS_GAP_BPS", "8")) / 100.0
        )
        self.test_near_miss_size_usd = float(os.getenv("TEST_NEAR_MISS_SIZE_USD", "15"))

        # CSV logging
        self.write_scan_csv = os.getenv("WRITE_SCAN_CSV", "false").lower() == "true"

        # Paper balance defaults
        self.paper_usdt = float(os.getenv("PAPER_USDT", "1000"))
        self.paper_usdc = float(os.getenv("PAPER_USDC", "1000"))

        # Symbol curation
        self.symbol_allowlist = (
            os.getenv("SYMBOL_ALLOWLIST", "").split(",")
            if os.getenv("SYMBOL_ALLOWLIST")
            else []
        )
        self.symbol_allowlist = [
            s.strip().upper() for s in self.symbol_allowlist if s.strip()
        ]
        triangle_bases_env = os.getenv("TRIANGLE_BASES", "")
        if triangle_bases_env:
            self.triangle_bases = [
                s.strip().upper() for s in triangle_bases_env.split(",") if s.strip()
            ]
        else:
            self.triangle_bases = []  # Empty = allow all currencies as bases
        self.exclude_symbols = (
            os.getenv("EXCLUDE_SYMBOLS", "").split(",")
            if os.getenv("EXCLUDE_SYMBOLS")
            else []
        )
        self.exclude_symbols = [
            s.strip().upper() for s in self.exclude_symbols if s.strip()
        ]

        # Regex-based symbol exclusion for more flexible filtering
        import re

        self.exclude_symbols_regex = os.getenv("EXCLUDE_SYMBOLS_REGEX", "")
        self.exclude_symbols_pattern = (
            re.compile(self.exclude_symbols_regex)
            if self.exclude_symbols_regex
            else None
        )

        # Per-symbol slippage caps (format: "BONK/USD:0.20,PEPE/USD:0.25")
        self.per_symbol_slippage_caps = {}
        per_symbol_caps_env = os.getenv("PER_SYMBOL_SLIPPAGE_CAPS", "")
        if per_symbol_caps_env:
            for item in per_symbol_caps_env.split(","):
                item = item.strip()
                if ":" in item:
                    symbol, cap_str = item.split(":", 1)
                    try:
                        self.per_symbol_slippage_caps[symbol.strip()] = (
                            float(cap_str) / 100.0
                        )
                    except ValueError:
                        logger.warning(
                            f"Invalid per-symbol slippage cap format: {item}"
                        )

        # Stablecoin filtering
        self.exclude_stablecoin_only = (
            os.getenv("EXCLUDE_STABLECOIN_ONLY", "true").lower() == "true"
        )
        self.stablecoins = {
            "USD",
            "USDT",
            "USDC",
            "BUSD",
            "DAI",
            "TUSD",
            "USDP",
            "USDDOLLAR",
            "FDUSD",
            "USDD",
            "USDE",  # TRON, Bybit stables
        }

        # Depth and polling
        self.depth_levels = int(os.getenv("DEPTH_LEVELS", "20"))
        self.poll_sec = int(os.getenv("POLL_SEC", "10"))
        self.depth_size_max_slippage_pct = float(
            os.getenv("DEPTH_SIZE_MAX_SLIPPAGE_PCT", "0.30")
        )  # Max slippage per leg when computing depth-limited size

        # Fee source
        self.fee_source = os.getenv("FEE_SOURCE", "static").lower()

        # Execution fee assumptions (for more accurate opportunity filtering)
        self.expected_maker_legs = int(os.getenv("EXPECTED_MAKER_LEGS", "2"))  # 0-3
        self.maker_prob = float(
            os.getenv("MAKER_PROB", "0.6")
        )  # Probability of maker fill

        # Live safety
        self.live_confirm = os.getenv("LIVE_CONFIRM", "NO").upper()

        # EMA tracking
        self.ema_alpha = 2 / (15 + 1)  # EMA(15)
        self.ema_gross = None
        self.ema_net = None

        # Set exchange-specific fees (will be updated in _setup_exchange if FEE_SOURCE=auto)
        self.fee_structure = self.EXCHANGE_FEES.get(
            self.exchange_name, {"maker": 0.002, "taker": 0.002}
        )
        self.maker_fee = self.fee_structure["maker"]
        self.taker_fee = self.fee_structure["taker"]
        self.fee_source_actual = "static"  # Will be updated if auto succeeds

        # Execution quality tracking
        self.execution_stats = {
            "attempts": 0,
            "full_fills": 0,
            "partial_fills": 0,
            "cancels": 0,
            "depth_rejects": 0,
            "slippage_rejects": 0,
            "timeouts": 0,
            "maker_used_count": 0,
            "maker_to_taker_fallbacks": 0,
        }
        self.trade_history = []  # Store executed trades with metrics
        self._last_scan_best = None  # Store best opportunity for CSV logging

        # Setup CSV logging
        if self.verbosity == "debug":
            os.makedirs("logs", exist_ok=True)

        self._setup_exchange()

        # Initialize DecisionEngine
        self.decision_engine = DecisionEngine(
            {
                "min_profit_threshold_pct": self.min_profit_threshold,
                "max_position_usd": self.max_position_size,
                "expected_maker_legs": self.expected_maker_legs,
            }
        )
        self.decision_history = deque(maxlen=100)

    async def _retry_with_backoff(self, func, operation_name, *args, **kwargs):
        """Execute a function with retry logic and exponential backoff.

        Implements exponential backoff with jitter to handle transient failures.
        The delay between retries doubles each time, with random jitter added
        to prevent thundering herd problems.

        Args:
            func: The function to execute
            operation_name: Name of the operation for logging
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The return value of the successful function call

        Raises:
            The last exception if all retries fail
        """
        last_exception = None

        for attempt in range(self.max_connection_retries):
            try:
                if attempt > 0:
                    # Calculate exponential backoff with jitter
                    base_delay = self.initial_retry_delay * (2 ** (attempt - 1))
                    # Add jitter: ±25% of base delay
                    jitter = base_delay * 0.25 * (2 * random.random() - 1)
                    delay = base_delay + jitter

                    logger.info(
                        f"🔄 Retrying {operation_name} (attempt {attempt + 1}/{self.max_connection_retries}) "
                        f"after {delay:.1f}s delay..."
                    )
                    await asyncio.sleep(delay)

                # Try to execute the function
                result = func(*args, **kwargs)

                if attempt > 0:
                    logger.info(
                        f"✅ {operation_name} succeeded after {attempt + 1} attempts"
                    )

                return result

            except (ccxt.RequestTimeout, ccxt.NetworkError) as e:
                last_exception = e

                if attempt < self.max_connection_retries - 1:
                    # Still have retries left
                    logger.warning(
                        f"⚠️ {operation_name} failed (attempt {attempt + 1}/{self.max_connection_retries}): {e}"
                    )
                    logger.info("💡 Will retry with exponential backoff...")
                else:
                    # This was the last attempt
                    logger.error(
                        f"❌ {operation_name} failed after {self.max_connection_retries} attempts: {e}"
                    )
                    logger.error(
                        "💡 Consider increasing MAX_CONNECTION_RETRIES or CONNECTION_TIMEOUT_SECONDS"
                    )
                    raise

            except Exception as e:
                # For non-network errors, don't retry
                logger.error(f"❌ {operation_name} failed with non-retryable error: {e}")
                raise

        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError(
                f"{operation_name} failed without exception"
            )  # noqa: F541

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for consistent comparisons"""
        # Uppercase, strip whitespace, remove common separators
        normalized = (
            symbol.strip().upper().replace("-", "").replace("_", "").replace(".", "")
        )
        # Handle common aliases
        if normalized in ["USDDOLLAR", "USDOLLAR"]:
            normalized = "USD"
        return normalized

    def _clamp_for_display(
        self, value: float, min_val: float = -10.0, max_val: float = 10.0
    ) -> float:
        """Clamp profit percentages to reasonable display range"""
        if value < min_val:
            return min_val
        elif value > max_val:
            return max_val
        return value

    def _setup_exchange(self):
        """Setup exchange with API credentials"""
        try:
            if self.exchange_name.lower() == "binanceus":
                self.exchange = ccxt.binanceus(
                    {
                        "apiKey": os.getenv("BINANCEUS_API_KEY"),
                        "secret": os.getenv("BINANCEUS_SECRET"),
                        "enableRateLimit": True,
                        "sandbox": False,
                        "options": {
                            "defaultType": "spot",
                        },
                    }
                )
            elif self.exchange_name.lower() == "binance":
                self.exchange = ccxt.binance(
                    {
                        "apiKey": os.getenv("BINANCE_API_KEY"),
                        "secret": os.getenv("BINANCE_SECRET"),
                        "enableRateLimit": True,
                        "sandbox": False,
                        "options": {
                            "defaultType": "spot",
                        },
                        # Add proxy if configured
                        "proxies": {
                            "http": os.getenv("HTTP_PROXY"),
                            "https": os.getenv("HTTPS_PROXY"),
                        }
                        if os.getenv("HTTP_PROXY")
                        else None,
                    }
                )
            elif self.exchange_name.lower() == "kraken":
                self.exchange = ccxt.kraken(
                    {
                        "apiKey": os.getenv("KRAKEN_API_KEY"),
                        "secret": os.getenv("KRAKEN_SECRET"),
                        "enableRateLimit": True,
                        "sandbox": False,  # Always use live data, even in paper mode
                    }
                )
            elif self.exchange_name.lower() == "kucoin":
                self.exchange = ccxt.kucoin(
                    {
                        "apiKey": os.getenv("KUCOIN_API_KEY"),
                        "secret": os.getenv("KUCOIN_SECRET"),
                        "password": os.getenv("KUCOIN_PASSWORD"),
                        "enableRateLimit": True,
                        "sandbox": False,  # Always use live data, even in paper mode
                    }
                )
            elif self.exchange_name.lower() == "coinbase":
                self.exchange = ccxt.coinbasepro(
                    {
                        "apiKey": os.getenv("COINBASE_API_KEY"),
                        "secret": os.getenv("COINBASE_SECRET"),
                        "passphrase": os.getenv("COINBASE_PASSPHRASE"),
                        "enableRateLimit": True,
                        "sandbox": False,  # Always use live data, even in paper mode
                    }
                )
            else:
                raise ValueError(f"Unsupported exchange: {self.exchange_name}")

            # Fetch real fees if FEE_SOURCE=auto
            if self.fee_source == "auto":
                try:
                    if hasattr(self.exchange, "fetch_trading_fees"):
                        fees = self.exchange.fetch_trading_fees()
                        if fees and "maker" in fees and "taker" in fees:
                            self.maker_fee = fees["maker"]
                            self.taker_fee = fees["taker"]
                            self.fee_source_actual = "auto"
                    elif hasattr(self.exchange, "load_markets"):
                        # Try getting from markets metadata
                        self.exchange.load_markets()
                        if self.exchange.markets:
                            # Get fees from first market as fallback
                            first_market = list(self.exchange.markets.values())[0]
                            if "maker" in first_market and "taker" in first_market:
                                self.maker_fee = first_market["maker"]
                                self.taker_fee = first_market["taker"]
                                self.fee_source_actual = "auto"
                except Exception:
                    pass  # Keep static fees

        except Exception as e:
            logger.error(f"❌ Failed to setup exchange: {e}")
            raise

    async def fetch_balances(self) -> Dict:
        """Fetch current account balances"""
        try:
            # In paper mode without API keys, skip real balance fetch
            if self.trading_mode == "paper" and not os.getenv(
                f"{self.exchange_name.upper()}_API_KEY"
            ):
                self.balances = {}
            else:
                # Fetch real balances from exchange
                self.balances = self.exchange.fetch_balance()

            # In paper mode, initialize paper balances on first fetch
            if self.trading_mode == "paper" and not self.paper_balances:
                # Choose base unit from env
                base_cash = os.getenv("BASE_CASH", "USDT")
                start_cash = float(os.getenv(f"PAPER_{base_cash}", "1000"))

                self.paper_balances = {
                    base_cash: {
                        "free": start_cash,
                        "used": 0.0,
                        "total": start_cash,
                    }
                }

            # Return balances (paper or real)
            display_balances = (
                self.paper_balances if self.trading_mode == "paper" else self.balances
            )
            return display_balances

        except Exception as e:
            logger.error(f"❌ Failed to fetch balances: {e}")
            return {}

    async def execute_trade(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "taker",
    ) -> Dict:
        """Execute a single trade with maker or taker option"""
        start_time = time.time()

        try:
            if self.trading_mode == "paper":
                # Simulate trade execution with REAL bid/ask prices
                # Note: Still crosses spread (no queue simulation), but respects maker vs taker fees
                if symbol in self.tickers:
                    ticker = self.tickers[symbol]
                    if side == "buy":
                        execution_price = ticker.get("ask", 1.0)
                        filled_amount = (
                            amount / execution_price if execution_price else amount
                        )
                    else:
                        execution_price = ticker.get("bid", 1.0)
                        filled_amount = amount * execution_price
                    # Use appropriate fee rate based on order type
                    fee_rate = (
                        self.maker_fee if order_type == "maker" else self.taker_fee
                    )
                else:
                    execution_price = 1.0
                    filled_amount = amount
                    fee_rate = self.taker_fee

                latency_ms = (time.time() - start_time) * 1000
                return {
                    "id": f"paper_{int(time.time())}",
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "filled": filled_amount,
                    "price": execution_price,
                    "status": "closed",
                    "fee": {"cost": filled_amount * fee_rate},
                    "order_type": order_type,
                    "latency_ms": latency_ms,
                }

            # Real trade execution
            if order_type == "maker":
                # Place limit order at best bid/ask
                order_book = self.exchange.fetch_order_book(symbol, limit=1)
                if side == "buy":
                    limit_price = (
                        order_book["asks"][0][0] if order_book["asks"] else None
                    )
                else:
                    limit_price = (
                        order_book["bids"][0][0] if order_book["bids"] else None
                    )

                if not limit_price:
                    return None

                order = self.exchange.create_limit_order(
                    symbol=symbol, side=side, amount=amount, price=limit_price
                )

                # Wait for fill with timeout
                wait_start = time.time()
                while (time.time() - wait_start) * 1000 < self.max_leg_latency_ms:
                    order_status = self.exchange.fetch_order(order["id"], symbol)
                    if order_status["status"] == "closed":
                        latency_ms = (time.time() - start_time) * 1000
                        order_status["order_type"] = "maker"
                        order_status["latency_ms"] = latency_ms
                        return order_status
                    await asyncio.sleep(0.1)

                # Timeout - cancel and fallback to taker
                self.exchange.cancel_order(order["id"], symbol)
                self.execution_stats["maker_to_taker_fallbacks"] += 1
                order_type = "taker"

            # Taker execution
            order = self.exchange.create_market_order(
                symbol=symbol, side=side, amount=amount
            )
            latency_ms = (time.time() - start_time) * 1000
            order["order_type"] = order_type
            order["latency_ms"] = latency_ms
            return order

        except Exception as e:
            logger.error(f"❌ Trade failed: {e}")
            return None

    async def should_use_maker(self, symbol: str, side: str, size: float) -> bool:
        """Determine if maker order is suitable for this leg"""
        try:
            # Check depth at top of book
            order_book = self.exchange.fetch_order_book(symbol, limit=1)
            book_side = order_book["asks"] if side == "buy" else order_book["bids"]

            if not book_side:
                return False

            top_size = book_side[0][1]
            return top_size >= size * 1.1  # 10% buffer

        except Exception:
            return False

    async def panic_sell(
        self, currency: str, amount: float, target_currency: str
    ) -> Dict:
        """Emergency sell to return to starting currency after failed trade"""
        try:
            logger.warning(
                f"🚨 PANIC SELL: Converting {amount:.4f} {currency} back to {target_currency}"
            )

            # Try direct pair first
            direct_pair = f"{currency}/{target_currency}"
            reverse_pair = f"{target_currency}/{currency}"

            if direct_pair in self.symbols:
                # Sell currency for target_currency
                trade = await self.execute_trade(
                    direct_pair, "sell", amount, order_type="taker"
                )
                if trade:
                    logger.info(f"✅ Panic sell successful: {trade}")
                    return {"success": True, "trade": trade}
            elif reverse_pair in self.symbols:
                # Buy target_currency with currency
                trade = await self.execute_trade(
                    reverse_pair, "buy", amount, order_type="taker"
                )
                if trade:
                    logger.info(f"✅ Panic sell successful: {trade}")
                    return {"success": True, "trade": trade}
            else:
                logger.error(
                    f"❌ No direct trading pair found for panic sell: {currency} -> {target_currency}"
                )
                return {"success": False, "error": "No direct pair"}

        except Exception as e:
            logger.error(f"❌ Panic sell failed: {e}")
            return {"success": False, "error": str(e)}

    async def execute_arbitrage_cycle(
        self,
        cycle: List[str],
        amount: float,
        legs_order_type: Optional[List[str]] = None,
    ) -> Dict:
        """Execute a complete arbitrage cycle with selective maker placement"""
        cycle_str = " -> ".join(cycle)

        if amount > self.max_position_size:
            logger.warning(
                f"⚠️ Amount {amount} exceeds max position size {self.max_position_size}"
            )
            amount = self.max_position_size

        start_currency = cycle[0]
        start_balance = amount
        current_amount = amount
        trades = []

        # In paper mode, check and update paper balances
        if self.trading_mode == "paper":
            # Check if we have enough balance
            available = self.paper_balances.get(start_currency, {}).get("free", 0)
            if available < amount:
                logger.error(
                    f"❌ Insufficient paper balance: {available} {start_currency} < {amount}"
                )
                return {"success": False, "error": "Insufficient balance"}

            # Deduct from starting currency
            self.paper_balances[start_currency]["free"] -= amount
            self.paper_balances[start_currency]["total"] -= amount

        leg_latencies = []
        fee_mix = []

        try:
            for i in range(len(cycle) - 1):
                from_currency = cycle[i]
                to_currency = cycle[i + 1]

                # Determine the correct trading pair and side
                buy_pair = f"{to_currency}/{from_currency}"
                sell_pair = f"{from_currency}/{to_currency}"

                if buy_pair in self.symbols:
                    symbol = buy_pair
                    side = "buy"
                elif sell_pair in self.symbols:
                    symbol = sell_pair
                    side = "sell"
                else:
                    logger.error(
                        f"❌ No trading pair found for {from_currency} -> {to_currency}"
                    )
                    break

                # Determine order type: maker for legs 0 and 2, taker for leg 1
                if legs_order_type:
                    order_type = legs_order_type[i]
                else:
                    # Default: try maker for legs 1 and 3, taker for leg 2
                    if i in [0, 2]:
                        use_maker = await self.should_use_maker(
                            symbol, side, current_amount
                        )
                        order_type = "maker" if use_maker else "taker"
                    else:
                        order_type = "taker"

                # Execute trade with latency guard
                trade = await leg_timed(
                    self.execute_trade(
                        symbol, side, current_amount, order_type=order_type
                    ),
                    timeout_ms=self.max_leg_latency_ms,
                    label=f"Step {i+1} {from_currency}->{to_currency}",
                )

                if not trade:
                    logger.error(f"❌ Trade failed at step {i+1}")
                    self.execution_stats["timeouts"] += 1

                    # If we're not at the first trade, we're holding an intermediate currency
                    # Attempt panic sell back to starting currency
                    if i > 0 and current_amount > 0:
                        current_currency = cycle[i]
                        logger.warning(
                            f"⚠️ Holding {current_amount:.4f} {current_currency}, attempting panic sell..."
                        )
                        panic_result = await self.panic_sell(
                            current_currency, current_amount, start_currency
                        )

                        if panic_result.get("success"):
                            panic_trade = panic_result.get("trade")
                            # Update amount after panic sell
                            fee = panic_trade.get("fee", {}).get(
                                "cost", current_amount * self.taker_fee
                            )
                            final_amount = (
                                panic_trade.get("filled", current_amount) - fee
                            )

                            # Update paper balances if in paper mode
                            if self.trading_mode == "paper":
                                self.paper_balances[start_currency][
                                    "free"
                                ] += final_amount
                                self.paper_balances[start_currency][
                                    "total"
                                ] += final_amount

                            loss = start_balance - final_amount
                            loss_pct = (loss / start_balance) * 100
                            logger.warning(
                                f"🚨 Panic sell completed. Loss: {loss:.4f} {start_currency} ({loss_pct:.2f}%)"
                            )

                            return {
                                "success": False,
                                "error": f"Trade {i+1} failed, panic sell executed",
                                "panic_sell": True,
                                "loss": loss,
                                "loss_percent": loss_pct,
                            }
                        else:
                            logger.error(
                                f"❌ Panic sell failed! You may be holding {current_amount:.4f} {current_currency}"
                            )
                            return {
                                "success": False,
                                "error": f"Trade {i+1} failed, panic sell also failed",
                                "panic_sell": False,
                                "stranded_currency": current_currency,
                                "stranded_amount": current_amount,
                            }

                    break

                trades.append(trade)
                leg_latencies.append(trade.get("latency_ms", 0))
                fee_mix.append(trade.get("order_type", "taker"))

                if trade.get("order_type") == "maker":
                    self.execution_stats["maker_used_count"] += 1

                # Update amount for next trade (subtract fees)
                fee_info = trade.get("fee")
                if fee_info and isinstance(fee_info, dict):
                    fee = fee_info.get("cost", current_amount * self.taker_fee)
                else:
                    fee = (
                        current_amount * self.taker_fee
                    )  # Use exchange-specific taker fee

                # Get the filled amount from the trade
                filled_amount = trade.get("filled") or trade.get("amount")
                filled_amount = filled_amount or current_amount

                # Ensure values are not None
                if fee is None:
                    fee = 0
                if filled_amount is None:
                    filled_amount = current_amount

                current_amount = float(filled_amount) - float(fee)
                logger.debug(
                    f"    Filled: {filled_amount}, Fee: {fee}, Remaining: {current_amount}"
                )

                # In live mode, wait for order confirmation before proceeding
                # In paper mode, no need to wait since orders are simulated
                if self.trading_mode == "live" and i < len(cycle) - 2:
                    # Wait for order to be fully filled (up to 5 seconds)
                    wait_start = time.time()
                    max_wait = 5.0
                    order_confirmed = False

                    while (time.time() - wait_start) < max_wait:
                        try:
                            # Fetch order status
                            order_status = self.exchange.fetch_order(
                                trade["id"], symbol
                            )
                            if order_status["status"] in ["closed", "filled"]:
                                order_confirmed = True
                                logger.info(
                                    f"    ✅ Order {trade['id']} confirmed as {order_status['status']}"
                                )
                                break
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            logger.warning(f"    ⚠️ Could not fetch order status: {e}")
                            break

                    if not order_confirmed:
                        logger.warning(
                            f"    ⚠️ Order confirmation timeout after {max_wait}s, proceeding anyway"
                        )
                elif self.trading_mode == "paper":
                    # Small delay in paper mode for realism
                    await asyncio.sleep(0.1)

            # Update paper balances with final amount
            if self.trading_mode == "paper":
                end_currency = cycle[-1]  # Should be same as start_currency
                if end_currency not in self.paper_balances:
                    self.paper_balances[end_currency] = {
                        "free": 0.0,
                        "used": 0.0,
                        "total": 0.0,
                    }

                self.paper_balances[end_currency]["free"] += current_amount
                self.paper_balances[end_currency]["total"] += current_amount

            profit = current_amount - start_balance
            profit_percent = (profit / start_balance) * 100

            # Track realized P&L in USD
            realized_usd = profit
            self.realized_pnl_usd += realized_usd

            # Record fill in equity tracker
            self.equity_tracker.on_fill(realized_usd)

            # Update equity after trade
            cur, _, _ = self._equity_usd()
            self.last_equity_usd = cur
            self.equity_curve.append((time.time(), cur))

            # Log compact execution line
            fee_mix_str = "/".join(fee_mix[:3])
            lat_str = (
                f"{leg_latencies[0]:.0f}/{leg_latencies[1]:.0f}/{leg_latencies[2]:.0f}"
                if len(leg_latencies) == 3
                else "N/A"
            )

            print(
                f"{time.strftime('%H:%M:%S')} {cycle_str} size={amount:.1f} "
                f"fee_mix={fee_mix_str} net={profit_percent:+.3f}% "
                f"lat_ms={lat_str} result=SUCCESS"
            )

            # Store trade metrics
            self.trade_history.append(
                {
                    "time": time.time(),
                    "cycle": cycle_str,
                    "size_usd": amount,
                    "fee_mix": fee_mix_str,
                    "net_pct": profit_percent,
                    "latencies_ms": leg_latencies,
                    "success": True,
                }
            )

            return {
                "success": True,
                "start_amount": start_balance,
                "final_amount": current_amount,
                "profit": profit,
                "profit_percent": profit_percent,
                "trades": trades,
                "leg_latencies": leg_latencies,
                "fee_mix": fee_mix,
            }

        except Exception as e:
            logger.error(f"❌ Arbitrage cycle failed: {e}")
            return {"success": False, "error": str(e)}

    async def check_order_book_depth(
        self, symbol: str, side: str, amount: float
    ) -> Dict:
        """Check if there's enough liquidity in the order book for the trade

        Args:
            symbol: Trading pair (e.g., "BTC/USD")
            side: "buy" or "sell"
            amount: Amount in FROM currency (quote for buy, base for sell)
        """
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit=self.depth_levels)

            # For buy orders, check asks (we need to buy from sellers)
            # For sell orders, check bids (we need to sell to buyers)
            orders = order_book["asks"] if side == "buy" else order_book["bids"]

            if not orders:
                return {"sufficient": False, "error": "Empty order book"}

            # Get best price (top of book)
            best_price = float(orders[0][0])

            # Convert amount to base units for proper comparison with order book volumes
            # amount is in FROM-currency units.
            # If BUY (to_currency/from_currency), we need BASE units = quote_amount / best_ask
            # If SELL (from_currency/to_currency), amount is already in BASE units
            target_base = (amount / best_price) if side == "buy" else amount

            cumulative_base = 0.0
            vwap_num = 0.0  # sum(price * base_taken)

            for order_entry in orders:
                # Order book entries are [price, volume] where volume is in BASE units
                price = float(order_entry[0])
                volume = float(order_entry[1])  # BASE units

                if cumulative_base >= target_base:
                    break
                take_base = min(target_base - cumulative_base, volume)
                vwap_num += price * take_base
                cumulative_base += take_base

            if cumulative_base < target_base:
                return {
                    "sufficient": False,
                    "available": cumulative_base,
                    "needed": target_base,
                    "avg_price": None,
                    "best_price": best_price,
                    "slippage_pct": None,
                }

            avg_price = vwap_num / target_base
            # Slippage = (avg_execution_price - best_price) / best_price
            slippage_pct = abs((avg_price - best_price) / best_price) * 100

            return {
                "sufficient": True,
                "available": cumulative_base,
                "needed": target_base,
                "avg_price": avg_price,
                "best_price": best_price,
                "slippage_pct": slippage_pct,
            }

        except Exception as e:
            logger.error(f"❌ Failed to check order book for {symbol}: {e}")
            return {"sufficient": False, "error": str(e)}

    async def estimate_cycle_slippage(
        self, cycle: List[str], amount_usd: float
    ) -> tuple[float, list[dict]]:
        """Estimate total slippage across all legs using order book depth

        Returns:
            tuple: (total_slippage_pct, per_leg_details)
            where per_leg_details is a list of dicts with keys: symbol, side, slippage_pct
        """
        books = []
        amounts = []
        leg_info = []  # Track symbol and side for each leg
        current_amount = amount_usd

        try:
            for i in range(len(cycle) - 1):
                from_currency = cycle[i]
                to_currency = cycle[i + 1]

                # Determine trading pair and side
                buy_pair = f"{to_currency}/{from_currency}"
                sell_pair = f"{from_currency}/{to_currency}"

                if buy_pair in self.symbols:
                    symbol = buy_pair
                    side = "buy"
                elif sell_pair in self.symbols:
                    symbol = sell_pair
                    side = "sell"
                else:
                    return (0.10, [])  # Conservative penalty if pair not found

                # Fetch order book
                try:
                    order_book = self.exchange.fetch_order_book(
                        symbol, limit=self.depth_levels
                    )
                    books.append(order_book)
                    leg_info.append({"symbol": symbol, "side": side})

                    # Convert to base currency amount for depth calculation
                    if side == "buy":
                        # Buying to_currency with from_currency
                        base_amount = (
                            current_amount / order_book["asks"][0][0]
                            if order_book["asks"]
                            else 0
                        )
                    else:
                        # Selling from_currency for to_currency
                        base_amount = current_amount

                    amounts.append(base_amount)

                    # Update amount for next leg (rough estimate)
                    if order_book.get("asks") or order_book.get("bids"):
                        best_price = (
                            order_book["asks"][0][0]
                            if side == "buy"
                            else order_book["bids"][0][0]
                        )
                        current_amount = (
                            current_amount * best_price
                            if side == "sell"
                            else current_amount / best_price
                        )

                except Exception as e:
                    logger.error(f"Failed to fetch order book for {symbol}: {e}")
                    return (0.10, [])

            # Calculate per-leg slippage
            per_leg_details = []
            total_slippage = 0.0

            for book, amount, info in zip(books, amounts, leg_info):
                if not book:
                    return (999.0, [])

                # Determine which side to use
                if info["side"] == "buy" and book.get("asks"):
                    side_data = book["asks"]
                    best_price = side_data[0][0]
                elif info["side"] == "sell" and book.get("bids"):
                    side_data = book["bids"]
                    best_price = side_data[0][0]
                else:
                    return (999.0, [])

                vwap = depth_fill_price(side_data, amount)
                if vwap is None:
                    return (999.0, [])  # Insufficient depth

                leg_slippage_pct = abs((vwap - best_price) / best_price) * 100
                total_slippage += leg_slippage_pct

                per_leg_details.append(
                    {
                        "symbol": info["symbol"],
                        "side": info["side"].upper(),
                        "slippage_pct": leg_slippage_pct,
                    }
                )

            # Apply slippage floor
            slippage_floor_pct = self.slippage_floor_bps / 100.0
            final_slippage = max(total_slippage, slippage_floor_pct)

            return (final_slippage, per_leg_details)

        except Exception as e:
            logger.error(f"❌ Failed to estimate slippage: {e}")
            return (0.10, [])  # Conservative penalty on error

    async def compute_depth_limited_size(
        self, cycle: List[str], max_size_usd: float
    ) -> float:
        """Compute maximum executable size based on order book depth"""
        try:
            min_size = max_size_usd

            for i in range(len(cycle) - 1):
                from_currency = cycle[i]
                to_currency = cycle[i + 1]

                # Determine trading pair and side
                buy_pair = f"{to_currency}/{from_currency}"
                sell_pair = f"{from_currency}/{to_currency}"

                if buy_pair in self.symbols:
                    symbol = buy_pair
                    side = "buy"
                elif sell_pair in self.symbols:
                    symbol = sell_pair
                    side = "sell"
                else:
                    return 0.0

                # Fetch order book
                order_book = self.exchange.fetch_order_book(
                    symbol, limit=self.depth_levels
                )
                book_side = order_book["asks"] if side == "buy" else order_book["bids"]

                if not book_side:
                    return 0.0

                best_price = book_side[0][0]

                # Calculate depth-limited size for this leg
                leg_max_size = depth_limited_size(
                    book_side,
                    best_price,
                    max_slippage_pct=self.depth_size_max_slippage_pct,
                )

                if leg_max_size == 0:
                    return 0.0

                # Convert to USD equivalent and track minimum
                leg_max_usd = (
                    leg_max_size * best_price if side == "sell" else leg_max_size
                )
                min_size = min(min_size, leg_max_usd)

            return min_size

        except Exception as e:
            logger.error(f"❌ Failed to compute depth-limited size: {e}")
            return 0.0

    async def find_arbitrage_opportunities(self) -> List[Dict]:
        """Find profitable arbitrage cycles"""
        try:
            # Fetch market data
            self.exchange.load_markets()
            self.symbols = list(self.exchange.markets.keys())
            self.tickers = self.exchange.fetch_tickers()

            # Exclude fiat currencies except USD (keep stablecoins, allow USD as bridge)
            fiat_currencies = {"EUR", "GBP", "JPY", "CAD", "AUD", "CHF"}

            # Build price graph with symbol filtering
            self.graph.clear()
            filtered_symbols = set()

            for symbol in self.symbols:
                if symbol not in self.tickers:
                    continue

                ticker = self.tickers[symbol]
                base, quote = symbol.split("/")

                # Skip pairs with fiat currencies
                if base in fiat_currencies or quote in fiat_currencies:
                    continue

                # Apply symbol allowlist if set
                if self.symbol_allowlist:
                    if (
                        base not in self.symbol_allowlist
                        or quote not in self.symbol_allowlist
                    ):
                        continue

                # Apply exclusions
                if base in self.exclude_symbols or quote in self.exclude_symbols:
                    continue

                # Apply regex-based exclusions
                if self.exclude_symbols_pattern:
                    if self.exclude_symbols_pattern.search(
                        base
                    ) or self.exclude_symbols_pattern.search(quote):
                        continue

                filtered_symbols.add(base)
                filtered_symbols.add(quote)

                # Add edges for both directions
                bid_price = ticker.get("bid")
                ask_price = ticker.get("ask")

                if bid_price and ask_price:
                    # Direct: base -> quote (selling base for quote)
                    self.graph.add_edge(
                        base, quote, rate=bid_price, symbol=symbol, side="sell"
                    )

                    # Reverse: quote -> base (buying base with quote)
                    self.graph.add_edge(
                        quote, base, rate=1 / ask_price, symbol=symbol, side="buy"
                    )

            # Find profitable cycles using efficient triangular arbitrage search
            opportunities = []
            all_cycles = []  # Track all cycles for debugging
            currencies = list(self.graph.nodes())

            # Filter to only triangle_bases if specified
            if self.triangle_bases:
                base_currencies = [c for c in currencies if c in self.triangle_bases]
            else:
                base_currencies = currencies

            # Check triangular arbitrage: A -> B -> C -> A
            for curr_a in base_currencies:
                # Find currencies we can trade to from A
                if curr_a not in self.graph:
                    continue

                for curr_b in self.graph.neighbors(curr_a):
                    # Find currencies we can trade to from B
                    if curr_b not in self.graph:
                        continue

                    for curr_c in self.graph.neighbors(curr_b):
                        # Check if we can complete the cycle back to A
                        if (
                            curr_c != curr_a
                            and curr_c != curr_b
                            and self.graph.has_edge(curr_c, curr_a)
                        ):
                            # Complete the cycle by returning to start
                            cycle = [curr_a, curr_b, curr_c, curr_a]

                            # Filter out stablecoin-only triangles if enabled
                            if self.exclude_stablecoin_only:
                                # Normalize and check if all three currencies are stablecoins
                                normalized_a = self._normalize_symbol(curr_a)
                                normalized_b = self._normalize_symbol(curr_b)
                                normalized_c = self._normalize_symbol(curr_c)
                                cycle_currencies = {
                                    normalized_a,
                                    normalized_b,
                                    normalized_c,
                                }
                                if cycle_currencies.issubset(self.stablecoins):
                                    # Skip this stablecoin-only cycle
                                    continue

                            # Calculate cycle profitability
                            gross_ratio = self._calculate_gross_cycle_profit(cycle)
                            if gross_ratio:
                                # Calculate net after fees and slippage
                                gross_profit_pct = (gross_ratio - 1) * 100

                                # Fees: Use expected fee model based on maker/taker mix
                                # expected_maker_legs determines how many legs we expect to fill as maker
                                maker_legs_fee = (
                                    self.expected_maker_legs * self.maker_fee
                                )
                                taker_legs_fee = (
                                    3 - self.expected_maker_legs
                                ) * self.taker_fee
                                fee_cost_pct = (maker_legs_fee + taker_legs_fee) * 100

                                # For initial filtering, use slippage based on mode
                                if self.slippage_mode == "dynamic":
                                    # Use dynamic slippage from order book depth
                                    # For now, we'll compute this for viable cycles only (below)
                                    # Use static estimate for initial scan
                                    slippage_pct_estimate = self.slippage_pct_estimate
                                else:
                                    # Use static slippage estimate
                                    slippage_pct_estimate = self.slippage_pct_estimate

                                # Net profit estimate
                                net_profit_pct_estimate = (
                                    gross_profit_pct
                                    - fee_cost_pct
                                    - slippage_pct_estimate
                                )

                                # Store cycle with slippage info
                                cycle_data = {
                                    "cycle": cycle,
                                    "gross_profit_pct": gross_profit_pct,
                                    "fee_cost_pct": fee_cost_pct,
                                    "slippage_pct": slippage_pct_estimate,
                                    "net_profit_pct": net_profit_pct_estimate,
                                    "profit_ratio": gross_ratio,
                                    "slippage_used_pct": slippage_pct_estimate,  # Track what we actually used
                                }
                                all_cycles.append(cycle_data)

                                # Only keep if net profit estimate exceeds threshold
                                # Guardrail: Never accept negative net regardless of config
                                effective_threshold = max(
                                    0.0, self.min_profit_threshold
                                )
                                if net_profit_pct_estimate > effective_threshold:
                                    opportunities.append(
                                        {
                                            "cycle": cycle,
                                            "gross_profit_pct": gross_profit_pct,
                                            "net_profit_pct": net_profit_pct_estimate,
                                            "fee_cost_pct": fee_cost_pct,
                                            "slippage_pct": slippage_pct_estimate,
                                            "profit_ratio": gross_ratio,
                                        }
                                    )

            # Sort all cycles
            all_cycles.sort(key=lambda x: x["net_profit_pct"], reverse=True)

            # Store for CSV logging and dedupe
            self._last_scan_best = all_cycles[0] if all_cycles else None
            self._all_cycles = all_cycles  # Store for caller to access

            # Sort by net profitability
            opportunities.sort(key=lambda x: x["net_profit_pct"], reverse=True)

            return opportunities[:5]  # Return top 5

        except Exception as e:
            logger.error(f"❌ Failed to find opportunities: {e}")
            return []

    def _calculate_gross_cycle_profit(self, cycle: List[str]) -> Optional[float]:
        """Calculate GROSS cycle profit (before fees and slippage)"""
        try:
            amount = 1.0

            # For cycle [A, B, C, A], we need 3 trades: A->B, B->C, C->A
            for i in range(len(cycle) - 1):
                from_curr = cycle[i]
                to_curr = cycle[i + 1]

                if self.graph.has_edge(from_curr, to_curr):
                    edge_data = self.graph[from_curr][to_curr]
                    rate = edge_data["rate"]
                    amount *= rate
                else:
                    return None

            return amount

        except Exception:
            return None

    def _log_scan_to_csv(self, scan_num: int, above_threshold: int):
        """Log scan data to CSV file"""
        if not self._last_scan_best:
            return

        try:
            import csv
            from datetime import datetime

            best = self._last_scan_best
            cycle_str = " -> ".join(best["cycle"])

            with open("logs/opps.csv", "a", newline="") as f:
                writer = csv.writer(f)
                # Write header if file is new
                if f.tell() == 0:
                    cols = [
                        "timestamp",
                        "scan",
                        "cycle",
                        "gross_pct",
                        "fee_pct",
                        "slip_pct",
                        "net_pct",
                        "above_threshold",
                    ]
                    if self.ema_gross is not None:
                        cols.extend(["ema15_gross", "ema15_net"])
                    writer.writerow(cols)

                row = [
                    datetime.now().isoformat(),
                    scan_num,
                    cycle_str,
                    f"{best['gross_profit_pct']:.4f}",
                    f"{best['fee_cost_pct']:.2f}",
                    f"{best['slippage_pct']:.2f}",
                    f"{best['net_profit_pct']:.4f}",
                    1 if above_threshold > 0 else 0,
                ]
                if self.ema_gross is not None:
                    row.extend([f"{self.ema_gross:.4f}", f"{self.ema_net:.4f}"])
                writer.writerow(row)
        except Exception as e:
            logger.error(f"CSV logging error: {e}")

    def _log_near_miss_to_csv(self, scan_num: int, best):
        """Log near-miss data to CSV file"""
        try:
            import csv
            from datetime import datetime

            cycle_str = " -> ".join(best["cycle"])
            shortfall_bps = (self.min_profit_threshold - best["net_profit_pct"]) * 100

            with open("logs/near_miss.csv", "a", newline="") as f:
                writer = csv.writer(f)
                # Write header if file is new
                if f.tell() == 0:
                    writer.writerow(
                        [
                            "timestamp",
                            "scan",
                            "cycle",
                            "gross_pct",
                            "fee_pct",
                            "slip_pct",
                            "net_pct",
                            "threshold",
                            "shortfall_bps",
                        ]
                    )

                writer.writerow(
                    [
                        datetime.now().isoformat(),
                        scan_num,
                        cycle_str,
                        f"{best['gross_profit_pct']:.4f}",
                        f"{best['fee_cost_pct']:.2f}",
                        f"{best['slippage_pct']:.2f}",
                        f"{best['net_profit_pct']:.4f}",
                        f"{self.min_profit_threshold:.2f}",
                        f"{shortfall_bps:.2f}",
                    ]
                )
        except Exception as e:
            logger.error(f"Near-miss CSV logging error: {e}")

    def _log_scan_summary_to_csv(
        self,
        scan_num: int,
        best_gross: float,
        best_net: float,
        gross_needed: float,
        count_above: int,
    ):
        """Log comprehensive scan summary to CSV file"""
        if not self.write_scan_csv:
            return

        try:
            import csv
            from datetime import datetime

            os.makedirs("logs", exist_ok=True)

            with open("logs/scan_summary.csv", "a", newline="") as f:
                writer = csv.writer(f)
                # Write header if file is new
                if f.tell() == 0:
                    writer.writerow(
                        [
                            "timestamp",
                            "scan",
                            "best_gross_pct",
                            "best_net_pct",
                            "gross_needed_pct",
                            "gap_pct",
                            "slippage_mode",
                            "slippage_used_pct",
                            "fee_per_leg_pct",
                            "threshold_pct",
                            "count_above_threshold",
                        ]
                    )

                # Calculate gap
                gap = gross_needed - best_gross if gross_needed > 0 else 0

                # Get actual slippage used (from best cycle if available)
                slippage_used = (
                    self._last_scan_best.get(
                        "slippage_used_pct", self.slippage_pct_estimate
                    )
                    if self._last_scan_best
                    else self.slippage_pct_estimate
                )

                writer.writerow(
                    [
                        datetime.now().isoformat(),
                        scan_num,
                        f"{best_gross:.4f}",
                        f"{best_net:.4f}",
                        f"{gross_needed:.4f}",
                        f"{gap:.4f}",
                        self.slippage_mode,
                        f"{slippage_used:.4f}",
                        f"{self.taker_fee * 100:.4f}",
                        f"{self.min_profit_threshold:.4f}",
                        count_above,
                    ]
                )
        except Exception as e:
            logger.error(f"Scan summary CSV logging error: {e}")

    async def get_cash(self):
        """Get total cash (USD + USDT) balance for equity tracker"""
        bals = self.paper_balances if self.trading_mode == "paper" else self.balances
        cash = 0.0
        for asset in ["USD", "USDT"]:
            if asset in bals:
                balance = bals[asset]
                if isinstance(balance, dict):
                    cash += balance.get("total", 0)
                else:
                    cash += balance
        return cash

    async def get_asset_value(self):
        """Get total non-cash asset value for equity tracker"""
        bals = self.paper_balances if self.trading_mode == "paper" else self.balances
        asset_value = 0.0

        for asset, balance in bals.items():
            if asset in ["USD", "USDT"]:
                continue  # Skip cash

            if isinstance(balance, dict):
                qty = balance.get("total", 0)
            else:
                qty = balance

            if qty <= 0:
                continue

            # Get price for asset
            ticker_symbol = f"{asset}/USDT"
            if ticker_symbol in self.tickers:
                px = float(self.tickers[ticker_symbol].get("last", 0))
            else:
                ticker_symbol = f"{asset}/USD"
                if ticker_symbol in self.tickers:
                    px = float(self.tickers[ticker_symbol].get("last", 0))
                else:
                    px = 0.0

            asset_value += float(qty) * float(px)

        return asset_value

    def _log_start_equity_breakdown(self):
        """Log detailed breakdown of starting equity"""
        total = 0.0
        logger.debug("Start equity breakdown:")
        bals = self.paper_balances if self.trading_mode == "paper" else self.balances

        for asset, balance in bals.items():
            if isinstance(balance, dict):
                qty = balance.get("total", 0)
            else:
                qty = balance

            if qty <= 0:
                continue

            # Treat USD and USDT as 1.0
            if asset in ("USD", "USDT"):
                px = 1.0
            else:
                # Get price for other assets
                ticker_symbol = f"{asset}/USDT"
                if ticker_symbol in self.tickers:
                    px = float(self.tickers[ticker_symbol].get("last", 0))
                else:
                    ticker_symbol = f"{asset}/USD"
                    if ticker_symbol in self.tickers:
                        px = float(self.tickers[ticker_symbol].get("last", 0))
                    else:
                        px = 0.0

            val = float(qty) * float(px)
            total += val
            logger.debug(f"  {asset}: qty={qty:.8f} px={px:.8f} val=${val:.2f}")

        logger.debug(f"Start equity sum: ${total:.2f}")

    def _equity_usd(self):
        """Calculate total equity in USD (mark-to-market)"""
        total = 0.0
        priced = 0
        unpriced = 0
        bals = self.paper_balances if self.trading_mode == "paper" else self.balances

        # Ensure tickers are available
        if not getattr(self, "tickers", None):
            try:
                self.tickers = self.exchange.fetch_tickers()
            except Exception:
                self.tickers = {}

        def price(symbol):
            """Get USD price for a symbol"""
            p = None
            s1 = f"{symbol}/USD"
            s2 = f"{symbol}/USDT"
            t1 = self.tickers.get(s1)
            t2 = self.tickers.get(s2)
            if t1 and t1.get("bid"):
                p = t1["bid"]
            elif t2 and t2.get("bid"):
                p = t2["bid"]  # assume USDT=$1
            return p

        for asset, v in (bals or {}).items():
            amt = v.get("total") if isinstance(v, dict) else (v or 0.0)
            if not amt:
                continue
            if asset in ("USD", "USDT", "USDC"):
                total += float(amt) * 1.0
                priced += 1
            else:
                p = price(asset)
                if p:
                    total += float(amt) * float(p)
                    priced += 1
                else:
                    unpriced += 1

        return total, priced, unpriced

    def print_summary(self):
        """Print compact session summary"""
        print("\n" + "=" * 60)
        print("SESSION SUMMARY")
        print("=" * 60)

        # Execution stats
        print(f"Attempts:         {self.execution_stats['attempts']}")
        print(f"Full fills:       {self.execution_stats['full_fills']}")
        print(f"Partial fills:    {self.execution_stats['partial_fills']}")
        print(f"Cancels:          {self.execution_stats['cancels']}")
        print(f"Depth rejects:    {self.execution_stats['depth_rejects']}")
        print(f"Slippage rejects: {self.execution_stats['slippage_rejects']}")
        print(f"Timeouts:         {self.execution_stats['timeouts']}")
        print(f"Maker used:       {self.execution_stats['maker_used_count']}")
        print(f"Maker fallbacks:  {self.execution_stats['maker_to_taker_fallbacks']}")

        # Trade metrics
        if self.trade_history:
            net_edges = [t["net_pct"] for t in self.trade_history]
            avg_net = sum(net_edges) / len(net_edges)

            all_latencies = []
            for t in self.trade_history:
                all_latencies.extend(t["latencies_ms"])

            if all_latencies:
                import statistics

                median_lat = statistics.median(all_latencies)

                print(f"\nFilled trades:    {len(self.trade_history)}")
                print(f"Avg net edge:     {avg_net:+.3f}%")
                print(f"Median leg lat:   {median_lat:.0f}ms")

                # Maker usage rate
                maker_legs = sum(
                    t["fee_mix"].count("maker") for t in self.trade_history
                )
                total_legs = len(self.trade_history) * 3
                if total_legs > 0:
                    maker_rate = (maker_legs / total_legs) * 100
                    print(f"Maker usage:      {maker_rate:.1f}%")

        # USD P&L section
        print("\nDOLLARS")
        print(f"  Realized P&L:   ${self.realized_pnl_usd:+.2f}")
        avg_hyp = (
            (self.hyp_best_pnl_usd_sum / self.hyp_best_count)
            if self.hyp_best_count
            else 0.0
        )
        print(
            f"  Hypothetical (best/scan): total ${self.hyp_best_pnl_usd_sum:+.2f} | avg/scan ${avg_hyp:+.2f}"
        )
        if self.evs:
            ev_scan = sum(self.evs) / len(self.evs)
            if self.ev_day_factor:
                scans_per_day = 86400 / max(1, self.poll_sec)
                print(
                    f"  EV: per-scan ${ev_scan:+.2f} | "
                    f"per-day ${ev_scan * scans_per_day:+.0f} "
                    f"(at POLL_SEC={self.poll_sec})"
                )
            else:
                print(f"  EV: per-scan ${ev_scan:+.2f}")

        # Reason buckets
        if self.reason_buckets:
            total_rejects = (
                self.reject_by_threshold
                + self.reject_by_fees
                + self.reject_by_slip
                + self.reject_by_depth
            )
            if total_rejects > 0:
                print(
                    f"\nREASONS (scans): threshold={self.reject_by_threshold}, "
                    f"fees={self.reject_by_fees}, slip={self.reject_by_slip}, "
                    f"depth={self.reject_by_depth}"
                )

                # Find primary blocker
                reasons = {
                    "threshold": self.reject_by_threshold,
                    "fees": self.reject_by_fees,
                    "slip": self.reject_by_slip,
                    "depth": self.reject_by_depth,
                }
                primary_blocker = max(reasons, key=reasons.get)
                print(f"primary blocker: {primary_blocker}")

                # If no fills, add message
                if self.execution_stats["full_fills"] == 0:
                    print(f"No fills this session. Primary blocker: {primary_blocker}.")

        # Money summary
        print("\nMONEY SUMMARY")
        end_eq = (
            self.last_equity_usd
            if self.last_equity_usd is not None
            else self.start_equity_usd
        )
        delta = (
            (end_eq - self.start_equity_usd)
            if (self.start_equity_usd is not None and end_eq is not None)
            else 0.0
        )
        deltap = (
            (delta / self.start_equity_usd * 100.0) if self.start_equity_usd else 0.0
        )
        print(f"  Start equity:   ${self.start_equity_usd:,.{self.equity_precision}f}")
        print(f"  End equity:     ${end_eq:,.{self.equity_precision}f}")
        print(
            f"  Change:         ${delta:+,.{self.equity_precision}f} ({deltap:+.2f}%)"
        )
        print(f"  Realized P&L:   ${self.realized_pnl_usd:+,.{self.equity_precision}f}")

        # Max drawdown
        if len(self.equity_curve) >= 2:
            peak = self.equity_curve[0][1]
            mdd = 0.0
            for _, eq in self.equity_curve:
                if eq > peak:
                    peak = eq
                dd = (eq - peak) / peak if peak else 0.0
                if dd < mdd:
                    mdd = dd
            print(f"  Max drawdown:   {mdd*100:.2f}%")

        print("=" * 60)

    async def run_trading_session(self, max_trades: int = None):
        """Run continuous automated arbitrage trading session"""
        fee_source_label = f"(source: {self.fee_source_actual})"
        fee_mix_desc = (
            "(mix: m/t/m planned)" if self.maker_fee != self.taker_fee else ""
        )
        print(
            f"🏦 {self.exchange_name.upper()} | "
            f"Fees: {self.maker_fee*100:.2f}%m/{self.taker_fee*100:.2f}%t "
            f"{fee_source_label} {fee_mix_desc}| Mode: {self.trading_mode}"
        )
        if self.run_min > 0:
            print(f"⏱️  Timeboxed: {self.run_min} min")
        print("💡 Press Ctrl+C to stop\n")

        await self.fetch_balances()

        # Log detailed start equity breakdown
        self._log_start_equity_breakdown()

        # Calculate and display starting equity
        self.start_equity_usd, priced, unpriced = self._equity_usd()
        self.last_equity_usd = self.start_equity_usd
        self.equity_curve.append((time.time(), self.start_equity_usd))
        print(
            f"🏁 Start equity: ${self.start_equity_usd:,.{self.equity_precision}f} "
            f"(priced {priced}, unpriced {unpriced})\n"
        )

        # Load markets to get universe stats
        self.exchange.load_markets()

        # Apply filtering to count filtered universe
        filtered_count = 0
        fiat_currencies = {"EUR", "GBP", "JPY", "CAD", "AUD", "CHF"}
        for symbol in self.exchange.markets.keys():
            if "/" not in symbol:
                continue
            base, quote = symbol.split("/")
            if base in fiat_currencies or quote in fiat_currencies:
                continue
            if self.symbol_allowlist:
                if (
                    base not in self.symbol_allowlist
                    or quote not in self.symbol_allowlist
                ):
                    continue
            if base in self.exclude_symbols or quote in self.exclude_symbols:
                continue
            if self.exclude_symbols_pattern:
                if self.exclude_symbols_pattern.search(
                    base
                ) or self.exclude_symbols_pattern.search(quote):
                    continue
            filtered_count += 1

        # Count potential triangles (filtered symbols)
        filtered_symbols_set = set()
        for symbol in self.exchange.markets.keys():
            if "/" not in symbol:
                continue
            base, quote = symbol.split("/")
            if base in fiat_currencies or quote in fiat_currencies:
                continue
            if self.symbol_allowlist:
                if (
                    base not in self.symbol_allowlist
                    or quote not in self.symbol_allowlist
                ):
                    continue
            if base in self.exclude_symbols or quote in self.exclude_symbols:
                continue
            if self.exclude_symbols_pattern:
                if self.exclude_symbols_pattern.search(
                    base
                ) or self.exclude_symbols_pattern.search(quote):
                    continue
            filtered_symbols_set.add(base)
            filtered_symbols_set.add(quote)

        # Rough triangle count: N choose 3 for filtered symbols
        n_symbols = len(filtered_symbols_set)
        approx_triangles = (
            (n_symbols * (n_symbols - 1) * (n_symbols - 2)) // 6
            if n_symbols >= 3
            else 0
        )

        bases_str = ",".join(self.triangle_bases) if self.triangle_bases else "any"
        print(
            f"🌐 Universe: {n_symbols} symbols, ~{approx_triangles} triangles (bases: {bases_str})\n"
        )

        trade_num = 0
        start_time = time.time()
        try:
            while True:
                # Check timebox
                elapsed_min = (time.time() - start_time) / 60
                if self.run_min > 0 and elapsed_min >= self.run_min:
                    print(f"\n⏱️  Timebox reached ({elapsed_min:.1f} min)")
                    break

                trade_num += 1

                # Show timebox ETA if applicable
                if self.run_min > 0:
                    print(
                        f"🔍 Scan {trade_num} | ⏱ timeboxed {self.run_min}m | "
                        f"elapsed {elapsed_min:.1f}m | scans {trade_num}",
                        end=" ",
                        flush=True,
                    )
                else:
                    print(f"🔍 Scan {trade_num}", end=" ", flush=True)

                opportunities = await self.find_arbitrage_opportunities()

                # Update EMA with best opportunity
                if self._last_scan_best:
                    best = self._last_scan_best
                    if self.ema_gross is None:
                        # Initialize EMA
                        self.ema_gross = best["gross_profit_pct"]
                        self.ema_net = best["net_profit_pct"]
                    else:
                        # Update EMA: EMA = alpha * new + (1 - alpha) * old
                        self.ema_gross = (
                            self.ema_alpha * best["gross_profit_pct"]
                            + (1 - self.ema_alpha) * self.ema_gross
                        )
                        self.ema_net = (
                            self.ema_alpha * best["net_profit_pct"]
                            + (1 - self.ema_alpha) * self.ema_net
                        )

                # Log to CSV if in debug mode
                if self.verbosity == "debug" and self._last_scan_best:
                    self._log_scan_to_csv(trade_num, len(opportunities))

                # Log scan summary CSV if enabled
                if self.write_scan_csv and self._last_scan_best:
                    # Use expected fee model
                    maker_legs_fee = self.expected_maker_legs * self.maker_fee
                    taker_legs_fee = (3 - self.expected_maker_legs) * self.taker_fee
                    fee_cost_pct_calc = (maker_legs_fee + taker_legs_fee) * 100
                    gross_needed_calc = (
                        self.min_profit_threshold
                        + fee_cost_pct_calc
                        + self.slippage_pct_estimate
                    )
                    self._log_scan_summary_to_csv(
                        trade_num,
                        self._last_scan_best["gross_profit_pct"],
                        self._last_scan_best["net_profit_pct"],
                        gross_needed_calc,
                        len(opportunities),
                    )

                # Dedupe logic: compute key and net for change detection
                all_cycles = getattr(self, "_all_cycles", [])
                best = all_cycles[0] if all_cycles else None
                key = None if not best else " / ".join(best["cycle"][:3])
                net = None if not best else best["net_profit_pct"]

                # Determine if we should print detailed output
                def should_print():
                    if not self.dedupe or best is None:
                        return True
                    if self._last_key is None:
                        return True
                    # print if cycle changed
                    if key != self._last_key:
                        return True
                    # print if net moved by >= CHANGE_BPS (in %)
                    if abs(net - self._last_net) >= (self.change_bps / 100):
                        return True
                    # heartbeat
                    if (trade_num % self.print_every_n) == 0:
                        return True
                    return False

                # Calculate execution size for USD P&L (do this before should_print so it's available for all scans)
                size_usd = self.max_position_size  # Default hypothetical
                size_label = "(hyp)"
                if best is not None:
                    # Try to get actual executable size
                    start_currency = best["cycle"][0]
                    check_balances = (
                        self.paper_balances
                        if self.trading_mode == "paper"
                        else self.balances
                    )
                    available = (
                        check_balances.get(start_currency, {}).get("free", 0)
                        if check_balances
                        else 0
                    )
                    if available > 0:
                        size_usd = min(self.max_position_size, available)
                        size_label = ""

                # Print output based on dedupe decision
                if should_print():
                    # Calculate breakeven gross ONCE at the top (used by banner and why line)
                    try:
                        # Use expected fee model
                        maker_legs_fee = self.expected_maker_legs * self.maker_fee
                        taker_legs_fee = (3 - self.expected_maker_legs) * self.taker_fee
                        fee_cost_pct_calc = (maker_legs_fee + taker_legs_fee) * 100
                        breakeven_gross = (
                            self.min_profit_threshold
                            + fee_cost_pct_calc
                            + self.slippage_pct_estimate
                        )
                        # Sanity check: breakeven should be positive and reasonable (<100%)
                        if 0 < breakeven_gross < 100:
                            breakeven_str = f" (need gross≥{breakeven_gross:.2f}%)"
                        else:
                            breakeven_str = ""
                            breakeven_gross = 0  # Fallback
                    except Exception:
                        breakeven_str = ""
                        breakeven_gross = 0  # Fallback

                    # Calculate USD P&L and EV
                    best_pnl_usd = 0.0
                    if best is not None:
                        best_net = best["net_profit_pct"]
                        best_pnl_usd = size_usd * (best_net / 100.0)
                        self.hyp_best_pnl_usd_sum += best_pnl_usd
                        self.hyp_best_count += 1

                        # EV calculation
                        if self.ev_only_above_thr:
                            ev_usd = (
                                best_pnl_usd
                                if best_net >= self.min_profit_threshold
                                else 0.0
                            )
                        else:
                            ev_usd = best_pnl_usd
                        self.evs.append(ev_usd)
                        if len(self.evs) > self.ev_window:
                            self.evs.pop(0)

                    # Print "(unchanged × N)" if we skipped scans
                    if self._repeat > 0:
                        print(f"  (unchanged × {self._repeat})")
                        self._repeat = 0

                    # Print detailed scan output
                    if all_cycles and self.verbosity != "quiet":
                        print()
                        topn = min(self.topn, len(all_cycles))
                        for i, opp in enumerate(all_cycles[:topn], 1):
                            cycle_str = " -> ".join(opp["cycle"][:3])
                            # Clamp values for display
                            gross_display = self._clamp_for_display(
                                opp["gross_profit_pct"]
                            )
                            net_display = self._clamp_for_display(opp["net_profit_pct"])
                            print(
                                f"  {i}. {cycle_str}: "
                                f"gross={gross_display:+.2f}% "
                                f"fees={opp['fee_cost_pct']:.2f}% "
                                f"net={net_display:+.2f}%"
                            )

                        # Show why line if 0 opportunities above threshold
                        if len(opportunities) == 0 and all_cycles:
                            try:
                                best_opp = all_cycles[0]
                                shortfall = (
                                    self.min_profit_threshold
                                    - best_opp["net_profit_pct"]
                                )
                                # Calculate gap to breakeven gross with safety check
                                if breakeven_gross > 0:
                                    gross_gap = (
                                        breakeven_gross - best_opp["gross_profit_pct"]
                                    )
                                    gap_str = f"(need {gross_gap:+.2f}% more) – "
                                else:
                                    gap_str = ""

                                # Clamp for display
                                net_display = self._clamp_for_display(
                                    best_opp["net_profit_pct"]
                                )
                                gross_display = self._clamp_for_display(
                                    best_opp["gross_profit_pct"]
                                )

                                print(
                                    f"  ✗ why: best_net={net_display:+.2f}% "
                                    f"(< thr by {shortfall:.2f}%), "
                                    f"gross={gross_display:+.2f}% "
                                    f"{gap_str}"
                                    f"fees={best_opp['fee_cost_pct']:.2f}% – "
                                    f"slip={best_opp['slippage_pct']:.2f}%"
                                )
                            except Exception as e:
                                logger.debug(f"Error formatting why line: {e}")
                                print("  ✗ why: calculation error")

                            # Track reason buckets
                            if self.reason_buckets:
                                if (
                                    best_opp["fee_cost_pct"]
                                    >= best_opp["gross_profit_pct"]
                                ):
                                    self.reject_by_fees += 1
                                elif best_opp["slippage_pct"] >= (
                                    best_opp["gross_profit_pct"]
                                    - best_opp["fee_cost_pct"]
                                ):
                                    self.reject_by_slip += 1
                                elif (
                                    best_opp["net_profit_pct"] + 1e-9
                                ) < self.min_profit_threshold:
                                    self.reject_by_threshold += 1

                            # Check for near-miss
                            if 0 < shortfall <= self.near_miss_bps:
                                gap = shortfall
                                print(
                                    f"  ⚑ near-miss: best_net={best_opp['net_profit_pct']:+.2f}% "
                                    f"(short {gap:.2f}%), "
                                    f"gross={best_opp['gross_profit_pct']:+.2f}% – "
                                    f"fees={best_opp['fee_cost_pct']:.2f}% – "
                                    f"slip={best_opp['slippage_pct']:.2f}%"
                                )
                                # Log to CSV
                                os.makedirs("logs", exist_ok=True)
                                self._log_near_miss_to_csv(trade_num, best_opp)

                        # Show threshold with breakeven (already calculated above)
                        print(
                            f"  → {len(opportunities)} above {self.min_profit_threshold}% threshold{breakeven_str}",
                            end="",
                        )

                        # Show EMA stats and scan metrics if available
                        if self.ema_gross is not None and self.verbosity in [
                            "normal",
                            "debug",
                        ]:
                            # Calculate filtered triangle count
                            total_cycles = len(all_cycles)
                            print(
                                f" | EMA15 g={self.ema_gross:.2f}% n={self.ema_net:.2f}% | "
                                f"cycles={total_cycles}",
                                end="",
                            )

                        # Show deltas if enabled and comparable
                        if self.show_delta and best is not None:
                            delta_net = None
                            delta_gross = None
                            if (
                                self._last_print_key is not None
                                and key == self._last_print_key
                            ):
                                if self._last_print_net is not None:
                                    delta_net = net - self._last_print_net
                                if self._last_print_gross is not None:
                                    delta_gross = (
                                        best["gross_profit_pct"]
                                        - self._last_print_gross
                                    )

                            delta_parts = []
                            if delta_net is not None:
                                delta_parts.append(f"Δnet={delta_net:+.02f}%")
                            if delta_gross is not None:
                                delta_parts.append(f"Δgross={delta_gross:+.02f}%")

                            if delta_parts:
                                print(f" | {' '.join(delta_parts)}", end="")

                        # Show USD P&L and EV
                        if self.show_usd and best is not None:
                            print(
                                f" | size≈${size_usd:.0f}{size_label} hyp_P&L=${best_pnl_usd:+.2f}",
                                end="",
                            )

                            # Show EV if available
                            if self.evs:
                                ev_scan = sum(self.evs) / len(self.evs)
                                if self.ev_day_factor:
                                    # Initialize EV timer on first use
                                    if not hasattr(self, "_ev_timer_t0"):
                                        self._ev_timer_t0 = time.time()
                                        self._ev_scan_count = 0

                                    self._ev_scan_count += 1
                                    elapsed = max(time.time() - self._ev_timer_t0, 1e-6)
                                    scans_per_min = self._ev_scan_count / (
                                        elapsed / 60.0
                                    )
                                    ev_per_min = ev_scan * scans_per_min
                                    ev_day = ev_per_min * 60.0 * 24.0

                                    # Only print EV per day after at least 10 scans for stability
                                    if self._ev_scan_count >= 10:
                                        print(
                                            f" | EV/scan=${ev_scan:+.2f} EV/day=${ev_day:+.0f}",
                                            end="",
                                        )
                                    else:
                                        print(f" | EV/scan=${ev_scan:+.2f}", end="")
                                else:
                                    print(f" | EV/scan=${ev_scan:+.2f}", end="")

                        print()  # newline

                        # Debug mode: show top 10 table
                        if self.verbosity == "debug":
                            print("  DEBUG: Top 10 cycles:")
                            for i, opp in enumerate(all_cycles[:10], 1):
                                cycle_str = " -> ".join(opp["cycle"])
                                print(
                                    f"    {i:2d}. {cycle_str:40s} "
                                    f"g={opp['gross_profit_pct']:+.3f}% "
                                    f"f={opp['fee_cost_pct']:.2f}% "
                                    f"s={opp['slippage_pct']:.2f}% "
                                    f"n={opp['net_profit_pct']:+.3f}%"
                                )

                    # Update state
                    self._last_key = key
                    self._last_net = net

                    # Update last printed values for delta calculation
                    if best is not None:
                        self._last_print_key = key
                        self._last_print_net = net
                        self._last_print_gross = best["gross_profit_pct"]

                else:
                    # Skipping detailed output - increment repeat counter
                    self._repeat += 1
                    # Always print a minimal status line so user knows bot is alive
                    if net is not None:
                        print(f"| best_net={net:+.2f}% (unchanged)")
                    else:
                        print("| (scanning...)")

                # Print equity summary periodically (every N scans OR when opportunities execute)
                should_print_equity = (trade_num % self.equity_print_every) == 0 or len(
                    opportunities
                ) > 0

                # Check if we should continue or execute
                if not opportunities:
                    # Periodic equity heartbeat
                    if should_print_equity:
                        cur, priced, unpriced = self._equity_usd()
                        self.last_equity_usd = cur
                        self.equity_curve.append((time.time(), cur))
                        delta = cur - self.start_equity_usd
                        deltap = (
                            (delta / self.start_equity_usd * 100.0)
                            if self.start_equity_usd
                            else 0.0
                        )
                        kill_switch_msg = (
                            " [🛑 KILL SWITCH ACTIVE]" if self.kill_switch_active else ""
                        )
                        print(
                            f"💼 Equity: ${cur:,.{self.equity_precision}f} "
                            f"(Δ ${delta:+,.{self.equity_precision}f}, {deltap:+.2f}%){kill_switch_msg}"
                        )

                        # CSV logging if debug
                        if self.verbosity == "debug":
                            os.makedirs("logs", exist_ok=True)
                            try:
                                import csv
                                from datetime import datetime

                                with open("logs/equity.csv", "a", newline="") as f:
                                    writer = csv.writer(f)
                                    if f.tell() == 0:
                                        writer.writerow(
                                            [
                                                "timestamp",
                                                "scan",
                                                "equity_usd",
                                                "delta_usd",
                                                "delta_pct",
                                            ]
                                        )
                                    writer.writerow(
                                        [
                                            datetime.now().isoformat(),
                                            trade_num,
                                            f"{cur:.{self.equity_precision}f}",
                                            f"{delta:+.{self.equity_precision}f}",
                                            f"{deltap:+.2f}",
                                        ]
                                    )
                            except Exception as e:
                                logger.error(f"Equity CSV logging error: {e}")

                    await asyncio.sleep(self.poll_sec)
                    continue

                # If we have opportunities, print now (dedupe already handled above)
                if self.verbosity == "quiet" and should_print():
                    print(f"| {len(opportunities)} above threshold")

                # Filter opportunities to only those starting with currencies we own
                owned_currencies = set()
                # Use paper balances in paper mode, real balances in live mode
                check_balances = (
                    self.paper_balances
                    if self.trading_mode == "paper"
                    else self.balances
                )

                if check_balances:
                    for currency, balance in check_balances.items():
                        if isinstance(balance, dict):
                            # Use total if free is None (some exchanges return None for free)
                            free_balance = balance.get("free")
                            if free_balance is None:
                                free_balance = balance.get("total", 0)
                            if (
                                free_balance and float(free_balance) > 1.0
                            ):  # At least $1
                                # Strip .F suffix that Kraken adds to some currencies
                                normalized_currency = currency.replace(".F", "")
                                owned_currencies.add(normalized_currency)

                if owned_currencies:
                    if self.verbosity == "debug":
                        logger.info(f"💼 You own: {', '.join(sorted(owned_currencies))}")
                    # Filter to opportunities starting with owned currencies
                    viable_opportunities = [
                        opp
                        for opp in opportunities
                        if opp["cycle"][0] in owned_currencies
                    ]
                    if not viable_opportunities:
                        logger.info(
                            "😔 No opportunities starting with your owned currencies"
                        )
                        logger.info("🔄 Continuing to search...")
                        await asyncio.sleep(self.poll_sec)
                        continue
                    opportunities = viable_opportunities

                # Execute ALL profitable opportunities in this scan, not just the best one
                if self.verbosity == "debug":
                    logger.info(
                        f"🎯 Found {len(opportunities)} opportunities to execute"
                    )
                executed_count = 0

                for opp_idx, opportunity in enumerate(opportunities):
                    # Check kill-switch before processing any opportunity
                    if self.kill_switch_enabled and not self.kill_switch_active:
                        cur_equity, _, _ = self._equity_usd()
                        if self.start_equity_usd and cur_equity:
                            drawdown_pct = (
                                (cur_equity - self.start_equity_usd)
                                / self.start_equity_usd
                            ) * 100
                            if drawdown_pct < -self.max_daily_drawdown_pct:
                                self.kill_switch_active = True
                                logger.warning(
                                    f"🛑 KILL SWITCH: daily drawdown {drawdown_pct:.1f}% exceeds "
                                    f"-{self.max_daily_drawdown_pct:.1f}% — halting executions (scan continues)"
                                )

                    # Skip execution if kill-switch is active
                    if self.kill_switch_active:
                        if opp_idx == 0:  # Only log once per scan
                            logger.info("🛑 Kill-switch active, skipping all executions")
                        continue

                    cycle = opportunity["cycle"]
                    net_profit = opportunity["net_profit_pct"]
                    gross_profit = opportunity["gross_profit_pct"]
                    fee_cost_pct = opportunity["fee_cost_pct"]

                    if self.verbosity == "debug":
                        logger.info(
                            f"\n📊 Opportunity {opp_idx + 1}/{len(opportunities)}: {' -> '.join(cycle)}"
                        )
                        logger.info(
                            f"📈 Expected profit: gross={gross_profit:.3f}% net={net_profit:.3f}%"
                        )

                    # Check if we have enough balance for this opportunity
                    start_currency = cycle[0]
                    check_balances = (
                        self.paper_balances
                        if self.trading_mode == "paper"
                        else self.balances
                    )
                    available_balance = check_balances.get(start_currency, {}).get(
                        "free", 0
                    )

                    # Balance-cap if needed
                    execution_size = self.max_position_size
                    if available_balance < self.max_position_size:
                        execution_size = available_balance
                        print(
                            f"  ⚠️  balance-cap: need ${self.max_position_size:.2f}, "
                            f"have ${available_balance:.2f}, sizing to ${execution_size:.2f}"
                        )
                        if execution_size < 10:  # Skip if too small
                            logger.warning(
                                f"⚠️ Balance too small ({execution_size:.2f}), skipping"
                            )
                            continue

                    # Check order book depth for each trade in the cycle (enforced in both paper and live)
                    logger.debug("📖 Checking order book depth...")
                    depth_check_passed = True
                    amount = self.max_position_size

                    for i in range(len(cycle) - 1):
                        from_currency = cycle[i]
                        to_currency = cycle[i + 1]

                        # Determine trading pair and side
                        buy_pair = f"{to_currency}/{from_currency}"
                        sell_pair = f"{from_currency}/{to_currency}"

                        if buy_pair in self.symbols:
                            symbol = buy_pair
                            side = "buy"
                        elif sell_pair in self.symbols:
                            symbol = sell_pair
                            side = "sell"
                        else:
                            depth_check_passed = False
                            break

                        depth = await self.check_order_book_depth(symbol, side, amount)

                        if not depth.get("sufficient"):
                            logger.warning(
                                f"  ⚠️ Step {i+1} ({from_currency}->{to_currency}): "
                                f"Insufficient liquidity in {symbol} "
                                f"(need {depth.get('needed')}, available {depth.get('available', 0):.2f})"
                            )
                            depth_check_passed = False
                            break
                        else:
                            avg_price = depth.get("avg_price")
                            ticker_price = self.tickers[symbol].get(
                                "ask" if side == "buy" else "bid"
                            )
                            slippage = (
                                abs(avg_price - ticker_price) / ticker_price * 100
                            )
                            logger.debug(
                                f"  ✅ Step {i+1} "
                                f"({from_currency}->{to_currency}): "
                                f"{symbol} has sufficient liquidity "
                                f"(avg price: {avg_price:.6f}, "
                                f"slippage: {slippage:.3f}%)"
                            )

                        # Update amount for next step - convert units correctly
                        if side == "sell":
                            # Selling BASE → receive QUOTE
                            amount = amount * depth.get("avg_price", 1.0)
                        else:
                            # Buying BASE with QUOTE
                            amount = amount / depth.get("avg_price", 1.0)
                        amount *= 0.999  # Small buffer for fees/precision

                    if not depth_check_passed:
                        logger.debug(
                            "❌ Skipping opportunity due to insufficient liquidity"
                        )
                        continue

                    # Track attempt
                    self.execution_stats["attempts"] += 1

                    # CRITICAL: Check per-leg slippage caps FIRST before any size gating
                    # Use max position size for slippage estimation to check worst case
                    logger.debug("📖 Checking per-leg slippage caps...")
                    (
                        estimated_slippage,
                        per_leg_details,
                    ) = await self.estimate_cycle_slippage(
                        cycle, self.max_position_size
                    )

                    # Check per-leg slippage caps (use per-symbol caps if available)
                    leg_cap_exceeded = False
                    chronic_offender = False
                    for i, leg in enumerate(per_leg_details, 1):
                        symbol = leg["symbol"]
                        # Use per-symbol cap if available, otherwise use global default
                        max_slippage_leg_pct = self.per_symbol_slippage_caps.get(
                            symbol, self.max_slippage_leg_bps / 100.0
                        )

                        # Record slippage observation for chronic offender detection
                        self.slippage_monitor.record(symbol, leg["slippage_pct"])

                        # Check if this symbol is a chronic offender
                        if self.slippage_monitor.is_chronic(
                            symbol, max_slippage_leg_pct
                        ):
                            stats = self.slippage_monitor.get_stats(symbol)
                            logger.warning(
                                f"   ⚠️ REJECT: Chronic slippage offender on LEG{i} "
                                f"(pair={symbol}, median={stats['median']:.2f}%, "
                                f"cap={max_slippage_leg_pct:.2f}%, samples={stats['count']})"
                            )
                            self.execution_stats["slippage_rejects"] += 1
                            chronic_offender = True
                            break

                        # Check immediate slippage cap
                        if leg["slippage_pct"] > max_slippage_leg_pct:
                            logger.warning(
                                f"   ⚠️ REJECT: Leg slippage {leg['slippage_pct']:.2f}% "
                                f"> cap {max_slippage_leg_pct:.2f}% on LEG{i} "
                                f"(pair={leg['symbol']}, side={leg['side']})"
                            )
                            self.execution_stats["slippage_rejects"] += 1
                            leg_cap_exceeded = True
                            break

                    if leg_cap_exceeded or chronic_offender:
                        continue

                    # Log per-leg slippage on success
                    if per_leg_details:
                        leg_slip_str = " ".join(
                            f"LEG{i}={leg['slippage_pct']:.3f}%"
                            for i, leg in enumerate(per_leg_details, 1)
                        )
                        logger.debug(
                            f"   ✅ Slip[{leg_slip_str}] (cap={max_slippage_leg_pct:.2f}%)"
                        )

                    # Determine size after balance cap (the actual intended order size)
                    size_after_balance_cap = min(
                        self.max_position_size, available_balance
                    )

                    # Check depth-limited size
                    logger.debug("📏 Computing depth-limited size...")
                    depth_limited_size_usd = await self.compute_depth_limited_size(
                        cycle, self.max_position_size
                    )

                    # Smart depth gating: max(absolute min, relative min)
                    relative_min = size_after_balance_cap * self.depth_rel_min_frac
                    min_required = max(self.depth_abs_min_usd, relative_min)

                    # Also check per-leg minimums
                    if depth_limited_size_usd < min_required:
                        logger.warning(
                            f"   ⚠️ REJECT: Depth-limited size ${depth_limited_size_usd:.2f} "
                            f"< min(abs=${self.depth_abs_min_usd:.2f}, "
                            f"rel={self.depth_rel_min_frac*100:.2f}%×${size_after_balance_cap:.2f}=${relative_min:.2f})"
                        )
                        self.execution_stats["depth_rejects"] += 1
                        continue

                    # Check that size meets per-leg exchange minimums
                    if depth_limited_size_usd < self.leg_min_notional_usd * 3:
                        logger.warning(
                            f"   ⚠️ REJECT: Size ${depth_limited_size_usd:.2f} "
                            f"< 3×leg_min (${self.leg_min_notional_usd * 3:.2f})"
                        )
                        self.execution_stats["depth_rejects"] += 1
                        continue

                    # Use depth-limited size for execution, respecting balance cap
                    execution_size = min(depth_limited_size_usd, available_balance)
                    logger.debug(
                        f"   ✅ Final execution size: ${execution_size:.2f} "
                        f"(depth=${depth_limited_size_usd:.2f}, balance=${available_balance:.2f})"
                    )

                    # Re-validate slippage with actual execution size
                    (
                        real_slippage,
                        real_per_leg_details,
                    ) = await self.estimate_cycle_slippage(cycle, execution_size)

                    # Recalculate net profit with real slippage at execution size
                    real_net_profit = gross_profit - fee_cost_pct - real_slippage
                    logger.debug(
                        f"   Real slippage: {real_slippage:.3f}% → net profit: {real_net_profit:.3f}%"
                    )

                    # Reject if real slippage kills the edge
                    # Guardrail: Never execute negative net regardless of config
                    effective_threshold = max(0.0, self.min_profit_threshold)
                    if real_net_profit < effective_threshold:
                        # Check if we can do a test execution (paper mode only)
                        can_test = (
                            self.trading_mode == "paper"
                            and self.test_execute_near_miss
                            and (effective_threshold - real_net_profit)
                            <= self.test_near_miss_gap_bps
                        )
                        if not can_test:
                            logger.warning(
                                f"   ⚠️ REJECT: Real net profit {real_net_profit:.3f}% below threshold"
                            )
                            self.execution_stats["slippage_rejects"] += 1
                            continue
                        else:
                            # Test execution: cap size to small amount
                            execution_size = min(
                                execution_size, self.test_near_miss_size_usd
                            )
                            logger.info(
                                f"   ✳️  TEST EXECUTION: forcing small fill size=${execution_size:.2f} "
                                f"(gap {effective_threshold - real_net_profit:.3f}%) to validate pipeline"
                            )
                            # Continue to execution with capped size

                    # Evaluate with DecisionEngine before execution
                    # Calculate per-leg notional for CEX validation
                    legs_data = []
                    for i, leg in enumerate(real_per_leg_details):
                        legs_data.append(
                            {
                                "notional_usd": execution_size
                                / 3,  # Rough approximation
                                "symbol": leg["symbol"],
                                "side": leg["side"],
                            }
                        )

                    decision = self.decision_engine.evaluate_opportunity(
                        gross_pct=gross_profit,
                        fees_pct=fee_cost_pct,
                        slip_pct=real_slippage,
                        gas_pct=0.0,  # No gas for CEX
                        size_usd=execution_size,
                        legs_data=legs_data,
                        exchange_ready=True,
                        has_quote=True,
                    )

                    # Log decision
                    decision_log = self.decision_engine.format_decision_log(decision)
                    logger.info(decision_log)

                    # Store decision in history
                    self.decision_history.append(decision.to_dict())

                    # Only execute if decision is EXECUTE
                    if decision.action != "EXECUTE":
                        logger.warning(
                            f"   ⚠️ DECISION SKIP: {', '.join(decision.reasons)}"
                        )
                        continue

                    # Execute with depth-limited size
                    result = await self.execute_arbitrage_cycle(cycle, execution_size)

                    if result.get("success"):
                        executed_count += 1
                        self.execution_stats["full_fills"] += 1
                        logger.debug(
                            f"✅ Opportunity {opp_idx + 1} executed successfully!"
                        )
                        # Update balances after successful trade
                        await self.fetch_balances()
                    else:
                        logger.error(f"❌ Opportunity {opp_idx + 1} failed")
                        self.execution_stats["cancels"] += 1

                logger.info(
                    f"\n✅ Executed {executed_count}/{len(opportunities)} "
                    f"opportunities in scan {trade_num}"
                )

                # Print equity after execution
                if executed_count > 0:
                    cur, priced, unpriced = self._equity_usd()
                    delta = cur - self.start_equity_usd
                    deltap = (
                        (delta / self.start_equity_usd * 100.0)
                        if self.start_equity_usd
                        else 0.0
                    )
                    kill_switch_msg = (
                        " [🛑 KILL SWITCH ACTIVE]" if self.kill_switch_active else ""
                    )
                    print(
                        f"💼 Equity: ${cur:,.{self.equity_precision}f} "
                        f"(Δ ${delta:+,.{self.equity_precision}f}, {deltap:+.2f}%){kill_switch_msg}"
                    )

                # Record scan in equity tracker
                await self.equity_tracker.on_scan(self.get_cash, self.get_asset_value)

                # Wait before next cycle
                logger.debug("🔄 Searching for next opportunity...")
                await asyncio.sleep(15)

        except KeyboardInterrupt:
            print(f"\n\n🛑 Stopped after {trade_num} scans")
        except Exception as e:
            logger.error(f"❌ Trading session error: {e}")

        # Print compact summary
        self.print_summary()


async def main():
    """Main trading function"""
    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()

    trading_mode = os.getenv("TRADING_MODE", "paper")

    if trading_mode == "live":
        print("⚠️ WARNING: LIVE TRADING MODE ENABLED ⚠️")
        print("This will trade with real money!")

        # Check LIVE_CONFIRM env var
        live_confirm = os.getenv("LIVE_CONFIRM", "NO").upper()
        if live_confirm != "YES":
            print("❌ LIVE_CONFIRM env variable must be set to 'YES' for live trading")
            print("   Set: export LIVE_CONFIRM=YES")
            return

        confirmation = input("Type 'YES' to continue: ")
        if confirmation != "YES":
            print("Trading cancelled.")
            return

    exchanges_to_try = ["binanceus", "kraken", "kucoin", "coinbase"]

    for exchange_name in exchanges_to_try:
        try:
            trader = RealTriangularArbitrage(exchange_name, trading_mode)
            await trader.run_trading_session()
            break
        except Exception as e:
            logger.error(f"❌ {exchange_name} failed: {e}")
            continue
    else:
        logger.error("❌ All exchanges failed")


if __name__ == "__main__":
    asyncio.run(main())
