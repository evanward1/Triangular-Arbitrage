#!/usr/bin/env python3
"""
Coinbase Advanced Trading API Adapter
Provides ccxt-like interface for Coinbase Advanced Trading API
"""
import asyncio
from typing import Dict, List, Any, Optional
from coinbase.rest import RESTClient
from decimal import Decimal
import time
import logging

logger = logging.getLogger(__name__)

class CoinbaseAdvancedAdapter:
    """
    Adapter to make Coinbase Advanced Trading API work like ccxt
    """

    def __init__(self, api_key: str, api_secret: str, sandbox: bool = False):
        self.client = RESTClient(api_key=api_key, api_secret=api_secret)
        self.markets = {}
        self.id = "coinbase_advanced"
        self.sandbox = sandbox

    async def load_markets(self) -> Dict[str, Any]:
        """Load all available markets"""
        try:
            products = self.client.get_products()
            self.markets = {}

            for product in products.products:
                symbol = f"{product.base_currency_id}/{product.quote_currency_id}"
                self.markets[symbol] = {
                    'id': product.product_id,
                    'symbol': symbol,
                    'base': product.base_currency_id,
                    'quote': product.quote_currency_id,
                    'active': product.status == 'online',
                    'type': 'spot',
                    'spot': True,
                    'precision': {
                        'amount': 8,  # Default precision
                        'price': 8
                    },
                    'limits': {
                        'amount': {
                            'min': float(product.base_min_size) if product.base_min_size else 0.001,
                            'max': float(product.base_max_size) if product.base_max_size else None
                        }
                    }
                }

            logger.info(f"Loaded {len(self.markets)} markets from Coinbase Advanced Trading")
            return self.markets

        except Exception as e:
            logger.error(f"Failed to load markets: {e}")
            raise

    async def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balances"""
        try:
            accounts = self.client.get_accounts()
            balance = {'free': {}, 'used': {}, 'total': {}}

            for account in accounts.accounts:
                currency = account.currency
                available = float(account.available_balance.value)
                total = float(account.available_balance.value)  # Coinbase Advanced shows available balance

                balance['free'][currency] = available
                balance['used'][currency] = 0.0  # Not provided in available balance
                balance['total'][currency] = total

            return balance

        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            raise

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch ticker for a symbol"""
        try:
            if symbol not in self.markets:
                raise ValueError(f"Market {symbol} not found")

            product_id = self.markets[symbol]['id']
            ticker = self.client.get_product(product_id)

            return {
                'symbol': symbol,
                'last': float(ticker.price) if ticker.price else None,
                'bid': None,  # Not provided in basic ticker
                'ask': None,  # Not provided in basic ticker
                'timestamp': int(time.time() * 1000),
                'datetime': None
            }

        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            raise

    async def fetch_order_book(self, symbol: str, limit: int = None) -> Dict[str, Any]:
        """Fetch order book for a symbol"""
        try:
            if symbol not in self.markets:
                raise ValueError(f"Market {symbol} not found")

            product_id = self.markets[symbol]['id']
            book = self.client.get_product_book(product_id)

            bids = [[float(bid.price), float(bid.size)] for bid in (book.bids[:limit] if limit else book.bids)]
            asks = [[float(ask.price), float(ask.size)] for ask in (book.asks[:limit] if limit else book.asks)]

            return {
                'symbol': symbol,
                'bids': bids,
                'asks': asks,
                'timestamp': int(time.time() * 1000),
                'datetime': None
            }

        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            raise

    async def create_market_buy_order(self, symbol: str, amount: float, price: float = None) -> Dict[str, Any]:
        """Create a market buy order"""
        try:
            if symbol not in self.markets:
                raise ValueError(f"Market {symbol} not found")

            product_id = self.markets[symbol]['id']

            # For market buy orders, we need to specify the quote currency amount
            order = self.client.market_order_buy(
                product_id=product_id,
                quote_size=str(amount)
            )

            return {
                'id': order.order_id,
                'symbol': symbol,
                'type': 'market',
                'side': 'buy',
                'amount': amount,
                'status': 'pending'
            }

        except Exception as e:
            logger.error(f"Failed to create buy order for {symbol}: {e}")
            raise

    async def create_market_sell_order(self, symbol: str, amount: float, price: float = None) -> Dict[str, Any]:
        """Create a market sell order"""
        try:
            if symbol not in self.markets:
                raise ValueError(f"Market {symbol} not found")

            product_id = self.markets[symbol]['id']

            # For market sell orders, we specify the base currency amount
            order = self.client.market_order_sell(
                product_id=product_id,
                base_size=str(amount)
            )

            return {
                'id': order.order_id,
                'symbol': symbol,
                'type': 'market',
                'side': 'sell',
                'amount': amount,
                'status': 'pending'
            }

        except Exception as e:
            logger.error(f"Failed to create sell order for {symbol}: {e}")
            raise

    async def create_order(self, symbol: str, type_: str, side: str, amount: float, price: float = None) -> Dict[str, Any]:
        """Create an order (unified interface)"""
        if type_ == 'market':
            if side == 'buy':
                return await self.create_market_buy_order(symbol, amount, price)
            else:
                return await self.create_market_sell_order(symbol, amount, price)
        else:
            raise NotImplementedError("Only market orders are supported")

    async def close(self):
        """Close the connection (placeholder for ccxt compatibility)"""
        pass