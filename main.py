# main.py

import asyncio
import os
import sys # Import sys to read command-line arguments
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import octobot_commons.os_util as os_util
import triangular_arbitrage.detector as detector
import triangular_arbitrage.trade_executor as trade_executor

async def show_wallet_balance(exchange):
    """
    Fetches and displays a detailed breakdown of the user's wallet,
    including balances and deposit addresses.
    """
    try:
        print("\nFetching wallet details...")
        balances = await exchange.fetch_balance()
        
        total_balances = balances.get('total', {})
        non_zero_assets = [
            asset for asset, total in total_balances.items() if total > 0
        ]

        if not non_zero_assets:
            print("You have no assets with a positive balance.")
            return

        print("\n--- Your Wallet Details ---")
        for asset in sorted(non_zero_assets):
            total = total_balances.get(asset, 0.0)
            free = balances.get('free', {}).get(asset, 0.0)
            used = balances.get('used', {}).get(asset, 0.0)
            
            print("-" * 40)
            print(f"Asset:            {asset}")
            print(f"  Total Balance:    {total:.8f}")
            print(f"  Available:        {free:.8f}")
            print(f"  In Open Orders:   {used:.8f}")

            # --- THIS IS THE PART THAT GETS YOUR PUBLIC ADDRESS ---
            try:
                # 1. Ask the exchange for the deposit address for this specific asset.
                address_info = await exchange.fetch_deposit_address(asset)
                
                if address_info and 'address' in address_info:
                    # 2. Print the public address it returns.
                    print(f"  Deposit Address:  {address_info['address']}")
                    
                    # 3. Also print the memo/tag if one is required for the deposit.
                    if 'tag' in address_info and address_info['tag']:
                        print(f"  -> Required Memo:  {address_info['tag']}")
                else:
                     print("  Deposit Address:  Not available")
            except Exception:
                # This handles cases where an address doesn't apply (like for USD).
                print("  Deposit Address:  N/A (e.g., Fiat)")
        
        print("-" * 40 + "\n")

    except Exception as e:
        print(f"An error occurred while fetching wallet details: {e}")


async def main():
    """
    Main execution function.
    """
    load_dotenv() # Load environment variables from .env file

    # --- Initialize Exchange for Wallet or Trading ---
    exchange_name = "coinbase"
    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")

    if not api_key or not api_secret:
        print("Error: EXCHANGE_API_KEY or EXCHANGE_API_SECRET not found in .env file.")
        return
    
    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
    })

    try:
        # Check for the --wallet flag
        if "--wallet" in sys.argv:
            await show_wallet_balance(exchange)
            return

        # --- ARBITRAGE DETECTION LOGIC ---
        benchmark = os_util.parse_boolean_environment_var("IS_BENCHMARKING", "False")
        if benchmark:
            import time
            s = time.perf_counter()

        # --- CONFIGURATION ---
        FEE_PERCENTAGE = 0.1
        ignored_symbols = []
        whitelisted_symbols = []
        # --- END CONFIGURATION ---

        print(f"Scanning for opportunities on {exchange_name}...")
        trade_fee = FEE_PERCENTAGE / 100

        opportunity = await detector.run_detection(
            exchange_name,
            trade_fee,
            ignored_symbols=ignored_symbols,
            whitelisted_symbols=whitelisted_symbols
        )

        if opportunity and opportunity[1] > 0:
            execute_choice = input("Profitable opportunity found. Do you want to attempt to execute this trade? (y/n): ").lower()
            if execute_choice == 'y':
                cycle, profit = opportunity
                
                try:
                    initial_amount = float(input(f"Enter the amount of {cycle[0]} to trade: "))
                except ValueError:
                    print("Invalid amount. Exiting.")
                    return

                print("\nChecking account balance...")
                balances = await exchange.fetch_balance()
                start_currency = cycle[0]
                balance = balances.get('free', {}).get(start_currency, 0.0)

                print(f"Available balance: {balance} {start_currency}")
                if balance < initial_amount:
                    print(f"Error: Insufficient funds. You have {balance} {start_currency}, but the trade requires {initial_amount} {start_currency}.")
                    return

                await trade_executor.execute_cycle(exchange, cycle, initial_amount)

        if benchmark:
            elapsed = time.perf_counter() - s
            print(f"\n{__file__} executed in {elapsed:0.2f} seconds.")
            
    finally:
        await exchange.close() # Ensure the connection is always closed


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
