#!/usr/bin/env python3
"""
Cross-Exchange Arbitrage Bot
Buy low on one exchange, sell high on another
"""

import asyncio
import logging
import os
import time
from typing import Dict, List

import ccxt
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()


class CrossExchangeArbitrage:
    # Exchange fee structures
    FEES = {
        "binanceus": {"maker": 0.001, "taker": 0.001},  # 0.10%
        "kraken": {"maker": 0.0016, "taker": 0.0026},  # 0.16%/0.26%
        "coinbase": {"maker": 0.004, "taker": 0.006},  # 0.40%/0.60%
    }

    # Withdrawal fees (approximate, in USD equivalent)
    WITHDRAWAL_FEES = {
        "BTC": 0.0005,  # ~$30 at $60k
        "ETH": 0.003,  # ~$10 at $3.3k
        "SOL": 0.01,  # ~$2 at $200
        "USDT": 20,  # $20 flat
        "USDC": 20,  # $20 flat
    }

    def __init__(self, trading_mode: str = "paper"):
        """Initialize cross-exchange arbitrage system"""
        self.trading_mode = trading_mode
        self.exchanges = {}
        self.min_profit_threshold = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.5"))
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "1000"))

        # Track trading pairs to monitor
        self.trading_pairs = [
            "BTC/USD",
            "BTC/USDT",
            "ETH/USD",
            "ETH/USDT",
            "SOL/USD",
            "SOL/USDT",
        ]

        self._setup_exchanges()

    def _setup_exchanges(self):
        """Setup multiple exchange connections"""
        exchange_configs = {
            "binanceus": {
                "class": ccxt.binanceus,
                "api_key": os.getenv("BINANCEUS_API_KEY"),
                "secret": os.getenv("BINANCEUS_SECRET"),
            },
            "kraken": {
                "class": ccxt.kraken,
                "api_key": os.getenv("KRAKEN_API_KEY"),
                "secret": os.getenv("KRAKEN_SECRET"),
            },
            "coinbase": {
                "class": ccxt.coinbasepro,
                "api_key": os.getenv("COINBASE_API_KEY"),
                "secret": os.getenv("COINBASE_SECRET"),
                "password": os.getenv("COINBASE_PASSPHRASE"),
            },
        }

        for name, config in exchange_configs.items():
            try:
                exchange_class = config["class"]
                params = {
                    "enableRateLimit": True,
                    "sandbox": False,
                }

                if config.get("api_key"):
                    params["apiKey"] = config["api_key"]
                    params["secret"] = config["secret"]
                    if "password" in config:
                        params["password"] = config["password"]

                self.exchanges[name] = exchange_class(params)
                logger.info(f"✅ {name.upper()} connected")
            except Exception as e:
                logger.error(f"❌ Failed to setup {name}: {e}")

    async def fetch_prices(self) -> Dict[str, Dict[str, float]]:
        """Fetch current prices from all exchanges"""
        prices = {}

        for exchange_name, exchange in self.exchanges.items():
            try:
                tickers = exchange.fetch_tickers()
                prices[exchange_name] = {}

                for symbol in self.trading_pairs:
                    if symbol in tickers:
                        ticker = tickers[symbol]
                        prices[exchange_name][symbol] = {
                            "bid": ticker.get("bid"),
                            "ask": ticker.get("ask"),
                            "last": ticker.get("last"),
                        }
            except Exception as e:
                logger.error(f"❌ Failed to fetch prices from {exchange_name}: {e}")

        return prices

    def calculate_arbitrage_profit(
        self,
        symbol: str,
        buy_exchange: str,
        sell_exchange: str,
        buy_price: float,
        sell_price: float,
        amount_usd: float,
    ) -> Dict:
        """Calculate potential profit from arbitrage opportunity"""

        # Get base currency (BTC, ETH, etc)
        base_currency = symbol.split("/")[0]

        # Calculate fees
        buy_fee_rate = self.FEES[buy_exchange]["taker"]
        sell_fee_rate = self.FEES[sell_exchange]["taker"]

        # Calculate amount in base currency
        amount_base = amount_usd / buy_price

        # Buy cost (including fee)
        buy_cost = amount_usd * (1 + buy_fee_rate)

        # Sell revenue (after fee)
        sell_revenue = (amount_base * sell_price) * (1 - sell_fee_rate)

        # Withdrawal fee in USD
        withdrawal_fee_usd = self.WITHDRAWAL_FEES.get(base_currency, 0) * buy_price

        # Net profit
        gross_profit = sell_revenue - buy_cost
        net_profit = gross_profit - withdrawal_fee_usd
        profit_percent = (net_profit / buy_cost) * 100

        return {
            "symbol": symbol,
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "amount_usd": amount_usd,
            "amount_base": amount_base,
            "buy_cost": buy_cost,
            "sell_revenue": sell_revenue,
            "gross_profit": gross_profit,
            "withdrawal_fee": withdrawal_fee_usd,
            "net_profit": net_profit,
            "profit_percent": profit_percent,
            "profitable": net_profit > 0 and profit_percent > self.min_profit_threshold,
        }

    def find_arbitrage_opportunities(self, prices: Dict) -> List[Dict]:
        """Find profitable arbitrage opportunities across exchanges"""
        opportunities = []

        # Compare prices across all exchange pairs
        for symbol in self.trading_pairs:
            for buy_exchange in self.exchanges.keys():
                if symbol not in prices.get(buy_exchange, {}):
                    continue

                buy_price = prices[buy_exchange][symbol]["ask"]
                if not buy_price:
                    continue

                for sell_exchange in self.exchanges.keys():
                    if buy_exchange == sell_exchange:
                        continue

                    if symbol not in prices.get(sell_exchange, {}):
                        continue

                    sell_price = prices[sell_exchange][symbol]["bid"]
                    if not sell_price:
                        continue

                    # Calculate potential profit
                    profit = self.calculate_arbitrage_profit(
                        symbol=symbol,
                        buy_exchange=buy_exchange,
                        sell_exchange=sell_exchange,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        amount_usd=self.max_position_size,
                    )

                    if profit["profitable"]:
                        opportunities.append(profit)

        # Sort by profit percentage
        opportunities.sort(key=lambda x: x["profit_percent"], reverse=True)
        return opportunities

    async def execute_arbitrage(self, opportunity: Dict) -> Dict:
        """Execute arbitrage trade"""
        logger.info("\n" + "=" * 60)
        logger.info("🎯 EXECUTING ARBITRAGE")
        logger.info("=" * 60)
        logger.info(f"Symbol: {opportunity['symbol']}")
        logger.info(
            f"Buy:  {opportunity['buy_exchange'].upper()} @ ${opportunity['buy_price']:.2f}"
        )
        logger.info(
            f"Sell: {opportunity['sell_exchange'].upper()} @ ${opportunity['sell_price']:.2f}"
        )
        logger.info(
            f"Amount: {opportunity['amount_base']:.6f} ({opportunity['amount_usd']:.2f} USD)"
        )
        logger.info(
            f"Expected profit: ${opportunity['net_profit']:.2f} ({opportunity['profit_percent']:.2f}%)"
        )

        if self.trading_mode == "paper":
            logger.info("📝 PAPER TRADE - No actual execution")
            return {"success": True, "mode": "paper"}

        # Real execution
        try:
            buy_exchange = self.exchanges[opportunity["buy_exchange"]]
            sell_exchange = self.exchanges[opportunity["sell_exchange"]]

            # Place buy order
            logger.info(f"🛒 Buying on {opportunity['buy_exchange']}...")
            buy_order = buy_exchange.create_market_buy_order(
                opportunity["symbol"], opportunity["amount_base"]
            )
            logger.info(f"✅ Buy order: {buy_order['id']}")

            # Place sell order
            logger.info(f"💰 Selling on {opportunity['sell_exchange']}...")
            sell_order = sell_exchange.create_market_sell_order(
                opportunity["symbol"], opportunity["amount_base"]
            )
            logger.info(f"✅ Sell order: {sell_order['id']}")

            logger.info("✅ Arbitrage executed successfully!")
            return {
                "success": True,
                "buy_order": buy_order,
                "sell_order": sell_order,
            }

        except Exception as e:
            logger.error(f"❌ Execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def run_monitor(self, duration_minutes: int = 60):
        """Monitor markets for arbitrage opportunities"""
        logger.info("\n" + "=" * 60)
        logger.info("🚀 CROSS-EXCHANGE ARBITRAGE BOT")
        logger.info("=" * 60)
        logger.info(f"Mode: {self.trading_mode.upper()}")
        logger.info(
            f"Exchanges: {', '.join([e.upper() for e in self.exchanges.keys()])}"
        )
        logger.info(f"Pairs: {', '.join(self.trading_pairs)}")
        logger.info(f"Min profit: {self.min_profit_threshold}%")
        logger.info(f"Max position: ${self.max_position_size}")
        logger.info(f"Duration: {duration_minutes} minutes")
        logger.info(f"{'='*60}\n")

        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        scan_count = 0
        opportunities_found = 0
        opportunities_executed = 0

        try:
            while time.time() < end_time:
                scan_count += 1
                elapsed = time.time() - start_time

                # Fetch prices
                prices = await self.fetch_prices()

                # Find opportunities
                opportunities = self.find_arbitrage_opportunities(prices)

                if opportunities:
                    opportunities_found += len(opportunities)
                    logger.info(
                        f"\n⚡ Scan #{scan_count} ({elapsed:.0f}s): Found {len(opportunities)} opportunities"
                    )

                    # Display top 3
                    for i, opp in enumerate(opportunities[:3], 1):
                        logger.info(
                            f"  {i}. {opp['symbol']}: Buy {opp['buy_exchange']} @ ${opp['buy_price']:.2f}, "
                            f"Sell {opp['sell_exchange']} @ ${opp['sell_price']:.2f} = "
                            f"${opp['net_profit']:.2f} ({opp['profit_percent']:.2f}%)"
                        )

                    # Execute best opportunity
                    if (
                        self.trading_mode == "live" or True
                    ):  # Always show execution in paper mode
                        best = opportunities[0]
                        result = await self.execute_arbitrage(best)
                        if result["success"]:
                            opportunities_executed += 1
                else:
                    print(
                        f"❌ Scan #{scan_count} ({elapsed:.0f}s): No opportunities",
                        end="\r",
                    )

                # Wait before next scan
                await asyncio.sleep(5)

        except KeyboardInterrupt:
            logger.info("\n🛑 Stopped by user")

        # Summary
        elapsed_total = time.time() - start_time
        logger.info("\n" + "=" * 60)
        logger.info("📊 SESSION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Runtime: {elapsed_total/60:.1f} minutes")
        logger.info(f"Scans: {scan_count}")
        logger.info(f"Opportunities found: {opportunities_found}")
        logger.info(f"Opportunities executed: {opportunities_executed}")
        if scan_count > 0:
            logger.info(
                f"Opportunity rate: {opportunities_found/scan_count*100:.1f}% of scans"
            )
        logger.info(f"{'='*60}")


async def main():
    """Main entry point"""
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "paper"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    bot = CrossExchangeArbitrage(trading_mode=mode)
    await bot.run_monitor(duration_minutes=duration)


if __name__ == "__main__":
    asyncio.run(main())
