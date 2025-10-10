# DEX/MEV Arbitrage - Paper Trading

Cross-DEX arbitrage simulator for Uniswap V2-style pools.

## Quick Start

1. **Set up RPC endpoint** in `.env`:
   ```bash
   RPC_URL=https://mainnet.infura.io/v3/YOUR_INFURA_KEY
   # or use Alchemy:
   # RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
   ```

2. **Configure parameters** (optional, defaults shown):
   ```bash
   GAS_PRICE_GWEI=12        # Current gas price
   GAS_LIMIT=180000         # Gas limit for dual swap
   SCAN_SEC=10              # Seconds between scans
   START_CASH_USDC=1000     # Starting capital
   GRID_LO_USDC=10          # Minimum trade size
   GRID_HI_USDC=10000       # Maximum trade size
   GRID_STEPS=40            # Size optimization granularity
   ```

3. **Run**:
   ```bash
   python3 run_dex.py
   ```

## What It Does

- Monitors **USDC/WETH** pools on Uniswap V2 and SushiSwap
- Finds cross-DEX price discrepancies
- Simulates round-trip trades: USDC → WETH → USDC
- Accounts for:
  - 0.30% pool fees (each leg)
  - Pool depth and price impact
  - Gas costs (based on current gas price)
- Executes profitable opportunities in paper mode
- Prints P&L every 5 scans

## Output Example

```
📝 DEX ARB PAPER MODE (V2↔V2 USDC/WETH) | fees=0.30% per pool
Gas≈12 gwei × 180000 | Start cash=$1,000.00

🔍 Scan   1 | UNI $3245.67 | SUSHI $3246.12 | dir=UNI→SUSHI | size=$250.00 | gross=$0.35 gas=$0.12 net=$0.23 | EXEC
🔍 Scan   2 | UNI $3245.89 | SUSHI $3245.78 | dir=SUSHI→UNI | size=$100.00 | gross=$0.08 gas=$0.12 net=$-0.04 | skip
🔍 Scan   3 | UNI $3246.01 | SUSHI $3245.95 | dir=(no edge) | size=$0.00 | gross=$-1000000000000000000.00 gas=$0.12 net=$-1000000000000000000.12 | skip
🔍 Scan   4 | UNI $3245.34 | SUSHI $3246.21 | dir=UNI→SUSHI | size=$500.00 | gross=$0.89 gas=$0.12 net=$0.77 | EXEC
🔍 Scan   5 | UNI $3245.67 | SUSHI $3245.89 | dir=UNI→SUSHI | size=$150.00 | gross=$0.18 gas=$0.12 net=$0.06 | EXEC
💼 Equity: $1,001.06 (Δ $1.06, +0.11%)
```

## Architecture

- **dex_v2_arb.py**: Core V2 pool logic
  - `fetch_pair()`: Reads reserves from on-chain
  - `amount_out_v2()`: Calculates swap output with fees
  - `simulate_cycle_usdc()`: Round-trip simulation
  - `DexV2Paper.run()`: Main scan loop

## Next Steps

1. **Add more pools**: Edit `UNIV2_USDC_WETH` / `SUSHI_USDC_WETH` to track more pairs
2. **Multi-pair support**: Track USDT/WETH, DAI/WETH simultaneously
3. **Uniswap V3**: Add concentrated liquidity math for V3 pools
4. **Multi-hop routes**: USD→ETH→BTC→USD across 3 pools
5. **Live execution**: Convert to real trading with flashbots/MEV-boost

## Pool Addresses (Ethereum Mainnet)

- Uniswap V2 USDC/WETH: `0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc`
- SushiSwap USDC/WETH: `0x397FF1542f962076d0BFE58eA045FfA2d347ACa0`

## Fees

- Uniswap V2: 0.30% per swap
- SushiSwap: 0.30% per swap
- **Total round-trip**: 0.60% (2 swaps)
- **Gas**: ~180k gas × current gwei price

## Notes

- This is **paper trading only** - no real funds at risk
- RPC rate limits apply (consider paid tier for production)
- Pool reserves update every block (~12 seconds)
- Negative net = skip execution
- Position sizing uses grid search for optimal trade size
