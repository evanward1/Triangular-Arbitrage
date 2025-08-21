# main.py

import asyncio
import os
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import octobot_commons.os_util as os_util
import triangular_arbitrage.detector as detector
import triangular_arbitrage.trade_executor as trade_executor

async def main():
    """
    Main execution function.
    """
    load_dotenv() # Load environment variables from .env file

    benchmark = os_util.parse_boolean_environment_var("IS_BENCHMARKING", "False")
    if benchmark:
        import time
        s = time.perf_counter()

    # --- CONFIGURATION ---
    exchange_name = "coinbase"
    FEE_PERCENTAGE = 0.1
    ignored_symbols = []
    whitelisted_symbols = []
    # --- END CONFIGURATION ---

    print(f"Scanning for opportunities on {exchange_name}...")
    trade_fee = FEE_PERCENTAGE / 100

    # Start the arbitrage detection process.
    opportunity = await detector.run_detection(
        exchange_name,
        trade_fee,
        ignored_symbols=ignored_symbols,
        whitelisted_symbols=whitelisted_symbols
    )

    # If a profitable opportunity is found, ask the user to execute
    if opportunity and opportunity[1] > 0:
        execute_choice = input("Profitable opportunity found. Do you want to attempt to execute this trade? (y/n): ").lower()
        if execute_choice == 'y':
            cycle, profit = opportunity
            
            try:
                initial_amount = float(input(f"Enter the amount of {cycle[0]} to trade: "))
            except ValueError:
                print("Invalid amount. Exiting.")
                return

            # --- Initialize Exchange for Trading ---
            api_key = os.getenv("EXCHANGE_API_KEY")
            api_secret = os.getenv("EXCHANGE_API_SECRET")

            if not api_key or not api_secret:
                print("Error: API_KEY or API_SECRET not found in .env file. Cannot execute trade.")
                return
            
            exchange_class = getattr(ccxt, exchange_name)
            exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
            })

            try:
                # --- PRE-TRADE BALANCE CHECK ---
                print("\nChecking account balance...")
                balances = await exchange.fetch_balance()
                start_currency = cycle[0]
                
                # Use balances['free'] which shows the amount not tied up in open orders
                balance = balances.get('free', {}).get(start_currency, 0.0)

                print(f"Available balance: {balance} {start_currency}")
                if balance < initial_amount:
                    print(f"Error: Insufficient funds. You have {balance} {start_currency}, but the trade requires {initial_amount} {start_currency}.")
                    return

                # If balance is sufficient, proceed to execute the cycle
                await trade_executor.execute_cycle(exchange, cycle, initial_amount)
            finally:
                await exchange.close()

    if benchmark:
        elapsed = time.perf_counter() - s
        print(f"\n{__file__} executed in {elapsed:0.2f} seconds.")


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
