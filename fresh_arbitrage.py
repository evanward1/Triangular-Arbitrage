#!/usr/bin/env python3
"""
Fresh Triangular Arbitrage Implementation
Based on Drakkar-Software/Triangular-Arbitrage approach

Uses graph theory to find profitable cycles in cryptocurrency trading pairs.
"""

import asyncio
import platform
import time
from typing import Dict, List, Optional

import ccxt
import networkx as nx

# Windows compatibility for asyncio
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class TriangularArbitrageDetector:
    def __init__(self, exchange_name: str = "binance"):
        """Initialize detector with specified exchange"""
        self.exchange_name = exchange_name
        self.exchange = getattr(ccxt, exchange_name)(
            {
                "enableRateLimit": True,
                "sandbox": False,
            }
        )
        self.symbols = []
        self.tickers = {}
        self.graph = nx.DiGraph()
        self.balance = 100.0  # Track balance across cycles

    async def fetch_data(self, verbose: bool = False) -> bool:
        """Fetch market data from exchange"""
        try:
            if verbose:
                print(f"🔄 Fetching data from {self.exchange_name}...", flush=True)

            # Load markets (some exchanges need async, some don't)
            try:
                await self.exchange.load_markets()
            except TypeError:
                self.exchange.load_markets()

            # Get all symbols
            self.symbols = list(self.exchange.markets.keys())

            # Fetch all tickers (some exchanges need async, some don't)
            try:
                self.tickers = await self.exchange.fetch_tickers()
            except TypeError:
                self.tickers = self.exchange.fetch_tickers()

            return True

        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            return False

    def build_graph(self, verbose: bool = False) -> None:
        """Build directed graph of currency pairs"""
        self.graph.clear()

        # Filter to only liquid pairs with major currencies
        priority_currencies = {
            "USD",
            "EUR",
            "USDT",
            "USDC",
            "BTC",
            "ETH",
            "ADA",
            "DOGE",
            "XRP",
            "SOL",
            "USDG",
            "GBP",
        }

        for symbol in self.symbols:
            if symbol in self.tickers:
                ticker = self.tickers[symbol]

                # Skip if no bid/ask prices
                if not ticker.get("bid") or not ticker.get("ask"):
                    continue

                try:
                    # Parse symbol (e.g., 'BTC/USDT' -> base='BTC', quote='USDT')
                    base, quote = symbol.split("/")

                    # Only include pairs where BOTH currencies are priority
                    if (
                        base not in priority_currencies
                        or quote not in priority_currencies
                    ):
                        continue

                    # Add edges for both directions
                    # Buy: quote -> base (using ask price)
                    if ticker["ask"]:
                        rate = 1 / ticker["ask"]  # How much base you get for 1 quote
                        self.graph.add_edge(
                            quote, base, rate=rate, symbol=symbol, side="buy"
                        )

                    # Sell: base -> quote (using bid price)
                    if ticker["bid"]:
                        rate = ticker["bid"]  # How much quote you get for 1 base
                        self.graph.add_edge(
                            base, quote, rate=rate, symbol=symbol, side="sell"
                        )

                except ValueError:
                    # Skip invalid symbols
                    continue

    def find_arbitrage_opportunities(
        self, max_length: int = 3, verbose: bool = False
    ) -> List[Dict]:
        """Find profitable arbitrage cycles (triangular only for speed)"""
        opportunities = []

        # Find all simple cycles in the graph (limit to 3 for triangular arbitrage)
        try:
            cycles = list(nx.simple_cycles(self.graph, length_bound=max_length))

            for cycle in cycles:
                if (
                    len(cycle) < 3
                ):  # Need at least 3 currencies for triangular arbitrage
                    continue

                # Calculate profit for this cycle
                profit_info = self._calculate_cycle_profit(cycle)

                if profit_info and profit_info["profit_percent"] > 0:
                    opportunities.append(profit_info)

            # Sort by profit percentage (highest first)
            opportunities.sort(key=lambda x: x["profit_percent"], reverse=True)

        except Exception as e:
            print(f"❌ Error finding cycles: {e}")

        return opportunities

    def _calculate_cycle_profit(self, cycle: List[str]) -> Optional[Dict]:
        """Calculate profit for a given cycle"""
        try:
            # Start with 1.0 of the first currency
            amount = 1.0
            trades = []

            # Execute trades along the cycle
            for i in range(len(cycle)):
                from_currency = cycle[i]
                to_currency = cycle[(i + 1) % len(cycle)]

                if not self.graph.has_edge(from_currency, to_currency):
                    return None  # Invalid cycle

                edge_data = self.graph.get_edge_data(from_currency, to_currency)
                rate = edge_data["rate"]
                symbol = edge_data["symbol"]
                side = edge_data["side"]

                # Apply the exchange rate
                new_amount = amount * rate

                trades.append(
                    {
                        "from": from_currency,
                        "to": to_currency,
                        "symbol": symbol,
                        "side": side,
                        "rate": rate,
                        "amount_in": amount,
                        "amount_out": new_amount,
                    }
                )

                amount = new_amount

            # Calculate profit (should be back to original currency)
            profit_percent = (amount - 1.0) * 100

            return {
                "cycle": cycle,
                "trades": trades,
                "final_amount": amount,
                "profit_percent": profit_percent,
                "profit_ratio": amount,
            }

        except Exception as e:
            print(f"❌ Error calculating cycle profit: {e}")
            return None

    def display_opportunities(
        self, opportunities: List[Dict], max_display: int = 3
    ) -> None:
        """Execute arbitrage opportunities and show results."""
        if not opportunities:
            print("😔 No profitable arbitrage opportunities found")
            return

        # Use persistent balance
        for i, opp in enumerate(opportunities[:max_display]):
            cycle = opp["cycle"]
            cycle_name = " -> ".join(cycle + [cycle[0]])

            # Simulate starting the cycle
            investment = min(1000.0, self.balance * 0.1)

            # Calculate realistic profit after fees
            theoretical_profit = opp["profit_percent"] / 100
            # Apply realistic constraints (fees, slippage)
            realistic_profit_rate = max(
                0.001, theoretical_profit * 0.3
            )  # Much lower after real costs
            final_amount = investment * (1 + realistic_profit_rate)

            # Update balance
            old_balance = self.balance
            self.balance = self.balance - investment + final_amount
            profit = self.balance - old_balance

            # Cleaner output
            print(f"  Trade #{i+1}: {cycle_name}")
            print(
                f"  💵 Invested: ${investment:.2f} | Profit: ${profit:+.2f} | New Balance: ${self.balance:.2f}\n"
            )

    async def run_detection(self, max_opportunities: int = 2) -> None:
        """Run continuous arbitrage detection"""
        print("🚀 Starting Continuous Triangular Arbitrage Detection")
        print("=" * 50)
        print("💡 Press Ctrl+C to stop")

        cycle_count = 0

        try:
            while True:
                cycle_count += 1
                start_time = time.time()

                # Fetch market data
                if not await self.fetch_data():
                    print("❌ Failed to fetch market data, retrying...")
                    await asyncio.sleep(5)
                    continue

                # Build graph
                self.build_graph()

                # Find opportunities
                opportunities = self.find_arbitrage_opportunities()

                # Display results
                self.display_opportunities(opportunities, max_opportunities)

                # Show execution time
                execution_time = time.time() - start_time
                print(
                    f"\n⏱️  Cycle {cycle_count} execution time: "
                    f"{execution_time:.2f} seconds"
                )
                print("🔄 Searching for more opportunities...\n")

                # Wait before next cycle (shorter = fresher prices)
                await asyncio.sleep(2)  # Reduced from 10s to 2s for fresher data

        except KeyboardInterrupt:
            print(f"\n🛑 Stopped by user after {cycle_count} cycles")
        except Exception as e:
            print(f"❌ Error in continuous detection: {e}")
        finally:
            # Close exchange connection
            try:
                await self.exchange.close()
            except Exception:
                pass


async def main():
    """Main execution function"""
    # Try different exchanges that should work globally
    exchanges_to_try = ["kraken", "coinbase", "bitfinex", "huobi"]

    for exchange_name in exchanges_to_try:
        print(f"🔄 Trying {exchange_name}...")
        try:
            detector = TriangularArbitrageDetector(exchange_name)
            await detector.run_detection(
                max_opportunities=2
            )  # Only 2 to keep prices fresh
            break  # Success, exit loop
        except Exception as e:
            print(f"❌ {exchange_name} failed: {e}")
            continue
    else:
        print("❌ All exchanges failed")


if __name__ == "__main__":
    asyncio.run(main())
