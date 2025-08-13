import asyncio
import octobot_commons.os_util as os_util
import triangular_arbitrage.detector as detector

if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # Windows handles asynchronous event loops

    benchmark = os_util.parse_boolean_environment_var("IS_BENCHMARKING", "False")
    if benchmark:
        import time
        s = time.perf_counter()

    # --- CONFIGURATION ---
    # The exchange you want to use (e.g., "coinbase", "binance", "kraken")
    # Make sure it's a valid exchange_id from the ccxt library
    exchange_name = "coinbase"

    # The trading fee as a percentage (e.g., 0.1 for 0.1%)
    # This is crucial for realistic profit calculation.
    FEE_PERCENTAGE = 0.1

    # Optional: You can ignore or specifically target certain symbols
    ignored_symbols = []
    whitelisted_symbols = []
    # --- END CONFIGURATION ---

    print(f"Scanning for opportunities on {exchange_name}...")

    # Calculate the fee as a decimal for the detector
    trade_fee = FEE_PERCENTAGE / 100

    # Start the arbitrage detection process.
    # The detector module will now handle printing any found opportunities.
    asyncio.run(detector.run_detection(
        exchange_name,
        trade_fee,
        ignored_symbols=ignored_symbols,
        whitelisted_symbols=whitelisted_symbols
    ))

    if benchmark:
        elapsed = time.perf_counter() - s
        print(f"\n{__file__} executed in {elapsed:0.2f} seconds.")
