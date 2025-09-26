"""
Backtest Exchange Adapter

Replays historical market data from CSV files for deterministic backtesting.
Supports time-based simulation with configurable slippage and fill models.
"""

import asyncio
import csv
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
# bisect removed - not used in current implementation

from .base_adapter import (
    ExchangeAdapter,
    OrderResult,
    FillInfo,
    MarketData,
    OrderSide,
    OrderType,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestTick:
    """Single market data point"""

    timestamp: float
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float

    def to_market_data(self) -> MarketData:
        return MarketData(
            symbol=self.symbol,
            bid=self.bid,
            ask=self.ask,
            last=self.last,
            volume=self.volume,
            timestamp=self.timestamp,
        )


@dataclass
class BacktestOrderState:
    """Internal state for backtest orders"""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount_requested: float
    limit_price: Optional[float] = None
    amount_filled: float = 0.0
    fills: List[FillInfo] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"
    error_message: Optional[str] = None


class BacktestExchange(ExchangeAdapter):
    """
    Backtest exchange that replays historical market data

    Features:
    - CSV data replay with time synchronization
    - Deterministic execution with seeded randomness
    - Market impact modeling based on order size
    - Configurable slippage and fill behavior
    - Time-based partial fill simulation
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize backtest exchange

        Args:
            config: Configuration containing:
                - data_file: Path to CSV data file
                - start_time: Start timestamp for backtest
                - end_time: End timestamp for backtest
                - time_acceleration: Speed multiplier (default: 1.0)
                - random_seed: Random seed for deterministic results
                - slippage_model: Slippage parameters
                - market_impact_model: Market impact parameters
        """
        super().__init__(config)

        # Data configuration
        self.data_file = config.get("data_file", "data/backtests/sample_feed.csv")
        self.start_time = config.get("start_time")
        self.end_time = config.get("end_time")
        self.time_acceleration = config.get("time_acceleration", 1.0)

        # Market data storage
        self._market_data: Dict[str, List[BacktestTick]] = {}
        self._market_indices: Dict[str, int] = {}
        self._current_time = 0.0
        self._simulation_start = time.time()
        self._data_loaded = False

        # Order management
        self._orders: Dict[str, BacktestOrderState] = {}
        self._balances = config.get("initial_balances", {})

        # Randomness for deterministic testing
        self.rng = random.Random(config.get("random_seed", 42))

        # Models
        self.slippage_model = config.get(
            "slippage_model",
            {
                "base_slippage_bps": 3,
                "size_impact_coefficient": 0.05,
                "max_slippage_bps": 100,
                "random_component_bps": 2,
            },
        )

        self.fill_model = config.get(
            "fill_model",
            {
                "fill_probability": 0.98,
                "partial_fill_threshold": 1000,  # USD threshold for partial fills
                "min_fill_ratio": 0.3,
                "max_fill_time_ms": 1000,
            },
        )

        # Markets simulation
        self._markets = {}

        # Metrics
        self.metrics = {
            "data_points_processed": 0,
            "orders_created": 0,
            "orders_filled": 0,
            "orders_partially_filled": 0,
            "orders_failed": 0,
            "total_slippage_bps": 0.0,
            "total_volume": 0.0,
            "simulation_start_time": None,
            "simulation_end_time": None,
            "backtest_duration_seconds": 0.0,
            "wall_clock_duration_seconds": 0.0,
        }

    async def initialize(self) -> None:
        """Initialize backtest exchange and load data"""
        await self._load_market_data()
        self._setup_simulation_time()
        self.metrics["simulation_start_time"] = self._current_time
        logger.info(
            f"BacktestExchange initialized with {len(self._market_data)} symbols"
        )

    async def _load_market_data(self) -> None:
        """Load historical market data from CSV"""
        data_path = Path(self.data_file)
        if not data_path.exists():
            from ..exceptions import DataError
            raise DataError(f"Backtest data file not found: {self.data_file}", source="file_system")

        logger.info(f"Loading backtest data from {self.data_file}")

        with open(data_path, "r") as f:
            reader = csv.DictReader(f)
            row_count = 0

            for row in reader:
                try:
                    tick = BacktestTick(
                        timestamp=float(row["timestamp"]),
                        symbol=row["symbol"],
                        bid=float(row["bid"]),
                        ask=float(row["ask"]),
                        last=float(row["last"]),
                        volume=float(row.get("volume", 0)),
                    )

                    # Filter by time range if specified
                    if self.start_time and tick.timestamp < self.start_time:
                        continue
                    if self.end_time and tick.timestamp > self.end_time:
                        continue

                    if tick.symbol not in self._market_data:
                        self._market_data[tick.symbol] = []
                        self._market_indices[tick.symbol] = 0

                    self._market_data[tick.symbol].append(tick)
                    row_count += 1

                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping invalid data row: {row} - {e}")

        # Sort data by timestamp for each symbol
        for symbol in self._market_data:
            self._market_data[symbol].sort(key=lambda x: x.timestamp)

        logger.info(
            f"Loaded {row_count} market data points for {len(self._market_data)} symbols"
        )
        self._data_loaded = True

    def _setup_simulation_time(self) -> None:
        """Set up simulation time based on data"""
        if not self._market_data:
            from ..exceptions import DataError
            raise DataError("No market data loaded", source="backtest_engine")

        # Find earliest timestamp across all symbols
        earliest_times = []
        for symbol_data in self._market_data.values():
            if symbol_data:
                earliest_times.append(symbol_data[0].timestamp)

        if earliest_times:
            self._current_time = min(earliest_times)
            logger.info(
                f"Backtest simulation starting at {datetime.fromtimestamp(self._current_time)}"
            )

    async def load_markets(self) -> Dict[str, Dict]:
        """Return simulated market info"""
        if not self._markets:
            for symbol in self._market_data.keys():
                base, quote = symbol.split("/")
                self._markets[symbol] = {
                    "id": symbol,
                    "symbol": symbol,
                    "base": base,
                    "quote": quote,
                    "active": True,
                    "limits": {
                        "amount": {"min": 0.001, "max": None},
                        "cost": {"min": 1.0, "max": None},
                    },
                }
        return self._markets

    async def fetch_ticker(self, symbol: str) -> MarketData:
        """Fetch current market data for symbol at current simulation time"""
        if symbol not in self._market_data:
            raise ValueError(f"No market data available for {symbol}")

        symbol_data = self._market_data[symbol]
        current_index = self._market_indices[symbol]

        # Find the most recent tick at or before current time
        while (
            current_index < len(symbol_data) - 1
            and symbol_data[current_index + 1].timestamp <= self._current_time
        ):
            current_index += 1

        self._market_indices[symbol] = current_index

        if current_index >= len(symbol_data):
            from ..exceptions import DataError
            raise DataError(
                f"No market data available for {symbol} at time {self._current_time}",
                symbol=symbol, source="backtest_engine"
            )

        tick = symbol_data[current_index]
        return tick.to_market_data()

    async def fetch_balance(self) -> Dict[str, float]:
        """Return simulated balances"""
        return self._balances.copy()

    async def create_market_order(
        self, symbol: str, side: OrderSide, amount: float
    ) -> OrderResult:
        """Create and simulate market order execution"""
        order_id = str(uuid.uuid4())

        order_state = BacktestOrderState(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            amount_requested=amount,
            timestamp=self._current_time,
        )

        self._orders[order_id] = order_state
        self.metrics["orders_created"] += 1

        try:
            market_data = await self.fetch_ticker(symbol)
            return await self._simulate_order_execution(order_state, market_data)

        except Exception as e:
            order_state.status = "failed"
            order_state.error_message = str(e)
            self.metrics["orders_failed"] += 1

            return OrderResult(
                order_id=order_id,
                symbol=symbol,
                side=side,
                amount_requested=amount,
                amount_filled=0.0,
                average_price=0.0,
                total_fee=0.0,
                fills=[],
                status="failed",
                error_message=str(e),
            )

    async def create_limit_order(
        self, symbol: str, side: OrderSide, amount: float, price: float
    ) -> OrderResult:
        """Create limit order (simplified - immediately check if fillable)"""
        order_id = str(uuid.uuid4())

        order_state = BacktestOrderState(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            amount_requested=amount,
            limit_price=price,
            timestamp=self._current_time,
        )

        self._orders[order_id] = order_state
        self.metrics["orders_created"] += 1

        try:
            market_data = await self.fetch_ticker(symbol)

            # Check if limit order can be filled immediately
            can_fill = (side == OrderSide.BUY and price >= market_data.ask) or (
                side == OrderSide.SELL and price <= market_data.bid
            )

            if can_fill:
                return await self._simulate_order_execution(
                    order_state, market_data, limit_price=price
                )
            else:
                # Order remains pending (would need limit order book simulation for full accuracy)
                return OrderResult(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    amount_requested=amount,
                    amount_filled=0.0,
                    average_price=0.0,
                    total_fee=0.0,
                    fills=[],
                    status="pending",
                )

        except Exception as e:
            order_state.status = "failed"
            order_state.error_message = str(e)
            self.metrics["orders_failed"] += 1

            return OrderResult(
                order_id=order_id,
                symbol=symbol,
                side=side,
                amount_requested=amount,
                amount_filled=0.0,
                average_price=0.0,
                total_fee=0.0,
                fills=[],
                status="failed",
                error_message=str(e),
            )

    async def fetch_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get order status"""
        if order_id not in self._orders:
            return OrderResult(
                order_id=order_id,
                symbol=symbol,
                side=OrderSide.BUY,
                amount_requested=0.0,
                amount_filled=0.0,
                average_price=0.0,
                total_fee=0.0,
                fills=[],
                status="failed",
                error_message="Order not found",
            )

        order_state = self._orders[order_id]
        total_fee = sum(fill.fee for fill in order_state.fills)
        avg_price = (
            sum(fill.price * fill.amount for fill in order_state.fills)
            / order_state.amount_filled
            if order_state.amount_filled > 0
            else 0.0
        )

        return OrderResult(
            order_id=order_id,
            symbol=order_state.symbol,
            side=order_state.side,
            amount_requested=order_state.amount_requested,
            amount_filled=order_state.amount_filled,
            average_price=avg_price,
            total_fee=total_fee,
            fills=order_state.fills.copy(),
            status=order_state.status,
            error_message=order_state.error_message,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order"""
        if order_id in self._orders:
            order_state = self._orders[order_id]
            if order_state.status == "pending":
                order_state.status = "cancelled"
                return True
        return False

    async def close(self) -> None:
        """Finalize backtest and calculate metrics"""
        self.metrics["simulation_end_time"] = self._current_time
        self.metrics["wall_clock_duration_seconds"] = (
            time.time() - self._simulation_start
        )

        if self.metrics["simulation_start_time"]:
            self.metrics["backtest_duration_seconds"] = (
                self.metrics["simulation_end_time"]
                - self.metrics["simulation_start_time"]
            )

    async def _simulate_order_execution(
        self,
        order_state: BacktestOrderState,
        market_data: MarketData,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """Simulate order execution with backtest-specific logic"""

        # Check fill probability
        if self.rng.random() > self.fill_model["fill_probability"]:
            order_state.status = "failed"
            order_state.error_message = "Order rejected by exchange"
            self.metrics["orders_failed"] += 1
            return await self.fetch_order_status(
                order_state.order_id, order_state.symbol
            )

        # Calculate execution price with slippage
        base_price = (
            market_data.ask if order_state.side == OrderSide.BUY else market_data.bid
        )
        execution_price = self._calculate_execution_price(
            base_price, order_state.side, order_state.amount_requested, market_data
        )

        # Apply limit price constraint
        if limit_price is not None:
            if order_state.side == OrderSide.BUY and execution_price > limit_price:
                execution_price = limit_price
            elif order_state.side == OrderSide.SELL and execution_price < limit_price:
                execution_price = limit_price

        # Determine fill amount and pattern
        notional_value = order_state.amount_requested * execution_price
        if notional_value > self.fill_model["partial_fill_threshold"]:
            # Large order - simulate partial fills
            fill_ratio = self.rng.uniform(self.fill_model["min_fill_ratio"], 1.0)
            fill_amount = order_state.amount_requested * fill_ratio
            await self._create_backtest_fills(order_state, execution_price, fill_amount)
        else:
            # Small order - single fill
            await self._create_single_fill(
                order_state, execution_price, order_state.amount_requested
            )

        # Update balances and metrics
        self._update_balances(order_state)
        self._update_metrics(order_state)

        return await self.fetch_order_status(order_state.order_id, order_state.symbol)

    def _calculate_execution_price(
        self, base_price: float, side: OrderSide, amount: float, market_data: MarketData
    ) -> float:
        """Calculate execution price with slippage for backtest"""
        slippage_bps = self.slippage_model["base_slippage_bps"]

        # Size-based slippage
        notional_value = amount * base_price
        size_impact = (notional_value / 1000.0) * self.slippage_model[
            "size_impact_coefficient"
        ]
        slippage_bps += min(size_impact, self.slippage_model["max_slippage_bps"])

        # Random component (deterministic with seed)
        random_slippage = self.rng.uniform(
            -self.slippage_model["random_component_bps"],
            self.slippage_model["random_component_bps"],
        )
        slippage_bps += random_slippage

        # Apply slippage
        slippage_factor = slippage_bps / 10000.0
        if side == OrderSide.BUY:
            execution_price = base_price * (1 + slippage_factor)
        else:
            execution_price = base_price * (1 - slippage_factor)

        # Track slippage for metrics
        self.metrics["total_slippage_bps"] += abs(slippage_bps)

        return max(execution_price, 0.0)

    async def _create_backtest_fills(
        self, order_state: BacktestOrderState, base_price: float, total_amount: float
    ) -> None:
        """Create multiple fills for large orders"""
        remaining = total_amount
        fill_count = self.rng.randint(2, 4)

        for i in range(fill_count):
            if remaining <= 0:
                break

            if i == fill_count - 1:
                fill_amount = remaining
            else:
                max_fill = remaining * 0.7
                fill_amount = self.rng.uniform(remaining * 0.2, max_fill)

            # Small price variance per fill
            price_var = self.rng.uniform(-0.0005, 0.0005)
            fill_price = base_price * (1 + price_var)

            await self._create_single_fill(order_state, fill_price, fill_amount)
            remaining -= fill_amount

            # Simulate time between fills
            time_delay_ms = self.rng.uniform(50, 200)
            await self._advance_simulation_time(time_delay_ms / 1000.0)

    async def _create_single_fill(
        self, order_state: BacktestOrderState, price: float, amount: float
    ) -> None:
        """Create a single fill"""
        fee_rate = self.get_fee_rate(
            order_state.symbol, order_state.side, order_state.order_type
        )
        fee = amount * price * fee_rate

        fill = FillInfo(
            order_id=order_state.order_id,
            symbol=order_state.symbol,
            side=order_state.side,
            amount=amount,
            price=price,
            fee=fee,
            timestamp=self._current_time,
            fill_id=str(uuid.uuid4()),
            trade_id=str(uuid.uuid4()),
            is_partial=(
                order_state.amount_filled + amount < order_state.amount_requested
            ),
        )

        order_state.fills.append(fill)
        order_state.amount_filled += amount

        if order_state.amount_filled >= order_state.amount_requested:
            order_state.status = "filled"
        else:
            order_state.status = "partial"

    def _update_balances(self, order_state: BacktestOrderState) -> None:
        """Update simulated balances"""
        base_currency, quote_currency = order_state.symbol.split("/")

        for fill in order_state.fills:
            if order_state.side == OrderSide.BUY:
                self._balances[base_currency] = (
                    self._balances.get(base_currency, 0.0) + fill.amount
                )
                self._balances[quote_currency] = self._balances.get(
                    quote_currency, 0.0
                ) - (fill.amount * fill.price + fill.fee)
            else:
                self._balances[base_currency] = (
                    self._balances.get(base_currency, 0.0) - fill.amount
                )
                self._balances[quote_currency] = self._balances.get(
                    quote_currency, 0.0
                ) + (fill.amount * fill.price - fill.fee)

    def _update_metrics(self, order_state: BacktestOrderState) -> None:
        """Update execution metrics"""
        if order_state.status == "filled":
            self.metrics["orders_filled"] += 1
        elif order_state.status == "partial":
            self.metrics["orders_partially_filled"] += 1

        total_volume = sum(fill.amount * fill.price for fill in order_state.fills)
        self.metrics["total_volume"] += total_volume

    async def _advance_simulation_time(self, seconds: float) -> None:
        """Advance simulation time"""
        self._current_time += seconds

        # Optional: sleep for realistic time if time_acceleration is set
        if self.time_acceleration > 0:
            await asyncio.sleep(seconds / self.time_acceleration)

    def advance_time_to(self, target_timestamp: float) -> None:
        """Advance simulation to specific timestamp"""
        if target_timestamp > self._current_time:
            self._current_time = target_timestamp

    def get_current_simulation_time(self) -> float:
        """Get current simulation timestamp"""
        return self._current_time

    async def get_execution_metrics(self) -> Dict[str, Any]:
        """Get comprehensive backtest metrics"""
        total_orders = self.metrics["orders_created"]
        avg_slippage = (
            self.metrics["total_slippage_bps"] / total_orders
            if total_orders > 0
            else 0.0
        )

        return {
            "execution_mode": "backtest",
            "data_file": self.data_file,
            "simulation_start_time": self.metrics["simulation_start_time"],
            "simulation_end_time": self.metrics["simulation_end_time"],
            "backtest_duration_seconds": self.metrics["backtest_duration_seconds"],
            "wall_clock_duration_seconds": self.metrics["wall_clock_duration_seconds"],
            "time_acceleration_factor": (
                self.metrics["backtest_duration_seconds"]
                / self.metrics["wall_clock_duration_seconds"]
                if self.metrics["wall_clock_duration_seconds"] > 0
                else 0.0
            ),
            "orders_created": total_orders,
            "orders_filled": self.metrics["orders_filled"],
            "orders_partially_filled": self.metrics["orders_partially_filled"],
            "orders_failed": self.metrics["orders_failed"],
            "fill_rate": (
                self.metrics["orders_filled"] / total_orders
                if total_orders > 0
                else 0.0
            ),
            "total_volume_usd": self.metrics["total_volume"],
            "average_slippage_bps": avg_slippage,
            "data_points_processed": len(self._market_data),
            "symbols_traded": list(self._market_data.keys()),
            "final_balances": self._balances.copy(),
        }

    def get_minimum_order_size(self, symbol: str) -> float:
        """Get minimum order size"""
        return 0.001

    def get_fee_rate(
        self, symbol: str, side: OrderSide, order_type: OrderType
    ) -> float:
        """Get trading fee rate"""
        fees = self.config.get("fees", {})
        if order_type == OrderType.MARKET:
            return fees.get("taker_bps", 30) / 10000.0
        else:
            return fees.get("maker_bps", 10) / 10000.0
