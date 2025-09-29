"""
Paper Trading Exchange Adapter

Simulates order execution with realistic slippage, partial fills, and fees.
Uses live market data for price discovery but doesn't execute real trades.
"""

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_adapter import (
    ExchangeAdapter,
    FillInfo,
    MarketData,
    OrderResult,
    OrderSide,
    OrderType,
)

logger = logging.getLogger(__name__)


@dataclass
class PaperOrderState:
    """Internal state for a paper order"""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount_requested: float
    limit_price: Optional[float] = None
    amount_filled: float = 0.0
    fills: List[FillInfo] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"  # 'pending', 'partial', 'filled', 'cancelled'
    error_message: Optional[str] = None
    last_fill_time: float = 0.0


class PaperExchange(ExchangeAdapter):
    """
    Paper trading exchange that simulates realistic order execution

    Features:
    - Configurable slippage simulation
    - Partial fill simulation based on market conditions
    - Realistic fee calculation
    - Market impact modeling for large orders
    - Latency simulation
    """

    def __init__(self, live_exchange, config: Dict[str, Any]):
        """
        Initialize paper exchange

        Args:
            live_exchange: Live exchange instance for market data
            config: Configuration containing:
                - fee_bps: Fee in basis points (default: 30)
                - fill_ratio: Probability of full fill (default: 0.95)
                - spread_padding_bps: Additional spread padding (default: 5)
                - random_seed: Random seed for deterministic testing
                - slippage_model: Slippage model parameters
                - partial_fill_model: Partial fill simulation parameters
        """
        super().__init__(config)
        self.live_exchange = live_exchange
        self._markets = None
        self._balances = config.get("initial_balances", {}).copy()
        self._orders: Dict[str, PaperOrderState] = {}

        # Configuration
        self.fee_bps = config.get("fee_bps", 30)
        self.fill_ratio = config.get("fill_ratio", 0.95)
        self.spread_padding_bps = config.get("spread_padding_bps", 5)
        self.latency_sim_ms = config.get("latency_sim_ms", 50)

        # Market impact model
        self.market_impact = config.get(
            "market_impact",
            {
                "enabled": True,
                "impact_coefficient": 0.1,  # bps per $1000 notional
                "max_impact_bps": 50,  # Maximum impact
            },
        )

        # Partial fill model
        self.partial_fill_config = config.get(
            "partial_fill_model",
            {
                "enabled": True,
                "min_fill_ratio": 0.3,  # Minimum fill percentage
                "fill_time_spread_ms": 500,  # Time spread for partial fills
                "large_order_threshold": 1000,  # USD threshold for partial fills
            },
        )

        # Slippage model
        self.slippage_config = config.get(
            "slippage_model",
            {
                "base_slippage_bps": 2,  # Base slippage
                "volatility_multiplier": 1.5,  # Volatility impact
                "random_component_bps": 3,  # Random slippage component
                "adverse_selection_bps": 1,  # Adverse selection cost
            },
        )

        # Initialize random seed for deterministic testing
        self.rng = random.Random(config.get("random_seed"))

        # Metrics tracking
        self.metrics = {
            "orders_created": 0,
            "orders_filled": 0,
            "orders_partially_filled": 0,
            "orders_cancelled": 0,
            "total_volume": 0.0,
            "total_fees": 0.0,
            "average_slippage_bps": 0.0,
            "fills_count": 0,
        }

    async def initialize(self) -> None:
        """Initialize the paper exchange"""
        await self.live_exchange.load_markets()
        logger.info("PaperExchange initialized with live market data feed")

    async def load_markets(self) -> Dict[str, Dict]:
        """Load markets from live exchange"""
        if self._markets is None:
            self._markets = await self.live_exchange.load_markets()
        return self._markets

    async def fetch_ticker(self, symbol: str) -> MarketData:
        """Fetch live market data with timeout"""
        import asyncio

        try:
            # Add timeout to prevent hanging
            ticker = await asyncio.wait_for(
                self.live_exchange.fetch_ticker(symbol), timeout=2.0  # 2 second timeout
            )
            return MarketData(
                symbol=symbol,
                bid=ticker["bid"],
                ask=ticker["ask"],
                last=ticker["last"],
                volume=ticker["quoteVolume"],
                timestamp=time.time(),
            )
        except asyncio.TimeoutError:
            logger.warning(f"Ticker fetch timeout for {symbol}, using synthetic data")
            return self._generate_synthetic_ticker(symbol)
        except Exception as e:
            logger.warning(
                f"Failed to fetch live ticker for {symbol}: {e}, using synthetic data"
            )
            return self._generate_synthetic_ticker(symbol)

    async def fetch_balance(self) -> Dict[str, float]:
        """Return simulated balances"""
        return self._balances.copy()

    async def create_market_order(
        self, symbol: str, side: OrderSide, amount: float
    ) -> OrderResult:
        """Create and immediately simulate execution of market order"""
        order_id = str(uuid.uuid4())

        order_state = PaperOrderState(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            amount_requested=amount,
        )

        self._orders[order_id] = order_state
        self.metrics["orders_created"] += 1

        # Simulate execution latency
        if self.latency_sim_ms > 0:
            await asyncio.sleep(self.latency_sim_ms / 1000.0)

        try:
            # Get market data (with timeout protection)
            market_data = await self.fetch_ticker(symbol)

            # Simulate market order execution
            return await self._execute_market_order(order_state, market_data)

        except Exception as e:
            order_state.status = "failed"
            order_state.error_message = str(e)
            logger.error(f"Paper order execution failed: {e}")

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
        """Create limit order (immediately filled if price is favorable)"""
        order_id = str(uuid.uuid4())

        order_state = PaperOrderState(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            amount_requested=amount,
            limit_price=price,
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
                # Execute as market order with limit price
                return await self._execute_market_order(
                    order_state, market_data, limit_price=price
                )
            else:
                # Order remains pending (simplified - real implementation would monitor)
                order_state.status = "pending"
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

    async def create_market_buy_order(
        self, symbol: str, amount: float, price: float = None
    ) -> OrderResult:
        """Create market buy order"""
        return await self.create_market_order(symbol, OrderSide.BUY, amount)

    async def create_market_sell_order(
        self, symbol: str, amount: float, price: float = None
    ) -> OrderResult:
        """Create market sell order"""
        return await self.create_market_order(symbol, OrderSide.SELL, amount)

    async def fetch_order(self, order_id: str, symbol: str = None) -> OrderResult:
        """Fetch order status (alias for fetch_order_status)"""
        return await self.fetch_order_status(order_id, symbol or "")

    async def fetch_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get current order status"""
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
        """Cancel an order"""
        if order_id in self._orders:
            order_state = self._orders[order_id]
            if order_state.status == "pending":
                order_state.status = "cancelled"
                self.metrics["orders_cancelled"] += 1
                return True
        return False

    async def close(self) -> None:
        """Clean up resources"""
        pass

    async def _execute_market_order(
        self,
        order_state: PaperOrderState,
        market_data: MarketData,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """Execute market order simulation with realistic behavior"""

        # Calculate execution price with slippage
        base_price = (
            market_data.ask if order_state.side == OrderSide.BUY else market_data.bid
        )
        execution_price = self._calculate_execution_price(
            base_price, order_state.side, order_state.amount_requested, market_data
        )

        # Apply limit price constraint if specified
        if limit_price is not None:
            if order_state.side == OrderSide.BUY and execution_price > limit_price:
                execution_price = limit_price
            elif order_state.side == OrderSide.SELL and execution_price < limit_price:
                execution_price = limit_price

        # Determine fill behavior
        fill_amount, should_partial_fill = self._determine_fill_amount(
            order_state.amount_requested, execution_price, market_data
        )

        if should_partial_fill:
            # Simulate partial fills over time
            await self._simulate_partial_fills(
                order_state, execution_price, fill_amount
            )
        else:
            # Single complete fill
            await self._create_fill(order_state, execution_price, fill_amount)

        # Update balances
        self._update_balances(order_state)

        # Update metrics
        self._update_metrics(order_state)

        # Return final order result
        return await self.fetch_order_status(order_state.order_id, order_state.symbol)

    def _generate_synthetic_ticker(self, symbol: str) -> "MarketData":
        """Generate synthetic market data to avoid hanging on live data"""
        import random
        import time

        from triangular_arbitrage.market_data import MarketData

        # Base prices for common pairs
        base_prices = {
            "BTC/USD": 50000.0,
            "ETH/USD": 3000.0,
            "XLM/USD": 0.12,
            "DASH/USD": 35.0,
            "MASK/USD": 2.8,
            "COMP/USD": 55.0,
            "USDT/USD": 1.0,
            "USD/USDT": 1.0,
            "BTC/USDT": 50000.0,
            "ETH/BTC": 0.06,
            "XLM/BTC": 0.0000024,
            "XLM/USDT": 0.12,
            "MASK/USDT": 2.8,
            "DASH/BTC": 0.0007,
        }

        # Get base price with small random variation
        base_price = base_prices.get(symbol, 1.0)
        variation = random.uniform(-0.01, 0.01)  # ±1% variation
        last_price = base_price * (1 + variation)

        # Create spread (0.1% typical)
        spread = last_price * 0.001
        bid = last_price - spread / 2
        ask = last_price + spread / 2

        return MarketData(
            symbol=symbol,
            last=last_price,
            bid=bid,
            ask=ask,
            high=last_price * 1.02,
            low=last_price * 0.98,
            volume=1000.0,
            timestamp=int(time.time() * 1000),
        )

    def _calculate_execution_price(
        self, base_price: float, side: OrderSide, amount: float, market_data: MarketData
    ) -> float:
        """Calculate execution price with slippage model"""
        slippage_bps = 0.0

        # Base slippage
        slippage_bps += self.slippage_config["base_slippage_bps"]

        # Market impact for large orders
        if self.market_impact["enabled"]:
            notional_value = amount * base_price
            impact_coefficient = self.market_impact["impact_coefficient"]
            market_impact_bps = min(
                (notional_value / 1000.0) * impact_coefficient,
                self.market_impact["max_impact_bps"],
            )
            slippage_bps += market_impact_bps

        # Add spread padding
        slippage_bps += self.spread_padding_bps

        # Random component
        random_slippage = self.rng.uniform(
            -self.slippage_config["random_component_bps"],
            self.slippage_config["random_component_bps"],
        )
        slippage_bps += random_slippage

        # Adverse selection (always unfavorable)
        slippage_bps += self.slippage_config["adverse_selection_bps"]

        # Apply slippage
        slippage_factor = slippage_bps / 10000.0
        if side == OrderSide.BUY:
            # Buy orders get worse (higher) prices
            execution_price = base_price * (1 + slippage_factor)
        else:
            # Sell orders get worse (lower) prices
            execution_price = base_price * (1 - slippage_factor)

        return max(execution_price, 0.0)  # Ensure non-negative

    def _determine_fill_amount(
        self, requested_amount: float, execution_price: float, market_data: MarketData
    ) -> tuple[float, bool]:
        """Determine how much of the order should be filled and if it should be partial"""

        # Check if order should fill completely
        if self.rng.random() < self.fill_ratio:
            return requested_amount, False

        # Determine if order qualifies for partial fill simulation
        notional_value = requested_amount * execution_price
        should_partial_fill = (
            self.partial_fill_config["enabled"]
            and notional_value > self.partial_fill_config["large_order_threshold"]
        )

        if should_partial_fill:
            # Partial fill between min_fill_ratio and full amount
            min_fill = requested_amount * self.partial_fill_config["min_fill_ratio"]
            fill_amount = self.rng.uniform(min_fill, requested_amount)
            return fill_amount, True
        else:
            # Small order gets partial fill in single shot
            partial_ratio = self.rng.uniform(0.7, 0.95)  # 70-95% fill
            return requested_amount * partial_ratio, False

    async def _simulate_partial_fills(
        self, order_state: PaperOrderState, base_price: float, total_fill_amount: float
    ) -> None:
        """Simulate partial fills over time"""
        remaining_amount = total_fill_amount
        fill_count = self.rng.randint(2, 5)  # 2-5 partial fills

        for i in range(fill_count):
            if remaining_amount <= 0:
                break

            # Determine fill size (larger fills earlier)
            if i == fill_count - 1:
                # Last fill gets remainder
                fill_size = remaining_amount
            else:
                max_fill = remaining_amount * 0.6  # Max 60% in one fill
                min_fill = remaining_amount * 0.1  # Min 10% in one fill
                fill_size = self.rng.uniform(min_fill, max_fill)

            # Slight price variation for each fill
            price_variance = self.rng.uniform(-0.001, 0.001)  # ±0.1%
            fill_price = base_price * (1 + price_variance)

            await self._create_fill(order_state, fill_price, fill_size)
            remaining_amount -= fill_size

            # Simulate time between fills
            if i < fill_count - 1:
                fill_delay = self.rng.uniform(0.05, 0.2)  # 50-200ms between fills
                await asyncio.sleep(fill_delay)

    async def _create_fill(
        self, order_state: PaperOrderState, price: float, amount: float
    ) -> None:
        """Create a fill and update order state"""

        # Calculate fee
        fee_rate = self.get_fee_rate(
            order_state.symbol, order_state.side, order_state.order_type
        )
        fee = amount * price * fee_rate

        # Create fill
        fill = FillInfo(
            order_id=order_state.order_id,
            symbol=order_state.symbol,
            side=order_state.side,
            amount=amount,
            price=price,
            fee=fee,
            timestamp=time.time(),
            fill_id=str(uuid.uuid4()),
            trade_id=str(uuid.uuid4()),
            is_partial=(
                order_state.amount_filled + amount < order_state.amount_requested
            ),
        )

        order_state.fills.append(fill)
        order_state.amount_filled += amount
        order_state.last_fill_time = time.time()

        # Update status
        if order_state.amount_filled >= order_state.amount_requested:
            order_state.status = "filled"
        else:
            order_state.status = "partial"

    def _update_balances(self, order_state: PaperOrderState) -> None:
        """Update simulated balances based on fills"""
        base_currency, quote_currency = order_state.symbol.split("/")

        for fill in order_state.fills:
            # Get current balances
            current_base = self._balances.get(base_currency, 0.0)
            current_quote = self._balances.get(quote_currency, 0.0)

            if order_state.side == OrderSide.BUY:
                # Buying base currency with quote currency
                # Add to base currency, subtract cost from quote currency
                self._balances[base_currency] = current_base + fill.amount
                self._balances[quote_currency] = current_quote - (
                    fill.amount * fill.price + fill.fee
                )
            else:
                # Selling base currency for quote currency
                # Subtract from base currency, add proceeds to quote currency
                self._balances[base_currency] = current_base - fill.amount
                self._balances[quote_currency] = current_quote + (
                    fill.amount * fill.price - fill.fee
                )

    def _update_metrics(self, order_state: PaperOrderState) -> None:
        """Update execution metrics"""
        if order_state.status == "filled":
            self.metrics["orders_filled"] += 1
        elif order_state.status == "partial":
            self.metrics["orders_partially_filled"] += 1

        total_volume = sum(fill.amount * fill.price for fill in order_state.fills)
        total_fees = sum(fill.fee for fill in order_state.fills)

        self.metrics["total_volume"] += total_volume
        self.metrics["total_fees"] += total_fees
        self.metrics["fills_count"] += len(order_state.fills)

    async def get_execution_metrics(self) -> Dict[str, Any]:
        """Get detailed execution metrics"""
        total_orders = self.metrics["orders_created"]
        fill_rate = (
            self.metrics["orders_filled"] / total_orders if total_orders > 0 else 0.0
        )
        partial_fill_rate = (
            self.metrics["orders_partially_filled"] / total_orders
            if total_orders > 0
            else 0.0
        )
        avg_fee_rate = (
            self.metrics["total_fees"] / self.metrics["total_volume"]
            if self.metrics["total_volume"] > 0
            else 0.0
        )

        return {
            "execution_mode": "paper",
            "orders_created": total_orders,
            "orders_filled": self.metrics["orders_filled"],
            "orders_partially_filled": self.metrics["orders_partially_filled"],
            "orders_cancelled": self.metrics["orders_cancelled"],
            "fill_rate": fill_rate,
            "partial_fill_rate": partial_fill_rate,
            "total_volume_usd": self.metrics["total_volume"],
            "total_fees_paid": self.metrics["total_fees"],
            "average_fee_rate_bps": avg_fee_rate * 10000,
            "fills_per_order": (
                self.metrics["fills_count"] / total_orders if total_orders > 0 else 0.0
            ),
            "current_balances": self._balances.copy(),
        }

    def get_minimum_order_size(self, symbol: str) -> float:
        """Get minimum order size for symbol"""
        # Use live exchange minimums if available
        if self._markets and symbol in self._markets:
            limits = self._markets[symbol].get("limits", {})
            amount_limit = limits.get("amount", {})
            return amount_limit.get("min", 0.001)  # Default minimum
        return 0.001

    def get_fee_rate(
        self, symbol: str, side: OrderSide, order_type: OrderType
    ) -> float:
        """Get fee rate for trading"""
        return self.fee_bps / 10000.0  # Convert basis points to decimal
