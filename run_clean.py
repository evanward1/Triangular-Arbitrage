#!/usr/bin/env python3
"""
Simple Clean Arbitrage Runner
Just run: python run_clean.py
"""

import asyncio
import os
import sqlite3
import time

from dotenv import load_dotenv

from fresh_arbitrage import TriangularArbitrageDetector


def clear_database():
    """Clear stuck cycles"""
    try:
        conn = sqlite3.connect("trade_state.db")
        conn.execute("DELETE FROM cycles")
        conn.commit()
        conn.close()
        print("🧹 Database cleared")
    except Exception:
        pass


def run_arbitrage():
    """Run arbitrage with 30-second feedback intervals"""
    import sys

    # Load environment variables
    load_dotenv()

    clear_database()

    print("🚀 Initializing arbitrage trading system...")
    print()

    # Check for command line argument
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        print("Choose trading mode:")
        print("1. 📝 Paper Trading (Simulation - Safe)")
        print("2. 💰 Live Trading (Real Money - Risk)")
        print()
        choice = input("Enter your choice (1 or 2): ").strip()

    if choice == "1":
        trading_mode = "paper"
        print("📝 PAPER TRADING MODE - Simulation only")
    elif choice == "2":
        trading_mode = "live"
        print("⚠️  LIVE TRADING MODE - Using real money!")
        print("🔑 Checking API keys...")

        # Check if API keys are configured
        kraken_key = os.getenv("KRAKEN_API_KEY")
        binance_key = os.getenv("BINANCE_API_KEY")
        coinbase_key = os.getenv("COINBASE_API_KEY")

        if not any([kraken_key, binance_key, coinbase_key]):
            print("❌ No API keys found!")
            print("Please set up your API keys in .env file first.")
            print("See TRADING_SETUP.md for instructions.")
            return

        print("✅ API keys configured")
        print()
        confirmation = input(
            "⚠️  Are you absolutely sure you want to proceed with LIVE "
            "trading? Type 'YES': "
        )
        if confirmation != "YES":
            print("❌ Trading cancelled for safety")
            return
    else:
        print("❌ Invalid choice. Please enter 1 or 2.")
        return

    max_position = os.getenv("MAX_POSITION_SIZE", "100")
    min_profit = os.getenv("MIN_PROFIT_THRESHOLD", "0.5")

    print(f"💰 Max position size: ${max_position}")
    print(f"📊 Min profit threshold: {min_profit}%")
    print("🎯 Monitoring markets for arbitrage opportunities...")
    print("📊 Reporting interval: every 2 seconds\n")

    # Run directly without subprocess
    asyncio.run(run_arbitrage_direct(trading_mode))


async def run_arbitrage_direct(trading_mode):
    """Run arbitrage detection directly"""
    exchanges_to_try = ["kraken", "coinbase", "bitfinex", "huobi"]

    for exchange_name in exchanges_to_try:
        print(f"🔄 Trying {exchange_name}...")
        try:
            detector = TriangularArbitrageDetector(exchange_name)

            # Run continuously
            cycle_count = 0
            start_time = time.time()

            while True:
                cycle_count += 1
                print(f"\n{'='*60}")
                runtime = time.time() - start_time
                print(
                    f"⚡ CYCLE #{cycle_count} | Runtime: {runtime:.0f}s | "
                    f"Balance: ${detector.balance:.2f}"
                )
                print("=" * 60)

                # Fetch data
                if not await detector.fetch_data():
                    print("❌ Failed to fetch data, retrying...")
                    await asyncio.sleep(5)
                    continue

                # Build graph
                detector.build_graph()

                # Find opportunities
                opportunities = detector.find_arbitrage_opportunities()

                # Display top 2
                if opportunities:
                    print(
                        f"✅ Found {len(opportunities)} opportunities | Executing top 2\n"
                    )
                    detector.display_opportunities(opportunities, max_display=2)
                else:
                    print("😔 No profitable opportunities found")

                # Wait 2 seconds
                await asyncio.sleep(2)

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user")
            break
        except Exception as e:
            print(f"❌ {exchange_name} failed: {e}")
            continue


if __name__ == "__main__":
    run_arbitrage()
