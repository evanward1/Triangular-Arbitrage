#!/usr/bin/env python3
"""
DEX/MEV Paper Runner (kept separate from CEX runner)
"""
from triangular_arbitrage_dex.dex_v2_arb import DexV2Paper

if __name__ == "__main__":
    DexV2Paper().run()
