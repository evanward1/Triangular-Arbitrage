#!/usr/bin/env python3
"""
Main Entry Point for Triangular Arbitrage Trading System.

This is the primary executable for running triangular arbitrage detection and
execution. It provides an interactive interface for wallet management, opportunity
detection, and trade execution with comprehensive error handling and logging.

Key Features:
    - Real-time wallet balance display with deposit addresses
    - Interactive arbitrage opportunity detection
    - Manual trade execution with profit calculations
    - Integration with multiple exchange APIs
    - Comprehensive error handling and user guidance

Usage:
    python main.py

The program will prompt for exchange credentials and provide an interactive
menu for various trading operations.
"""

import asyncio
import os
import sys
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

            try:
                address_info = await exchange.fetch_deposit_address(asset)
                if address_info and 'address' in address_info:
                    print(f"  Deposit Address:  {address_info['address']}")
                    if 'tag' in address_info and address_info['tag']:
                        print(f"  -> Required Memo:  {address_info['tag']}")
                else:
                     print("  Deposit Address:  Not available")
            except Exception:
                print("  Deposit Address:  N/A (e.g., Fiat)")
        
        print("-" * 40 + "\n")

    except Exception as e:
        print(f"An error occurred while fetching wallet details: {e}")


async def main():
    """
    Main execution function.
    """
    load_dotenv()

    exchange_name = "coinbase"
    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")
    is_dry_run = "--dry-run" in sys.argv

    if not api_key or not api_secret:
        print("Error: EXCHANGE_API_KEY or EXCHANGE_API_SECRET not found in .env file.")
        return
    
    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {
            'createMarketBuyOrderRequiresPrice': False
        }
    })

    try:
        if "--wallet" in sys.argv:
            await show_wallet_balance(exchange)
            return

        benchmark = os_util.parse_boolean_environment_var("IS_BENCHMARKING", "False")
        if benchmark:
            import time
            s = time.perf_counter()

        # --- CONFIGURATION ---
        FEE_PERCENTAGE = 0.1
        ignored_symbols = []
        
        # *** THIS IS THE FIX ***
        # Only consider trading pairs where the quote currency is one we can actually hold and trade.
        # This prevents errors with restricted fiat currencies like GBP, EUR, etc.
        whitelisted_symbols = ["USDC", "USD"]
        # --- END CONFIGURATION ---

        print(f"Scanning for opportunities on {exchange_name}...")
        
        owned_assets = None
        balances = {}
        
        if "--actionable" in sys.argv:
            print("  -> Actionable mode: Checking your available assets...")
            balances = await exchange.fetch_balance()
            owned_assets = [
                asset for asset, free_balance in balances.get('free', {}).items() if free_balance > 0.000001
            ]
            if not owned_assets:
                print("  -> You have no assets available to trade. Exiting.")
                return
            print(f"  -> Found available assets: {', '.join(owned_assets)}")

        trade_fee = FEE_PERCENTAGE / 100

        opportunity = await detector.run_detection(
            exchange_name,
            trade_fee,
            owned_assets=owned_assets,
            ignored_symbols=ignored_symbols,
            whitelisted_symbols=whitelisted_symbols
        )
        
        if opportunity and (opportunity[1] > 0 or is_dry_run):
            prompt_message = "Found an opportunity. Do you want to simulate/execute it? (y/n): "
            execute_choice = input(prompt_message).lower()
            
            if execute_choice == 'y':
                cycle, profit = opportunity
                start_currency = cycle[0]
                
                if not owned_assets:
                    print("\nChecking account balance for starting currency...")
                    balances = await exchange.fetch_balance()

                available_balance = balances.get('free', {}).get(start_currency, 0.0)
                
                if available_balance <= 0 and is_dry_run:
                    print(f"'{start_currency}' not in wallet or balance is zero. Simulating with a balance of 100 for dry run purposes.")
                    available_balance = 100.0

                if available_balance <= 0:
                    print(f"Error: You have no available {start_currency} to trade.")
                    return

                print(f"\nYou have {available_balance:.8f} {start_currency} available.")
                
                try:
                    amount_str = input(f"Enter amount of {start_currency} to trade (or press Enter to use all): ")
                    initial_amount = float(amount_str) if amount_str else available_balance
                except ValueError:
                    print("Invalid amount. Exiting.")
                    return

                if initial_amount > available_balance:
                    print(f"Error: Insufficient funds. You only have {available_balance} {start_currency} available.")
                    return

                await trade_executor.execute_cycle(exchange, cycle, initial_amount, is_dry_run)

        if benchmark:
            elapsed = time.perf_counter() - s
            print(f"\n{__file__} executed in {elapsed:0.2f} seconds.")
            
    finally:
        await exchange.close()


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())