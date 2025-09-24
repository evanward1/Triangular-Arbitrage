#!/usr/bin/env python3
"""
Check available Coinbase markets and find valid triangular arbitrage cycles
"""
import os
from dotenv import load_dotenv
from coinbase_adapter import CoinbaseAdvancedAdapter
import asyncio

async def main():
    load_dotenv()

    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")

    adapter = CoinbaseAdvancedAdapter(api_key, api_secret)
    markets = await adapter.load_markets()

    # Find popular triangular cycles that exist on Coinbase
    popular_bases = ['BTC', 'ETH', 'SOL', 'ADA', 'DOT', 'AVAX', 'LINK', 'LTC']
    popular_quotes = ['USD', 'USDC', 'USDT', 'BTC', 'ETH']

    valid_symbols = list(markets.keys())
    print(f"Found {len(valid_symbols)} valid trading pairs")

    # Look for common triangular patterns
    triangular_cycles = []

    for base in popular_bases:
        for intermediate in popular_bases:
            for quote in popular_quotes:
                if base == intermediate or base == quote or intermediate == quote:
                    continue

                pair1 = f"{base}/{intermediate}"
                pair2 = f"{intermediate}/{quote}"
                pair3 = f"{base}/{quote}"

                if pair1 in valid_symbols and pair2 in valid_symbols and pair3 in valid_symbols:
                    cycle = (base, intermediate, quote, pair1, pair2, pair3)
                    triangular_cycles.append(cycle)

    print(f"\nFound {len(triangular_cycles)} valid triangular arbitrage cycles:")

    # Show first 20 cycles
    for i, cycle in enumerate(triangular_cycles[:20]):
        base, inter, quote, p1, p2, p3 = cycle
        print(f"{i+1:2d}. {base} -> {inter} -> {quote} -> {base}: {p1}, {p2}, {p3}")

    if len(triangular_cycles) > 20:
        print(f"... and {len(triangular_cycles) - 20} more")

if __name__ == "__main__":
    asyncio.run(main())