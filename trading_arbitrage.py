#!/usr/bin/env python3
"""
Real Trading Triangular Arbitrage Implementation
WARNING: This trades with real money. Use at your own risk.
"""

import asyncio
import logging
import os
import platform
import time
from typing import Dict, List, Optional

import ccxt
import networkx as nx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Windows compatibility
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class RealTriangularArbitrage:
    def __init__(self, exchange_name: str = "kraken", trading_mode: str = "paper"):
        """Initialize real trading arbitrage system"""
        self.exchange_name = exchange_name
        self.trading_mode = trading_mode  # 'paper' or 'live'
        self.exchange = None
        self.symbols = []
        self.tickers = {}
        self.graph = nx.DiGraph()
        self.balances = {}

        # Safety limits
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "100"))
        self.min_profit_threshold = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.5"))

        self._setup_exchange()

    def _setup_exchange(self):
        """Setup exchange with API credentials"""
        try:
            if self.exchange_name.lower() == "kraken":
                self.exchange = ccxt.kraken(
                    {
                        "apiKey": os.getenv("KRAKEN_API_KEY"),
                        "secret": os.getenv("KRAKEN_SECRET"),
                        "enableRateLimit": True,
                        "sandbox": self.trading_mode == "paper",
                    }
                )
            elif self.exchange_name.lower() == "binance":
                self.exchange = ccxt.binance(
                    {
                        "apiKey": os.getenv("BINANCE_API_KEY"),
                        "secret": os.getenv("BINANCE_SECRET"),
                        "enableRateLimit": True,
                        "sandbox": self.trading_mode == "paper",
                    }
                )
            elif self.exchange_name.lower() == "coinbase":
                self.exchange = ccxt.coinbasepro(
                    {
                        "apiKey": os.getenv("COINBASE_API_KEY"),
                        "secret": os.getenv("COINBASE_SECRET"),
                        "passphrase": os.getenv("COINBASE_PASSPHRASE"),
                        "enableRateLimit": True,
                        "sandbox": self.trading_mode == "paper",
                    }
                )
            else:
                raise ValueError(f"Unsupported exchange: {self.exchange_name}")

            logger.info(
                f"🔑 Exchange {self.exchange_name} configured in "
                f"{self.trading_mode} mode"
            )

        except Exception as e:
            logger.error(f"❌ Failed to setup exchange: {e}")
            raise

    async def fetch_balances(self) -> Dict:
        """Fetch current account balances"""
        try:
            if self.trading_mode == "paper":
                # Return simulated balances for testing
                return {
                    "USD": {"free": 10000.0, "used": 0.0, "total": 10000.0},
                    "BTC": {"free": 0.0, "used": 0.0, "total": 0.0},
                    "ETH": {"free": 0.0, "used": 0.0, "total": 0.0},
                }

            self.balances = await self.exchange.fetch_balance()
            currency_count = len(
                [k for k, v in self.balances.items() if v.get("total", 0) > 0]
            )
            logger.info(f"💰 Current balances: {currency_count} currencies")
            return self.balances

        except Exception as e:
            logger.error(f"❌ Failed to fetch balances: {e}")
            return {}

    async def execute_trade(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> Dict:
        """Execute a single trade"""
        try:
            if self.trading_mode == "paper":
                # Simulate trade execution
                logger.info(f"📝 PAPER TRADE: {side} {amount} {symbol} @ market price")
                return {
                    "id": f"paper_{int(time.time())}",
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price or 1.0,
                    "status": "closed",
                    "fee": amount * 0.001,  # Simulate 0.1% fee
                }

            # Real trade execution
            logger.info(f"🚀 LIVE TRADE: {side} {amount} {symbol}")

            # Place market order
            order = await self.exchange.create_market_order(
                symbol=symbol, side=side, amount=amount
            )

            logger.info(f"✅ Trade executed: {order['id']}")
            return order

        except Exception as e:
            logger.error(f"❌ Trade failed: {e}")
            return None

    async def execute_arbitrage_cycle(self, cycle: List[str], amount: float) -> Dict:
        """Execute a complete arbitrage cycle"""
        logger.info(f"🔄 Starting arbitrage cycle: {' -> '.join(cycle)}")

        if amount > self.max_position_size:
            logger.warning(
                f"⚠️ Amount {amount} exceeds max position size {self.max_position_size}"
            )
            amount = self.max_position_size

        start_balance = amount
        current_amount = amount
        trades = []

        try:
            for i in range(len(cycle) - 1):
                from_currency = cycle[i]
                to_currency = cycle[i + 1]
                symbol = f"{from_currency}/{to_currency}"

                # Check if pair exists (might need to reverse)
                if symbol not in self.symbols:
                    symbol = f"{to_currency}/{from_currency}"
                    side = "sell"
                else:
                    side = "buy"

                logger.info(
                    f"  Step {i+1}: {from_currency} -> {to_currency} ({current_amount})"
                )

                trade = await self.execute_trade(symbol, side, current_amount)
                if not trade:
                    logger.error(f"❌ Trade failed at step {i+1}")
                    break

                trades.append(trade)

                # Update amount for next trade (subtract fees)
                fee = trade.get("fee", current_amount * 0.001)
                current_amount = trade.get("amount", current_amount) - fee

                # Small delay between trades
                await asyncio.sleep(0.5)

            profit = current_amount - start_balance
            profit_percent = (profit / start_balance) * 100

            logger.info("✅ Cycle completed!")
            logger.info(f"💰 Final amount: {current_amount:.6f}")
            logger.info(f"📈 Profit: {profit:+.6f} ({profit_percent:+.3f}%)")

            return {
                "success": True,
                "start_amount": start_balance,
                "final_amount": current_amount,
                "profit": profit,
                "profit_percent": profit_percent,
                "trades": trades,
            }

        except Exception as e:
            logger.error(f"❌ Arbitrage cycle failed: {e}")
            return {"success": False, "error": str(e)}

    async def find_arbitrage_opportunities(self) -> List[Dict]:
        """Find profitable arbitrage cycles"""
        try:
            # Fetch market data
            await self.exchange.load_markets()
            self.symbols = list(self.exchange.markets.keys())
            self.tickers = await self.exchange.fetch_tickers()

            logger.info(f"📊 Analyzing {len(self.symbols)} trading pairs...")

            # Build price graph
            self.graph.clear()

            for symbol in self.symbols:
                if symbol not in self.tickers:
                    continue

                ticker = self.tickers[symbol]
                base, quote = symbol.split("/")

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

            # Find profitable cycles
            opportunities = []
            currencies = list(self.graph.nodes())

            for start_currency in currencies[:10]:  # Limit search for performance
                try:
                    cycles = nx.simple_cycles(self.graph)
                    for cycle in cycles:
                        if len(cycle) >= 3 and start_currency in cycle:
                            # Calculate cycle profitability
                            profit_ratio = self._calculate_cycle_profit(cycle)
                            if profit_ratio and profit_ratio > (
                                1 + self.min_profit_threshold / 100
                            ):
                                profit_percent = (profit_ratio - 1) * 100
                                opportunities.append(
                                    {
                                        "cycle": cycle,
                                        "profit_percent": profit_percent,
                                        "profit_ratio": profit_ratio,
                                    }
                                )
                except Exception:
                    continue

            # Sort by profitability
            opportunities.sort(key=lambda x: x["profit_percent"], reverse=True)
            logger.info(f"🎯 Found {len(opportunities)} profitable opportunities")

            return opportunities[:5]  # Return top 5

        except Exception as e:
            logger.error(f"❌ Failed to find opportunities: {e}")
            return []

    def _calculate_cycle_profit(self, cycle: List[str]) -> Optional[float]:
        """Calculate expected profit for a trading cycle"""
        try:
            amount = 1.0

            for i in range(len(cycle)):
                from_curr = cycle[i]
                to_curr = cycle[(i + 1) % len(cycle)]

                if self.graph.has_edge(from_curr, to_curr):
                    edge_data = self.graph[from_curr][to_curr]
                    rate = edge_data["rate"]
                    amount *= rate

                    # Apply trading fees (0.1% typical)
                    amount *= 0.999
                else:
                    return None

            return amount

        except Exception:
            return None

    async def run_trading_session(self, max_trades: int = None):
        """Run continuous automated arbitrage trading session"""
        logger.info(f"🚀 Starting continuous trading session ({self.trading_mode} mode)")
        logger.info(f"💰 Max position size: ${self.max_position_size}")
        logger.info(f"📊 Min profit threshold: {self.min_profit_threshold}%")
        logger.info("💡 Press Ctrl+C to stop")

        await self.fetch_balances()

        trade_num = 0
        try:
            while True:
                trade_num += 1
                logger.info(f"\n🔍 Scan {trade_num}")

                opportunities = await self.find_arbitrage_opportunities()

                if not opportunities:
                    logger.info("😔 No profitable opportunities found")
                    logger.info("🔄 Continuing to search...")
                    await asyncio.sleep(10)
                    continue

                best_opportunity = opportunities[0]
                cycle = best_opportunity["cycle"]
                expected_profit = best_opportunity["profit_percent"]

                logger.info(f"🎯 Best opportunity: {' -> '.join(cycle)}")
                logger.info(f"📈 Expected profit: {expected_profit:.3f}%")

                if expected_profit > self.min_profit_threshold:
                    result = await self.execute_arbitrage_cycle(
                        cycle, self.max_position_size
                    )

                    if result.get("success"):
                        logger.info(f"✅ Trade {trade_num} completed successfully!")
                        # Update balances after successful trade
                        await self.fetch_balances()
                    else:
                        logger.error(f"❌ Trade {trade_num} failed")
                else:
                    logger.info(
                        f"⏭️ Skipping - profit {expected_profit:.3f}% below threshold"
                    )

                # Wait before next cycle
                logger.info("🔄 Searching for next opportunity...")
                await asyncio.sleep(15)

        except KeyboardInterrupt:
            logger.info(f"\n🛑 Trading session stopped by user after {trade_num} scans")
        except Exception as e:
            logger.error(f"❌ Trading session error: {e}")

        logger.info("🏁 Trading session completed")


async def main():
    """Main trading function"""
    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()

    trading_mode = os.getenv("TRADING_MODE", "paper")

    if trading_mode == "live":
        print("⚠️ WARNING: LIVE TRADING MODE ENABLED ⚠️")
        print("This will trade with real money!")
        confirmation = input("Type 'YES' to continue: ")
        if confirmation != "YES":
            print("Trading cancelled.")
            return

    exchanges_to_try = ["kraken", "coinbase", "binance"]

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
