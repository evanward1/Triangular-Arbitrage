# DEX Pool Finding & Verification Scripts

Utility scripts to find and verify Uniswap V2-style pool addresses for the DEX paper trading scanner.

## Quick Start

### 1. Find Pools on Base

Search for WETH/USDC pools across Base DEXes:

```bash
# BaseSwap factory (example - verify address on BaseScan)
python3 scripts/find_pools.py \
  https://mainnet.base.org \
  0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB \
  0x4200000000000000000000000000000000000006 \
  0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  --blocks 500000
```

This searches the last 500k blocks for PairCreated events and prints all discovered pool addresses.

### 2. Verify a Pool Works

Before adding to your config, verify the pool has the correct interface:

```bash
python3 scripts/check_pair.py https://mainnet.base.org 0xYOUR_PAIR_ADDRESS
```

**Expected output:**
```
✅ Pair is VALID for V2 scanner!
```

If you see errors, the pool either:
- Isn't a V2-style pair (might be V3, Curve, etc.)
- Uses a custom interface
- Doesn't exist at that address

### 3. Add to Config

Once verified, add to `configs/dex_mev.yaml`:

```yaml
dexes:
  - name: "baseswap"
    kind: "v2"
    fee_bps: 25  # Check DEX docs for actual fee
    pairs:
      - name: "WETH/USDC"
        address: "0xVERIFIED_PAIR_ADDRESS"
        base: "WETH"
        quote: "USDC"
```

**You need at least 2 DEXes with the same pair for cross-DEX arbitrage!**

## Script Reference

### `check_pair.py`

Verifies a single pair address works with our V2 scanner.

**Usage:**
```bash
python3 scripts/check_pair.py <rpc_url> <pair_address>
```

**Tests:**
- `token0()` returns address
- `token1()` returns address
- `getReserves()` returns (uint112, uint112, uint32)

**Exit codes:**
- `0` - Pair is valid
- `1` - Pair failed verification

### `find_pools.py`

Scans factory contracts for PairCreated events to discover pools.

**Usage:**
```bash
python3 scripts/find_pools.py <rpc_url> <factory_address> <token0> <token1> [--blocks N]
```

**Arguments:**
- `rpc_url` - HTTP(S) RPC endpoint
- `factory_address` - UniswapV2Factory (or fork) address
- `token0` - First token address (WETH, USDC, etc.)
- `token1` - Second token address
- `--blocks N` - Search last N blocks (default: 100,000)

**Notes:**
- Automatically tries both token orderings (V2 stores tokens sorted)
- Deduplicates results
- Can take 30-60s depending on block range and RPC speed

## Common Base DEX Factories

**Note:** Always verify these addresses on BaseScan before use!

| DEX | Factory Address (Base) | Fee |
|-----|------------------------|-----|
| BaseSwap | `0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB` | 0.25% |
| SushiSwap | TBD - verify on BaseScan | 0.30% |
| LeetSwap | TBD - verify on BaseScan | 0.30% |

To find factory addresses:
1. Go to the DEX's official docs
2. Look for "Contracts" or "Developers" section
3. Copy the **Factory** address for Base mainnet
4. Verify on BaseScan it has `PairCreated` events

## Token Addresses (Base Mainnet)

```yaml
WETH: 0x4200000000000000000000000000000000000006
USDC: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
USDbC: 0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA  # Bridged USDC
DAI: 0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb
```

## Troubleshooting

### "No pairs found"

Try:
- Increase `--blocks` (e.g., `--blocks 1000000`)
- Verify token addresses are correct (check BaseScan)
- Confirm factory address is for Base mainnet (not testnet/Ethereum)

### "getReserves() failed: execution reverted"

The pair exists but isn't V2-compatible. Could be:
- Uniswap V3 pool (needs Quoter, not getReserves)
- Curve pool (different math)
- Balancer pool (weighted pools)
- Custom AMM

Our scanner **only supports V2** (constant product x*y=k).

### "RPC rate limit exceeded"

Use a paid RPC provider (Alchemy, Infura, QuickNode) or:
- Reduce `--blocks` search range
- Add delays between requests
- Switch to a different RPC endpoint

## Finding More DEXes

To find DEXes on Base:
1. Visit DeFiLlama: https://defillama.com/chain/Base
2. Filter for "DEXes"
3. Look for "V2-style" or "Uniswap V2 fork"
4. Check their docs for factory addresses

**Compatible DEX types:**
- ✅ Uniswap V2 forks (constant product)
- ✅ SushiSwap
- ✅ PancakeSwap V2
- ❌ Uniswap V3 (different interface - coming soon)
- ❌ Curve (stable swaps - different math)
- ❌ Balancer (weighted pools)

## Example Workflow

```bash
# 1. Find BaseSwap pools for WETH/USDC
python3 scripts/find_pools.py \
  https://mainnet.base.org \
  0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB \
  0x4200000000000000000000000000000000000006 \
  0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  --blocks 500000

# Output: Found 1 pair: 0xABC...

# 2. Verify it works
python3 scripts/check_pair.py https://mainnet.base.org 0xABC...

# Output: ✅ Pair is VALID

# 3. Find SushiSwap pools (same tokens, different factory)
python3 scripts/find_pools.py \
  https://mainnet.base.org \
  0xSUSHI_FACTORY_ADDRESS \
  0x4200000000000000000000000000000000000006 \
  0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  --blocks 500000

# 4. Add both to configs/dex_mev.yaml

# 5. Run scanner
python3 run_dex_paper.py --once
```

## Support

If you're stuck finding pools:
1. Check BaseScan for recent DEX transactions
2. Look at DEX aggregator APIs (1inch, Paraswap)
3. Ask in the DEX's Discord/Telegram for contract addresses
