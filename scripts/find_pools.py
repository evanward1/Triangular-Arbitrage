#!/usr/bin/env python3
"""
Scans Uniswap V2-style factory contracts for PairCreated events
to find WETH/USDC (or other) pools on Base or other chains.

Usage:
    python3 scripts/find_pools.py <rpc_url> <factory_address> <token0> <token1> [--blocks N]

Example (Base):
    python3 scripts/find_pools.py https://mainnet.base.org \\
        0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB \\
        0x4200000000000000000000000000000000000006 \\
        0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \\
        --blocks 100000

This searches the last 100k blocks for PairCreated(token0, token1, pair) events.
Prints all discovered pair addresses.
"""

import sys

from web3 import HTTPProvider, Web3

# Uniswap V2 Factory ABI (PairCreated event only)
FACTORY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "token0", "type": "address"},
            {"indexed": True, "name": "token1", "type": "address"},
            {"indexed": False, "name": "pair", "type": "address"},
            {"indexed": False, "name": "", "type": "uint256"},
        ],
        "name": "PairCreated",
        "type": "event",
    }
]


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)

    rpc_url = sys.argv[1]
    factory_addr = sys.argv[2]
    token0 = sys.argv[3]
    token1 = sys.argv[4]

    # Optional: block range
    blocks_back = 100_000
    if "--blocks" in sys.argv:
        idx = sys.argv.index("--blocks")
        if idx + 1 < len(sys.argv):
            blocks_back = int(sys.argv[idx + 1])

    print(f"🔍 Scanning factory: {factory_addr}")
    print(f"📡 RPC: {rpc_url}")
    print(f"🪙  token0: {token0}")
    print(f"🪙  token1: {token1}")
    print(f"📦 Blocks: last {blocks_back:,}\n")

    # Connect
    try:
        w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect")
        chain_id = w3.eth.chain_id
        latest_block = w3.eth.block_number
        print(f"✓ Connected to chain {chain_id}, latest block {latest_block:,}\n")
    except Exception as e:
        print(f"❌ RPC error: {e}")
        sys.exit(1)

    # Checksum addresses
    try:
        factory_addr = Web3.to_checksum_address(factory_addr)
        token0 = Web3.to_checksum_address(token0)
        token1 = Web3.to_checksum_address(token1)
    except Exception as e:
        print(f"❌ Invalid address: {e}")
        sys.exit(1)

    # Create factory contract
    factory = w3.eth.contract(address=factory_addr, abi=FACTORY_ABI)

    # Calculate block range
    from_block = max(0, latest_block - blocks_back)
    to_block = latest_block

    print(f"📜 Fetching PairCreated events from block {from_block:,} to {to_block:,}...")

    # Query logs
    try:
        # UniswapV2 stores tokens in sorted order, so try both orderings
        pairs = []

        # Try token0 < token1
        try:
            logs = factory.events.PairCreated.get_logs(
                fromBlock=from_block,
                toBlock=to_block,
                argument_filters={"token0": token0, "token1": token1},
            )
            for log in logs:
                pairs.append(log["args"]["pair"])
        except Exception:
            pass

        # Try token1 < token0 (reversed)
        try:
            logs = factory.events.PairCreated.get_logs(
                fromBlock=from_block,
                toBlock=to_block,
                argument_filters={"token0": token1, "token1": token0},
            )
            for log in logs:
                pairs.append(log["args"]["pair"])
        except Exception:
            pass

        # Deduplicate
        pairs = list(set(pairs))

        if not pairs:
            print("❌ No pairs found for these tokens in the specified block range.")
            print("\nTry:")
            print("  - Increasing --blocks (e.g., --blocks 500000)")
            print("  - Checking token addresses are correct")
            print("  - Verifying the factory address is correct")
            sys.exit(1)

        print(f"\n✅ Found {len(pairs)} pair(s):\n")
        for i, pair in enumerate(pairs, 1):
            print(f"  {i}. {pair}")

        print("\n📝 To verify a pair works with our scanner:")
        print(f"  python3 scripts/check_pair.py {rpc_url} <PAIR_ADDRESS>")

        print("\n📋 Add to configs/dex_mev.yaml:")
        print("  dexes:")
        print('    - name: "dex_name"')
        print('      kind: "v2"')
        print("      fee_bps: 30  # Check DEX docs for actual fee")
        print("      pairs:")
        for pair in pairs[:3]:  # Show first 3 as examples
            print('        - name: "TOKEN/TOKEN"')
            print(f'          address: "{pair}"')
            print('          base: "TOKEN_SYMBOL"')
            print('          quote: "TOKEN_SYMBOL"')

    except Exception as e:
        print(f"❌ Error fetching logs: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
