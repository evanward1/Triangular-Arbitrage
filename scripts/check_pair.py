#!/usr/bin/env python3
"""
Quick verifier for Uniswap V2-style pair contracts.

Usage:
    python3 scripts/check_pair.py <rpc_url> <pair_address>

Example:
    python3 scripts/check_pair.py https://mainnet.base.org 0x...

Returns:
    - ✅ if the pair has token0(), token1(), getReserves()
    - Prints token addresses and current reserves
    - Exit code 0 on success, 1 on failure
"""

import sys

from web3 import HTTPProvider, Web3

# Minimal UniV2-like Pair ABI fragments
PAIR_ABI = [
    {
        "name": "token0",
        "outputs": [{"type": "address"}],
        "inputs": [],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "name": "token1",
        "outputs": [{"type": "address"}],
        "inputs": [],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "name": "getReserves",
        "outputs": [
            {"type": "uint112", "name": "_reserve0"},
            {"type": "uint112", "name": "_reserve1"},
            {"type": "uint32", "name": "_blockTimestampLast"},
        ],
        "inputs": [],
        "stateMutability": "view",
        "type": "function",
    },
]


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scripts/check_pair.py <rpc_url> <pair_address>")
        print("\nExample:")
        print("  python3 scripts/check_pair.py https://mainnet.base.org 0x...")
        sys.exit(1)

    rpc_url = sys.argv[1]
    pair_addr = sys.argv[2]

    print(f"🔍 Checking pair: {pair_addr}")
    print(f"📡 RPC: {rpc_url}\n")

    # Connect to RPC
    try:
        w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to RPC")

        chain_id = w3.eth.chain_id
        block = w3.eth.block_number
        print(f"✓ Connected to chain {chain_id}, block {block}")
    except Exception as e:
        print(f"❌ RPC connection failed: {e}")
        sys.exit(1)

    # Checksum address
    try:
        pair_addr = Web3.to_checksum_address(pair_addr)
    except Exception as e:
        print(f"❌ Invalid address format: {e}")
        sys.exit(1)

    # Create contract instance
    pair = w3.eth.contract(address=pair_addr, abi=PAIR_ABI)

    # Test token0()
    try:
        token0 = pair.functions.token0().call()
        print(f"✓ token0(): {token0}")
    except Exception as e:
        print(f"❌ token0() failed: {e}")
        sys.exit(1)

    # Test token1()
    try:
        token1 = pair.functions.token1().call()
        print(f"✓ token1(): {token1}")
    except Exception as e:
        print(f"❌ token1() failed: {e}")
        sys.exit(1)

    # Test getReserves()
    try:
        reserves = pair.functions.getReserves().call()
        r0, r1, timestamp = reserves
        print("✓ getReserves():")
        print(f"  reserve0: {r0:,}")
        print(f"  reserve1: {r1:,}")
        print(f"  timestamp: {timestamp}")
    except Exception as e:
        print(f"❌ getReserves() failed: {e}")
        sys.exit(1)

    print("\n✅ Pair is VALID for V2 scanner!")
    print("\nAdd to configs/dex_mev.yaml:")
    print('  - name: "dex_name"')
    print('    kind: "v2"')
    print("    fee_bps: 30  # Adjust based on DEX")
    print("    pairs:")
    print('      - name: "TOKEN/TOKEN"')
    print(f'        address: "{pair_addr}"')
    print('        base: "TOKEN0_SYMBOL"')
    print('        quote: "TOKEN1_SYMBOL"')

    return 0


if __name__ == "__main__":
    sys.exit(main())
