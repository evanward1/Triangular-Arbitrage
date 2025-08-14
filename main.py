import asyncio
import os
import ccxt.async_support as ccxt
import octobot_commons.os_util as os_util
import triangular_arbitrage.detector as detector
from dotenv import load_dotenv  # <-- 1. IMPORT THE LIBRARY

load_dotenv()  # <-- 2. LOAD THE .ENV FILE

if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    benchmark = os_util.parse_boolean_environment_var("IS_BENCHMARKING", "False")
    if benchmark:
        import time
        s = time.perf_counter()

    # --- CONFIGURATION ---
    exchange_name = "coinbase"
    FEE_PERCENTAGE = 0.1
    
    # --- API KEY CONFIGURATION ---
    # The script will now load these from your .env file
    api_key = os.environ.get('EXCHANGE_API_KEY')
    api_secret = os.environ.get('EXCHANGE_API_SECRET')

    if not api_key or not api_secret:
        print("Error: API key and secret are not configured in your .env file.")
        exit()
        
    # --- Authenticated Exchange Instance ---
    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
    })

    ignored_symbols = []
    whitelisted_symbols = []
    # --- END CONFIGURATION ---

    print(f"Scanning for opportunities on {exchange_name}...")

    trade_fee = FEE_PERCENTAGE / 100

    try:
        asyncio.run(detector.run_detection(
            exchange,
            trade_fee,
            ignored_symbols=ignored_symbols,
            whitelisted_symbols=whitelisted_symbols
        ))
    finally:
        asyncio.run(exchange.close())

    if benchmark:
        elapsed = time.perf_counter() - s
        print(f"\n{__file__} executed in {elapsed:0.2f} seconds.")