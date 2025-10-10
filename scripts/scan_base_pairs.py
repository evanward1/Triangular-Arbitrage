#!/usr/bin/env python3
"""
Scans Base mainnet for all Uniswap V2-style WETH/USDC pairs by:
1. Searching PairCreated events across all contracts (no factory needed)
2. Verifying each pair responds to token0(), token1(), getReserves()
3. Filtering for exactly WETH/USDC pairs
4. Ranking by liquidity

This finds ALL V2-compatible pools on Base, regardless of which DEX.

Usage:
    python3 scripts/scan_base_pairs.py [--blocks N] [--rpc URL]

Example:
    python3 scripts/scan_base_pairs.py --blocks 500000
    python3 scripts/scan_base_pairs.py --rpc https://base.llamarpc.com --blocks 250000
"""

import sys

from eth_abi import decode as abi_decode
from web3 import HTTPProvider, Web3

# Base mainnet defaults
DEFAULT_RPC = "https://mainnet.base.org"
DEFAULT_WETH = "0x4200000000000000000000000000000000000006"
DEFAULT_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_BLOCKS_BACK = 250_000

# Minimal V2 Pair ABI
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


def parse_args():
    """Parse command line arguments."""
    rpc = DEFAULT_RPC
    blocks_back = DEFAULT_BLOCKS_BACK

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--rpc" and i + 2 < len(sys.argv):
            rpc = sys.argv[i + 2]
        elif arg == "--blocks" and i + 2 < len(sys.argv):
            blocks_back = int(sys.argv[i + 2])
        elif arg in ["-h", "--help"]:
            print(__doc__)
            sys.exit(0)

    return rpc, blocks_back


def main():
    rpc_url, blocks_back = parse_args()

    print("🔍 Scanning Base for WETH/USDC V2 pairs")
    print(f"📡 RPC: {rpc_url}")
    print(f"📦 Blocks: last {blocks_back:,}\n")

    # Connect to Base
    try:
        w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to RPC")

        chain_id = w3.eth.chain_id
        head = w3.eth.block_number
        print(f"✓ Connected to chain {chain_id}, block {head:,}\n")
    except Exception as e:
        print(f"❌ RPC connection failed: {e}")
        return 1

    # Calculate block range
    from_block = max(0, head - blocks_back)

    # PairCreated event signature
    pair_created_sig = w3.keccak(
        text="PairCreated(address,address,address,uint256)"
    ).hex()

    # Checksum addresses
    weth = Web3.to_checksum_address(DEFAULT_WETH)
    usdc = Web3.to_checksum_address(DEFAULT_USDC)

    print(f"🔎 Searching PairCreated events from block {from_block:,} to {head:,}...")
    print(f"   Token0: WETH ({weth})")
    print(f"   Token1: USDC ({usdc})\n")

    # Fetch logs for both token orderings
    def fetch_logs(token0, token1):
        try:
            return w3.eth.get_logs(
                {
                    "fromBlock": from_block,
                    "toBlock": head,
                    "topics": [pair_created_sig, token0, token1],
                }
            )
        except Exception as e:
            print(f"⚠ Warning: Log fetch failed: {e}")
            return []

    logs = []
    # Order A: token0=WETH, token1=USDC
    logs += fetch_logs(weth, usdc)
    # Order B: token0=USDC, token1=WETH
    logs += fetch_logs(usdc, weth)

    print(f"📜 Found {len(logs)} PairCreated events")
    print("🔬 Verifying each pair responds to V2 calls...\n")

    # Verify each pair
    verified_pairs = {}
    for log in logs:
        try:
            # Decode pair address from event data
            pair_addr, _ = abi_decode(
                ["address", "uint256"], bytes.fromhex(log["data"][2:])
            )
            pair = Web3.to_checksum_address(pair_addr)

            # Skip if already verified
            if pair in verified_pairs:
                continue

            # Create contract instance
            contract = w3.eth.contract(address=pair, abi=PAIR_ABI)

            # Test V2 calls
            tk0 = Web3.to_checksum_address(contract.functions.token0().call())
            tk1 = Web3.to_checksum_address(contract.functions.token1().call())
            r0, r1, timestamp = contract.functions.getReserves().call()

            # Verify it's exactly WETH/USDC (in either order)
            if {tk0, tk1} != {weth, usdc}:
                continue

            # Store verified pair
            verified_pairs[pair] = {
                "token0": tk0,
                "token1": tk1,
                "reserve0": r0,
                "reserve1": r1,
                "timestamp": timestamp,
                "liquidity_proxy": r0 + r1,  # Simple sum for ranking
            }

            print(f"  ✓ {pair}")

        except Exception:
            # Not a V2 pair or call failed - skip silently
            continue

    # Sort by liquidity
    sorted_pairs = sorted(
        verified_pairs.items(), key=lambda x: x[1]["liquidity_proxy"], reverse=True
    )

    print(f"\n{'='*80}")
    print(f"✅ Found {len(sorted_pairs)} verified WETH/USDC V2-style pairs on Base")
    print(f"{'='*80}\n")

    if not sorted_pairs:
        print("⚠️ No pairs found in the specified block range.")
        print("\nTry:")
        print("  - Increasing --blocks (e.g., --blocks 500000 or --blocks 1000000)")
        print("  - Using a different RPC endpoint with --rpc")
        print("  - Checking if Base has V2-style DEXes deployed")
        return 1

    # Print all pairs
    for i, (addr, info) in enumerate(sorted_pairs, 1):
        print(f"{i:2d}. {addr}")
        print(f"    token0: {info['token0']}")
        print(f"    token1: {info['token1']}")
        print(f"    reserves: ({info['reserve0']:,}, {info['reserve1']:,})")
        print(f"    liquidity: {info['liquidity_proxy']:,}")
        print()

    # Show config for top pairs
    if len(sorted_pairs) >= 2:
        print(f"{'='*80}")
        print("📋 Ready to paste into configs/dex_mev.yaml")
        print(f"{'='*80}\n")
        print("dexes:")

        for i, (addr, info) in enumerate(sorted_pairs[:2], 1):
            # Determine which token is WETH and which is USDC
            if info["token0"] == weth:
                base_token = "WETH"
                quote_token = "USDC"
            else:
                base_token = "USDC"
                quote_token = "WETH"

            print(f'  - name: "dex_{i}"  # Replace with actual DEX name')
            print('    kind: "v2"')
            print("    fee_bps: 30  # Verify actual fee (25-30 typical)")
            print("    pairs:")
            print(f'      - name: "{base_token}/{quote_token}"')
            print(f'        address: "{addr}"')
            print(f'        base: "{base_token}"')
            print(f'        quote: "{quote_token}"')
            print()
    else:
        print("\n⚠️ Only found 1 pair - you need at least 2 for cross-DEX arbitrage")

    print(f"{'='*80}")
    print("🚀 Next step: python3 run_dex_paper.py --once")
    print(f"{'='*80}\n")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⏸ Interrupted by user")
        sys.exit(1)
