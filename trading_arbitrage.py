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
        self.paper_balances = {}  # Track paper trading balances separately

        # Safety limits
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "100"))
        self.min_profit_threshold = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.1"))

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
                        "sandbox": False,  # Always use live data, even in paper mode
                    }
                )
            elif self.exchange_name.lower() == "binance":
                self.exchange = ccxt.binance(
                    {
                        "apiKey": os.getenv("BINANCE_API_KEY"),
                        "secret": os.getenv("BINANCE_SECRET"),
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

            mode_desc = (
                "paper (live prices)" if self.trading_mode == "paper" else "LIVE"
            )
            logger.info(
                f"🔑 Exchange {self.exchange_name} configured in " f"{mode_desc} mode"
            )

        except Exception as e:
            logger.error(f"❌ Failed to setup exchange: {e}")
            raise

    async def fetch_balances(self) -> Dict:
        """Fetch current account balances"""
        try:
            # Fetch real balances from exchange
            self.balances = self.exchange.fetch_balance()

            # In paper mode, initialize paper balances on first fetch
            if self.trading_mode == "paper" and not self.paper_balances:
                self.paper_balances = {}

                # Check if we should use test balances (no tradable balance in priority currencies)
                use_test_balance = True
                priority_test_currencies = ["USDC", "USDG", "EUR", "USDT", "USD"]

                for currency, balance in self.balances.items():
                    if isinstance(balance, dict):
                        total = balance.get("total", 0)
                        normalized_currency = currency.replace(".F", "")

                        if total and total > 0:
                            self.paper_balances[normalized_currency] = {
                                "free": total,
                                "used": 0.0,
                                "total": total,
                            }

                            # Check if we have any meaningful balance in priority currencies
                            if (
                                normalized_currency in priority_test_currencies
                                and total > 1.0
                            ):
                                use_test_balance = False

                # If no meaningful balances found, initialize with test balances (stablecoins + major cryptos)
                if use_test_balance:
                    logger.info(
                        "💰 No tradable balance found, initializing test balances"
                    )
                    self.paper_balances = {}  # Clear any tiny balances
                    test_balances = {
                        "USDT": 100.0,
                        "USDC": 100.0,
                        "BTC": 0.005,
                        "ETH": 0.05,
                        "SOL": 2.0,
                    }
                    for currency, amount in test_balances.items():
                        self.paper_balances[currency] = {
                            "free": amount,
                            "used": 0.0,
                            "total": amount,
                        }

            # Display balances (paper or real)
            display_balances = (
                self.paper_balances if self.trading_mode == "paper" else self.balances
            )
            currency_count = 0
            for currency, balance in display_balances.items():
                if isinstance(balance, dict):
                    total = balance.get("total")
                    if total and total > 0:
                        currency_count += 1
                        logger.info(
                            f"  💵 {currency}: {balance.get('free', 0):.6f} free, {total:.6f} total"
                        )

            logger.info(f"💰 Current balances: {currency_count} currencies")
            return display_balances

        except Exception as e:
            logger.error(f"❌ Failed to fetch balances: {e}")
            return {}

    async def execute_trade(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> Dict:
        """Execute a single trade"""
        try:
            if self.trading_mode == "paper":
                # Simulate trade execution with REAL bid/ask prices
                # Get current market price for this symbol
                if symbol in self.tickers:
                    ticker = self.tickers[symbol]
                    if side == "buy":
                        # When buying, you pay the ASK price (higher)
                        # amount is in quote currency, filled is in base currency
                        execution_price = ticker.get("ask", 1.0)
                        filled_amount = (
                            amount / execution_price if execution_price else amount
                        )
                    else:  # sell
                        # When selling, you receive the BID price (lower)
                        # amount is in base currency, filled is in quote currency
                        execution_price = ticker.get("bid", 1.0)
                        filled_amount = amount * execution_price
                else:
                    execution_price = 1.0
                    filled_amount = amount

                logger.info(
                    f"📝 PAPER TRADE: {side} {amount} {symbol} @ {execution_price}"
                )
                return {
                    "id": f"paper_{int(time.time())}",
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "filled": filled_amount,
                    "price": execution_price,
                    "status": "closed",
                    "fee": {"cost": filled_amount * 0.001},  # 0.1% fee on output
                }

            # Real trade execution
            logger.info(f"🚀 LIVE TRADE: {side} {amount} {symbol}")

            # Place market order
            order = self.exchange.create_market_order(
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

        try:
            for i in range(len(cycle) - 1):
                from_currency = cycle[i]
                to_currency = cycle[i + 1]

                # Determine the correct trading pair and side
                # If we want to go FROM -> TO, we need to either:
                # - Buy TO/FROM (buy TO with FROM)
                # - Sell FROM/TO (sell FROM for TO)

                buy_pair = f"{to_currency}/{from_currency}"  # TO/FROM
                sell_pair = f"{from_currency}/{to_currency}"  # FROM/TO

                if buy_pair in self.symbols:
                    symbol = buy_pair
                    side = "buy"  # Buy TO with FROM
                elif sell_pair in self.symbols:
                    symbol = sell_pair
                    side = "sell"  # Sell FROM for TO
                else:
                    logger.error(
                        f"❌ No trading pair found for {from_currency} -> {to_currency}"
                    )
                    break

                logger.info(
                    f"  Step {i+1}: {from_currency} -> {to_currency} "
                    f"({current_amount} {from_currency}) via {side} {symbol}"
                )

                trade = await self.execute_trade(symbol, side, current_amount)
                if not trade:
                    logger.error(f"❌ Trade failed at step {i+1}")
                    break

                trades.append(trade)

                # Update amount for next trade (subtract fees)
                fee_info = trade.get("fee")
                if fee_info and isinstance(fee_info, dict):
                    fee = fee_info.get("cost", current_amount * 0.001)
                else:
                    fee = current_amount * 0.001  # Default 0.1% fee

                # Get the filled amount from the trade
                filled_amount = trade.get("filled") or trade.get("amount")
                filled_amount = filled_amount or current_amount

                # Ensure values are not None
                if fee is None:
                    fee = 0
                if filled_amount is None:
                    filled_amount = current_amount

                current_amount = float(filled_amount) - float(fee)
                logger.info(
                    f"    Filled: {filled_amount}, Fee: {fee}, Remaining: {current_amount}"
                )

                # Small delay between trades
                await asyncio.sleep(0.5)

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

    async def check_order_book_depth(
        self, symbol: str, side: str, amount: float
    ) -> Dict:
        """Check if there's enough liquidity in the order book for the trade"""
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit=10)

            # For buy orders, check asks (we need to buy from sellers)
            # For sell orders, check bids (we need to sell to buyers)
            orders = order_book["asks"] if side == "buy" else order_book["bids"]

            cumulative_amount = 0.0
            weighted_price = 0.0

            for order_entry in orders:
                # Order book entries can be [price, volume] or [price, volume, timestamp]
                price = order_entry[0]
                volume = order_entry[1]

                if cumulative_amount >= amount:
                    break
                take_amount = min(amount - cumulative_amount, volume)
                weighted_price += price * take_amount
                cumulative_amount += take_amount

            if cumulative_amount < amount:
                return {
                    "sufficient": False,
                    "available": cumulative_amount,
                    "needed": amount,
                    "avg_price": None,
                }

            avg_price = weighted_price / amount
            return {
                "sufficient": True,
                "available": cumulative_amount,
                "needed": amount,
                "avg_price": avg_price,
            }

        except Exception as e:
            logger.error(f"❌ Failed to check order book for {symbol}: {e}")
            return {"sufficient": False, "error": str(e)}

    async def find_arbitrage_opportunities(self) -> List[Dict]:
        """Find profitable arbitrage cycles"""
        try:
            # Fetch market data
            self.exchange.load_markets()
            self.symbols = list(self.exchange.markets.keys())
            self.tickers = self.exchange.fetch_tickers()

            logger.info(f"📊 Analyzing {len(self.symbols)} trading pairs...")

            # Exclude fiat currencies except USD (keep stablecoins, allow USD as bridge)
            fiat_currencies = {"EUR", "GBP", "JPY", "CAD", "AUD", "CHF"}

            # Build price graph
            self.graph.clear()

            for symbol in self.symbols:
                if symbol not in self.tickers:
                    continue

                ticker = self.tickers[symbol]
                base, quote = symbol.split("/")

                # Skip pairs with fiat currencies
                if base in fiat_currencies or quote in fiat_currencies:
                    continue

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
            currencies = list(self.graph.nodes())

            logger.info(
                f"🔍 Checking {len(currencies)} currencies for triangular arbitrage..."
            )

            # Check triangular arbitrage: A -> B -> C -> A
            for curr_a in currencies:
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

            # For cycle [A, B, C, A], we need 3 trades: A->B, B->C, C->A
            # So iterate len(cycle) - 1 times
            for i in range(len(cycle) - 1):
                from_curr = cycle[i]
                to_curr = cycle[i + 1]

                if self.graph.has_edge(from_curr, to_curr):
                    edge_data = self.graph[from_curr][to_curr]
                    rate = edge_data["rate"]
                    amount *= rate

                    # Apply maker fees (0.16% per trade on Kraken for limit orders)
                    # Standard users: 0.26% taker / 0.16% maker
                    # Using limit orders (maker fees) to reduce costs
                    amount *= 0.9984
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
                                logger.info(
                                    f"  ✅ Will trade with: {normalized_currency} ({free_balance:.6f})"
                                )

                if owned_currencies:
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
                        await asyncio.sleep(10)
                        continue
                    opportunities = viable_opportunities

                # Execute ALL profitable opportunities in this scan, not just the best one
                logger.info(f"🎯 Found {len(opportunities)} opportunities to execute")
                executed_count = 0

                for opp_idx, opportunity in enumerate(opportunities):
                    cycle = opportunity["cycle"]
                    expected_profit = opportunity["profit_percent"]

                    logger.info(
                        f"\n📊 Opportunity {opp_idx + 1}/{len(opportunities)}: {' -> '.join(cycle)}"
                    )
                    logger.info(f"📈 Expected profit: {expected_profit:.3f}%")

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

                    if available_balance < self.max_position_size:
                        logger.warning(
                            f"⚠️ Insufficient {start_currency} balance "
                            f"({available_balance:.2f} < {self.max_position_size}), skipping"
                        )
                        continue

                    # Skip order book depth check in paper trading mode
                    if self.trading_mode == "paper":
                        logger.info("📖 Skipping order book depth check (paper trading)")
                    else:
                        # Check order book depth for each trade in the cycle
                        logger.info("📖 Checking order book depth...")
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

                            depth = await self.check_order_book_depth(
                                symbol, side, amount
                            )

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
                                logger.info(
                                    f"  ✅ Step {i+1} "
                                    f"({from_currency}->{to_currency}): "
                                    f"{symbol} has sufficient liquidity "
                                    f"(avg price: {avg_price:.6f}, "
                                    f"slippage: {slippage:.3f}%)"
                                )

                            # Update amount for next step (rough estimate)
                            amount = amount * depth.get("avg_price", 1.0) * 0.999

                        if not depth_check_passed:
                            logger.info(
                                "❌ Skipping opportunity due to insufficient liquidity"
                            )
                            continue

                    if expected_profit > self.min_profit_threshold:
                        result = await self.execute_arbitrage_cycle(
                            cycle, self.max_position_size
                        )

                        if result.get("success"):
                            executed_count += 1
                            logger.info(
                                f"✅ Opportunity {opp_idx + 1} executed successfully!"
                            )
                            # Update balances after successful trade
                            await self.fetch_balances()
                        else:
                            logger.error(f"❌ Opportunity {opp_idx + 1} failed")
                    else:
                        logger.info(
                            f"⏭️ Skipping - profit {expected_profit:.3f}% below threshold"
                        )

                logger.info(
                    f"\n✅ Executed {executed_count}/{len(opportunities)} "
                    f"opportunities in scan {trade_num}"
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
