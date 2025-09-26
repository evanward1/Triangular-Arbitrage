from .base_adapter import ExchangeAdapter, FillInfo, OrderResult
from .paper_exchange import PaperExchange
from .backtest_exchange import BacktestExchange
from ..constants import OrderSide, OrderType
from typing import Dict, Any, Optional
import asyncio


class LiveExchangeAdapter(ExchangeAdapter):
    """
    Concrete live exchange adapter implementation for testing.
    Wraps a live exchange instance and delegates calls.
    """

    def __init__(self, live_exchange, config: Dict[str, Any]):
        super().__init__(config)
        self.live_exchange = live_exchange
        self._markets = {}

    async def initialize(self) -> None:
        """Initialize the adapter."""
        if hasattr(self.live_exchange, 'load_markets'):
            await self.live_exchange.load_markets()

    async def close(self) -> None:
        """Close the adapter."""
        if hasattr(self.live_exchange, 'close'):
            await self.live_exchange.close()

    async def load_markets(self) -> Dict[str, Any]:
        """Load market data."""
        if hasattr(self.live_exchange, 'load_markets'):
            self._markets = await self.live_exchange.load_markets()
        return self._markets

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch ticker data."""
        if hasattr(self.live_exchange, 'fetch_ticker'):
            return await self.live_exchange.fetch_ticker(symbol)
        return {"symbol": symbol, "last": 0.0, "bid": 0.0, "ask": 0.0}

    async def fetch_balance(self) -> Dict[str, float]:
        """Fetch account balance."""
        if hasattr(self.live_exchange, 'fetch_balance'):
            balance = await self.live_exchange.fetch_balance()
            return balance.get('total', {})
        return {}

    async def create_market_order(self, symbol: str, side: OrderSide, amount: float) -> OrderResult:
        """Create a market order."""
        if hasattr(self.live_exchange, 'create_market_order'):
            result = await self.live_exchange.create_market_order(symbol, side.value, amount)
            # Create fill info from trades
            fills = []
            if 'trades' in result:
                for trade in result['trades']:
                    fills.append(FillInfo(
                        order_id=result.get('id', 'test_order'),
                        symbol=symbol,
                        side=side,
                        amount=trade.get('amount', 0.0),
                        price=trade.get('price', 100.0),
                        fee=trade.get('fee', {}).get('cost', 0.0) if isinstance(trade.get('fee'), dict) else 0.0,
                        timestamp=trade.get('timestamp', 0),
                        fill_id=trade.get('id', 'test_fill')
                    ))

            return OrderResult(
                order_id=result.get('id', 'test_order'),
                symbol=symbol,
                side=side,
                amount_requested=amount,
                amount_filled=result.get('filled', amount),
                average_price=result.get('average', 100.0),
                total_fee=sum(fill.fee for fill in fills),
                fills=fills,
                status='filled' if result.get('status') == 'closed' else result.get('status', 'filled'),
                error_message=None
            )
        # Mock response for testing
        return OrderResult(
            order_id='mock_order',
            symbol=symbol,
            side=side,
            amount_requested=amount,
            amount_filled=amount,
            average_price=100.0,
            total_fee=0.0,
            fills=[],
            status='filled',
            error_message=None
        )

    async def create_limit_order(self, symbol: str, side: OrderSide, amount: float, price: float) -> FillInfo:
        """Create a limit order."""
        if hasattr(self.live_exchange, 'create_limit_order'):
            result = await self.live_exchange.create_limit_order(symbol, side.value, amount, price)
            return FillInfo(
                order_id=result.get('id', 'test_order'),
                symbol=symbol,
                side=side,
                amount_requested=amount,
                amount_filled=result.get('filled', amount),
                avg_price=result.get('average', price),
                status=result.get('status', 'filled'),
                timestamp=result.get('timestamp', 0),
                fills=[]
            )
        # Mock response for testing
        return FillInfo(
            order_id='mock_order',
            symbol=symbol,
            side=side,
            amount_requested=amount,
            amount_filled=amount,
            avg_price=price,
            status='filled',
            timestamp=0,
            fills=[]
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        if hasattr(self.live_exchange, 'cancel_order'):
            result = await self.live_exchange.cancel_order(order_id, symbol)
            return result.get('status') == 'canceled'
        return True

    async def fetch_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch order status."""
        if hasattr(self.live_exchange, 'fetch_order'):
            return await self.live_exchange.fetch_order(order_id, symbol)
        return {"id": order_id, "status": "filled"}


__all__ = ["ExchangeAdapter", "FillInfo", "PaperExchange", "BacktestExchange", "LiveExchangeAdapter", "OrderSide", "OrderType"]
