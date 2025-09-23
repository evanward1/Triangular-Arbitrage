#!/usr/bin/env python3
"""
Generate ALL possible triangular arbitrage cycles from Coinbase's 793 trading pairs
This creates thousands of combinations instead of the weak 20 we had before
"""
import os
import asyncio
from dotenv import load_dotenv
from coinbase_adapter import CoinbaseAdvancedAdapter
from itertools import combinations
import csv
from collections import defaultdict

async def generate_massive_cycles():
    load_dotenv()

    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")

    adapter = CoinbaseAdvancedAdapter(api_key, api_secret)
    markets = await adapter.load_markets()

    print(f"🚀 Processing {len(markets)} trading pairs from Coinbase...")

    # Parse all available currencies and their trading pairs
    currencies = set()
    trading_pairs = {}

    for symbol, market_data in markets.items():
        if not market_data.get('active', True):
            continue

        base = market_data['base']
        quote = market_data['quote']

        currencies.add(base)
        currencies.add(quote)

        # Store bidirectional trading info
        if base not in trading_pairs:
            trading_pairs[base] = set()
        if quote not in trading_pairs:
            trading_pairs[quote] = set()

        trading_pairs[base].add(quote)
        trading_pairs[quote].add(base)

    print(f"📊 Found {len(currencies)} unique currencies")
    print(f"🔗 Active trading relationships mapped")

    # Generate ALL possible triangular arbitrage cycles
    triangular_cycles = []

    print("🔍 Generating triangular arbitrage cycles...")

    for base_currency in currencies:
        if base_currency not in trading_pairs:
            continue

        # For each currency that can be traded with base_currency
        for intermediate_currency in trading_pairs[base_currency]:
            if intermediate_currency == base_currency or intermediate_currency not in trading_pairs:
                continue

            # For each currency that can be traded with intermediate_currency
            for quote_currency in trading_pairs[intermediate_currency]:
                if quote_currency == base_currency or quote_currency == intermediate_currency:
                    continue
                if quote_currency not in trading_pairs:
                    continue

                # Check if we can complete the triangle back to base_currency
                if base_currency in trading_pairs[quote_currency]:
                    # We found a valid triangular arbitrage cycle!
                    cycle = (base_currency, intermediate_currency, quote_currency)

                    # Avoid duplicates by sorting the cycle
                    sorted_cycle = tuple(sorted(cycle))
                    if sorted_cycle not in [tuple(sorted(existing)) for existing in triangular_cycles]:

                        # Determine the actual trading pairs needed
                        pair1 = f"{base_currency}/{intermediate_currency}" if f"{base_currency}/{intermediate_currency}" in markets else f"{intermediate_currency}/{base_currency}"
                        pair2 = f"{intermediate_currency}/{quote_currency}" if f"{intermediate_currency}/{quote_currency}" in markets else f"{quote_currency}/{intermediate_currency}"
                        pair3 = f"{quote_currency}/{base_currency}" if f"{quote_currency}/{base_currency}" in markets else f"{base_currency}/{quote_currency}"

                        # Verify all pairs exist
                        if pair1 in markets and pair2 in markets and pair3 in markets:
                            triangular_cycles.append((base_currency, intermediate_currency, quote_currency, pair1, pair2, pair3))

    print(f"💥 Generated {len(triangular_cycles)} triangular arbitrage cycles!")

    # Filter for high-volume, liquid currencies for better arbitrage opportunities
    priority_currencies = {
        'BTC', 'ETH', 'USDT', 'USDC', 'USD', 'SOL', 'ADA', 'DOT', 'AVAX', 'LINK',
        'LTC', 'XRP', 'DOGE', 'MATIC', 'ATOM', 'NEAR', 'ALGO', 'XLM', 'HBAR',
        'MANA', 'SAND', 'APE', 'FIL', 'AAVE', 'UNI', 'COMP', 'MKR', 'SNX',
        'BAT', 'ZRX', 'OMG', 'GRT', 'ENJ', 'STORJ', 'SKL', 'NMR', 'RLY'
    }

    # Separate high-priority and general cycles
    priority_cycles = []
    general_cycles = []

    for cycle in triangular_cycles:
        base, intermediate, quote = cycle[0], cycle[1], cycle[2]
        if base in priority_currencies and intermediate in priority_currencies and quote in priority_currencies:
            priority_cycles.append(cycle)
        else:
            general_cycles.append(cycle)

    print(f"⭐ {len(priority_cycles)} high-priority cycles (liquid tokens)")
    print(f"📈 {len(general_cycles)} general cycles (all tokens)")

    # Save the massive cycle files
    def save_cycles(cycles, filename, description):
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['base', 'inter', 'quote', 'pair1', 'pair2', 'pair3', 'fee_bps', 'min_profit_bps'])

            for base, inter, quote, pair1, pair2, pair3 in cycles:
                writer.writerow([base, inter, quote, pair1, pair2, pair3, 10, 7])  # 10bps fee, 7bps min profit

        print(f"💾 Saved {len(cycles)} cycles to {filename} ({description})")

    # Save different strategy files
    save_cycles(priority_cycles[:500], 'data/cycles/coinbase_cycles_priority.csv', 'Top 500 liquid tokens')
    save_cycles(triangular_cycles[:1000], 'data/cycles/coinbase_cycles_massive.csv', 'Top 1000 all tokens')
    save_cycles(triangular_cycles, 'data/cycles/coinbase_cycles_complete.csv', 'Complete set')

    print(f"\n🎯 CYCLE GENERATION COMPLETE!")
    print(f"📊 Total cycles generated: {len(triangular_cycles)}")
    print(f"🚀 Ready to scan MASSIVE arbitrage opportunities!")

if __name__ == "__main__":
    asyncio.run(generate_massive_cycles())