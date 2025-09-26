"""
Base Exchange Adapter Interface

Provides the abstraction layer between the trading engine and exchange implementations.
Supports live trading, paper trading, and backtesting modes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class FillInfo:
    """Information about an order fill"""

    order_id: str
    symbol: str
    side: OrderSide
    amount: float
    price: float
    fee: float
    timestamp: float
    fill_id: str
    trade_id: Optional[str] = None
    is_partial: bool = False


@dataclass
class OrderResult:
    """Result of placing/monitoring an order"""

    order_id: str
    symbol: str
    side: OrderSide
    amount_requested: float
    amount_filled: float
    average_price: float
    total_fee: float
    fills: List[FillInfo]
    status: str  # 'filled', 'partial', 'cancelled', 'failed'
    error_message: Optional[str] = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class MarketData:
    """Market data snapshot"""

    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: float


class ExchangeAdapter(ABC):
    """Abstract base class for exchange adapters"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize exchange adapter

        Args:
            config: Configuration dictionary containing:
                - execution_mode: 'live', 'paper', 'backtest'
                - fees: Fee configuration
                - slippage: Slippage configuration
                - other mode-specific parameters
        """
        self.config = config
        self.execution_mode = config.get("execution_mode", "live")

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the adapter (load markets, connect, etc.)"""
        pass

    @abstractmethod
    async def load_markets(self) -> Dict[str, Dict]:
        """Load market information"""
        pass

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> MarketData:
        """Fetch current market data for a symbol"""
        pass

    @abstractmethod
    async def fetch_balance(self) -> Dict[str, float]:
        """Fetch account balances"""
        pass

    @abstractmethod
    async def create_market_order(
        self, symbol: str, side: OrderSide, amount: float
    ) -> OrderResult:
        """Create a market order"""
        pass

    @abstractmethod
    async def create_limit_order(
        self, symbol: str, side: OrderSide, amount: float, price: float
    ) -> OrderResult:
        """Create a limit order"""
        pass

    @abstractmethod
    async def fetch_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Fetch current order status"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources"""
        pass

    # Optional methods for specific functionality
    async def get_execution_metrics(self) -> Dict[str, Any]:
        """Get execution metrics (for paper/backtest modes)"""
        return {}

    def supports_partial_fills(self) -> bool:
        """Whether this adapter supports partial fills"""
        return True

    def get_minimum_order_size(self, symbol: str) -> float:
        """Get minimum order size for a symbol"""
        return 0.0

    def get_fee_rate(
        self, symbol: str, side: OrderSide, order_type: OrderType
    ) -> float:
        """Get fee rate for a trade"""
        fees = self.config.get("fees", {})
        if order_type == OrderType.MARKET:
            return fees.get("taker_bps", 30) / 10000.0  # Default 0.3%
        else:
            return fees.get("maker_bps", 10) / 10000.0  # Default 0.1%


class LiveExchangeAdapter(ExchangeAdapter):
    """Wrapper for live exchange implementations (ccxt-based)"""

    def __init__(self, exchange_instance, config: Dict[str, Any]):
        """
        Wrap an existing exchange instance (e.g., ccxt exchange)

        Args:
            exchange_instance: Live exchange instance (ccxt)
            config: Configuration
        """
        super().__init__(config)
        self.exchange = exchange_instance
        self._markets = None

    async def initialize(self) -> None:
        """Initialize the live exchange"""
        if hasattr(self.exchange, "load_markets"):
            await self.exchange.load_markets()

    async def load_markets(self) -> Dict[str, Dict]:
        """Load markets from live exchange"""
        if self._markets is None:
            self._markets = await self.exchange.load_markets()
        return self._markets

    async def fetch_ticker(self, symbol: str) -> MarketData:
        """Fetch ticker from live exchange"""
        ticker = await self.exchange.fetch_ticker(symbol)
        return MarketData(
            symbol=symbol,
            bid=ticker["bid"],
            ask=ticker["ask"],
            last=ticker["last"],
            volume=ticker["quoteVolume"],
            timestamp=time.time(),
        )

    async def fetch_balance(self) -> Dict[str, float]:
        """Fetch balance from live exchange"""
        balance = await self.exchange.fetch_balance()
        return balance.get("free", {})

    async def create_market_order(
        self, symbol: str, side: OrderSide, amount: float
    ) -> OrderResult:
        """Create market order on live exchange"""
        try:
            if side == OrderSide.BUY:
                order = await self.exchange.create_market_buy_order(symbol, amount)
            else:
                order = await self.exchange.create_market_sell_order(symbol, amount)

            return await self._convert_order_result(order, symbol, side, amount)

        except Exception as e:
            return OrderResult(
                order_id="",
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
        """Create limit order on live exchange"""
        try:
            if side == OrderSide.BUY:
                order = await self.exchange.create_limit_buy_order(
                    symbol, amount, price
                )
            else:
                order = await self.exchange.create_limit_sell_order(
                    symbol, amount, price
                )

            return await self._convert_order_result(order, symbol, side, amount)

        except Exception as e:
            return OrderResult(
                order_id="",
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
        """Fetch order status from live exchange"""
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            return await self._convert_order_result(
                order, symbol, None, order.get("amount", 0)
            )

        except Exception as e:
            return OrderResult(
                order_id=order_id,
                symbol=symbol,
                side=OrderSide.BUY,  # Default
                amount_requested=0.0,
                amount_filled=0.0,
                average_price=0.0,
                total_fee=0.0,
                fills=[],
                status="failed",
                error_message=str(e),
            )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order on live exchange"""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            return True
        except:
            return False

    async def close(self) -> None:
        """Close live exchange connection"""
        if hasattr(self.exchange, "close"):
            await self.exchange.close()

    async def _convert_order_result(
        self, order: Dict, symbol: str, side: Optional[OrderSide], amount: float
    ) -> OrderResult:
        """Convert ccxt order format to OrderResult"""
        order_side = OrderSide(order.get("side", side.value if side else "buy"))
        status = order.get("status", "unknown")

        # Map ccxt status to our format
        if status in ["closed", "filled"]:
            result_status = "filled"
        elif status == "canceled":
            result_status = "cancelled"
        elif order.get("filled", 0) > 0:
            result_status = "partial"
        else:
            result_status = "pending"

        # Create fills from trades if available
        fills = []
        trades = order.get("trades", [])
        for trade in trades:
            fill = FillInfo(
                order_id=order["id"],
                symbol=symbol,
                side=order_side,
                amount=trade.get("amount", 0),
                price=trade.get("price", 0),
                fee=trade.get("fee", {}).get("cost", 0),
                timestamp=trade.get("timestamp", time.time()) / 1000,
                fill_id=trade.get("id", ""),
                trade_id=trade.get("id", ""),
            )
            fills.append(fill)

        return OrderResult(
            order_id=order["id"],
            symbol=symbol,
            side=order_side,
            amount_requested=order.get("amount", amount),
            amount_filled=order.get("filled", 0),
            average_price=order.get("average", order.get("price", 0)),
            total_fee=order.get("fee", {}).get("cost", 0),
            fills=fills,
            status=result_status,
            error_message=order.get("info", {}).get("error"),
        )
