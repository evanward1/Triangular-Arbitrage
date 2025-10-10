# Triangular Arbitrage Trading System

A cryptocurrency triangular arbitrage detection and execution system that automatically identifies and executes profitable trading opportunities across multiple exchanges using real-time market data.

## Overview

This system continuously monitors cryptocurrency markets to find triangular arbitrage opportunities—profitable cycles that exploit price differences across three trading pairs. For example: USD → BTC → ETH → USD, where the exchange rates create a net profit opportunity.

### Key Features

- **⚡ Real-Time Detection**: Continuously scans markets for profitable arbitrage cycles
- **🔄 Multi-Exchange Support**: Works with Binance, Kraken, KuCoin, and Coinbase
- **🔗 DEX Support**: NEW! DEX/MEV arbitrage on Ethereum with Uniswap V3
- **🤖 Machine Learning**: GNN-based cycle scoring learns from historical trade performance
- **📊 Live Market Data**: Uses real-time order book data with configurable depth levels
- **💰 Dual Trading Modes**: Paper trading (simulation) and live trading (real money)
- **🛡️ Risk Management**: Configurable position limits, profit thresholds, and execution controls
- **📈 Equity Tracking**: Tracks portfolio value and P&L over time
- **🎯 Smart Filtering**: Configurable symbol allowlists, triangle bases, and exclusion lists

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Triangular-Arbitrage

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API credentials (optional for paper trading)
```

### Running the System

The system provides a unified command-line interface through `run_clean.py`:

**Interactive Mode (Recommended for Beginners)**
```bash
# Interactive menu - choose CEX/DEX and paper/live trading
python run_clean.py
```

**CEX Arbitrage (Centralized Exchanges)**
```bash
# Paper trading mode (safe simulation)
python run_clean.py cex --paper

# Live trading mode (real money - requires API keys)
python run_clean.py cex --live
```

**DEX/MEV Arbitrage (Decentralized Exchanges)**
```bash
# Paper trading mode (quiet output, single scan for testing)
python run_clean.py dex --quiet --once

# Continuous paper trading (quiet mode)
python run_clean.py dex --quiet

# Custom config file
python run_clean.py dex --config configs/dex_mev.yaml

# Live trading mode (requires wallet setup - see DEX section below)
python run_clean.py dex --live --config configs/dex_mev.yaml
```

## Configuration

### Environment Variables

Configure the system by setting environment variables in your `.env` file:

#### Trading Configuration

```bash
# Position sizing
MAX_POSITION_SIZE=100          # Maximum USD per trade
MIN_PROFIT_THRESHOLD=0.5       # Minimum profit % to execute (after fees)

# Execution limits
MAX_LEG_LATENCY_MS=2000       # Maximum latency per leg (milliseconds)
MIN_FRACTION_OF_TARGET=0.05   # Minimum fraction of target size for depth checks
```

#### Paper Trading Settings

```bash
# Starting balances for paper trading
PAPER_USDT=1000               # Starting USDT balance
PAPER_USDC=1000               # Starting USDC balance
```

#### Display and Output Settings

```bash
# Verbosity control
VERBOSITY=normal              # normal, quiet, or debug
TOPN=3                        # Number of top opportunities to display
RUN_MIN=3                     # Minimum runtime in minutes before showing summary

# Deduplication
DEDUPE=true                   # Enable deduplication of similar opportunities
CHANGE_BPS=3                  # Basis points change threshold for deduplication
PRINT_EVERY_N=6               # Print every Nth scan if no changes

# Display options
SHOW_DELTA=true               # Show change from previous best opportunity
SHOW_USD=true                 # Show USD-denominated P&L
REASON_BUCKETS=true           # Track rejection reasons by category
```

#### Symbol Filtering

```bash
# Symbol curation
SYMBOL_ALLOWLIST=BTC,ETH,SOL,AVAX,LINK  # Only include these symbols
TRIANGLE_BASES=USD,USDT                  # Required base currencies for triangles
EXCLUDE_SYMBOLS=SHIB,DOGE                # Exclude specific symbols

# Market data
DEPTH_LEVELS=20               # Order book depth levels to fetch
POLL_SEC=10                   # Seconds between market scans
FEE_SOURCE=static             # 'static' or 'auto' (fetch from exchange)
```

#### Expected Value Tracking

```bash
# EV calculation
EV_WINDOW=30                  # Rolling window for EV calculation (scans)
EV_ONLY_ABOVE_THR=true       # Only count opportunities above threshold
EV_DAY_FACTOR=true           # Extrapolate to daily EV
```

#### Equity Tracking

```bash
EQUITY_PRECISION=2            # Decimal places for equity display
EQUITY_EVERY_N=3             # Record equity every N scans
```

### Exchange API Configuration

For live trading, configure your exchange API credentials in `.env`:

```bash
# Binance (Primary - Lowest fees)
BINANCEUS_API_KEY=your_api_key
BINANCEUS_SECRET=your_secret

# Kraken
KRAKEN_API_KEY=your_api_key
KRAKEN_SECRET=your_secret

# KuCoin
KUCOIN_API_KEY=your_api_key
KUCOIN_SECRET=your_secret
KUCOIN_PASSWORD=your_password

# Coinbase Pro
COINBASE_API_KEY=your_api_key
COINBASE_SECRET=your_secret
COINBASE_PASSPHRASE=your_passphrase
```

## How It Works

### Triangular Arbitrage Detection

The system uses graph theory to detect profitable cycles:

1. **Graph Construction**: Creates a directed graph where nodes are currencies and edges are trading pairs
2. **Cycle Detection**: Uses the Bellman-Ford algorithm to find negative-weight cycles (profit opportunities)
3. **Profit Calculation**: Calculates net profit after fees, slippage, and execution costs
4. **Execution**: Executes profitable cycles that meet the minimum threshold

### Trading Flow

```
┌─────────────────────────────────────────┐
│  Fetch Market Data (Tickers + Depth)   │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Build Currency Graph                   │
│  (Filter by allowlist/bases)            │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Find Arbitrage Cycles                  │
│  (Bellman-Ford algorithm)               │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Calculate Profit & Check Depth         │
│  - Net profit after fees                │
│  - Slippage estimation                  │
│  - Liquidity validation                 │
└──────────────────┬──────────────────────┘
                   │
         ┌─────────▼─────────┐
         │ Profitable?       │
         │ Above threshold?  │
         └─────────┬─────────┘
              Yes  │  No
         ┌─────────▼─────────┐
         │ Execute Trade     │  Skip
         │ (or simulate)     │
         └───────────────────┘
```

### Exchange Fee Structure

The system accounts for exchange-specific fees:

- **Binance**: 0.10% maker/taker (0.075% with BNB discount)
- **Kraken**: 0.16% maker / 0.26% taker
- **KuCoin**: 0.10% maker/taker
- **Coinbase**: 0.40% maker / 0.60% taker

## Output and Monitoring

### Example Output

```
🧹 Database cleared

Choose trading mode:
1. 📝 Paper Trading (Simulation - Safe)
2. 💰 Live Trading (Real Money - Risk)

Enter your choice (1 or 2): 1
📝 PAPER TRADING MODE - Simulation only
💰 Position: $100 | Threshold: 0.5% NET

🔄 Trying binanceus...
✅ Connected to BinanceUS | 793 markets

⚡ SCAN #1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Best cycle: USDT→BTC→ETH→USDT
   Gross: +0.87% | Net: +0.57% | Size: $98.50
   Depth OK | Slippage: 0.12% | Latency: 145ms
   ✅ EXECUTED (paper)

📊 Equity: $1000.57 (+0.57) | Realized: +$0.57

⚡ SCAN #2 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Scanning 1,920 cycles...
💤 No opportunities above threshold (best: +0.23%)

Near misses:
  • USDC→SOL→AVAX→USDC: +0.42% (depth limited)
  • USDT→LINK→ETH→USDT: +0.38% (fees too high)
```

### Logs and Data

- **Equity Tracking**: `logs/equity_timeseries.csv` - Time series of portfolio equity
- **Trade History**: `logs/trades_*.csv` - Detailed trade execution records
- **GNN State**: `logs/gnn_state.json` - Machine learning model state (edge weights, success rates)
- **Database**: `trade_state.db` - SQLite database for cycle state management

## Architecture

### Core Components

```
trading_arbitrage.py
├── RealTriangularArbitrage     # Main trading engine
│   ├── _setup_exchange()       # Exchange initialization
│   ├── fetch_data()            # Market data fetching
│   ├── build_graph()           # Currency graph construction
│   ├── find_cycles()           # Arbitrage detection
│   ├── calculate_profit()      # Profit calculation with fees/slippage
│   ├── execute_cycle()         # Trade execution (live/paper)
│   └── track_equity()          # Portfolio tracking
│
triangular_arbitrage/           # Supporting modules
├── execution_helpers.py        # Depth, slippage, latency helpers
├── execution_engine.py         # Strategy execution engine
├── detector.py                 # Opportunity detection
├── risk_controls.py           # Risk management
├── gnn_optimizer.py           # GNN-based cycle scoring
└── metrics.py                 # Performance metrics
```

### Key Algorithms

**Bellman-Ford Arbitrage Detection**
- Transforms exchange rates to log-space for additive calculations
- Finds negative-weight cycles representing profit opportunities
- Handles up to 1,920+ triangular combinations efficiently

**Depth-Limited Sizing**
- Analyzes order book depth at configured levels
- Limits position size based on available liquidity
- Estimates slippage impact on profitability

**Equity Tracking**
- Records portfolio value at each scan
- Tracks realized and unrealized P&L
- Maintains time series in CSV format

**GNN Cycle Scoring (Machine Learning)**
- Graph Neural Network learns from historical trade outcomes
- Tracks success rates for each trading edge (e.g., BTC→ETH)
- Scores cycles based on past profitability and execution success
- Automatically rejects cycles with poor historical performance (score < 1.0)
- Updates predictions using gradient descent on profit errors
- Persists learned state across sessions in `logs/gnn_state.json`

## Safety and Risk Management

### Built-in Protections

- **Position Limits**: Maximum position size per trade
- **Profit Thresholds**: Only execute above minimum profit percentage
- **Latency Checks**: Reject stale data or slow execution
- **Depth Validation**: Ensure sufficient liquidity before execution
- **Slippage Estimation**: Account for market impact
- **GNN Cycle Filtering**: Automatically blocks cycles with poor historical performance
- **Paper Trading**: Test strategies without risk

### Live Trading Safety

When running live trading, the system:

1. ✅ Validates API credentials
2. ⚠️ Requires double confirmation (`YES`)
3. 🔒 Uses exchange-specific position limits
4. 📊 Logs all execution attempts
5. ⏸️ Can be stopped with Ctrl+C (clean shutdown)

### Testing Before Live Trading

Always test in paper mode first:

```bash
# Run paper trading with debug output
VERBOSITY=debug python run_clean.py 1

# Test with small position sizes
MAX_POSITION_SIZE=10 MIN_PROFIT_THRESHOLD=1.0 python run_clean.py 1

# Run for short duration to verify configuration
RUN_MIN=1 python run_clean.py 1
```

## Machine Learning: GNN Cycle Optimizer

The system includes a Graph Neural Network (GNN) optimizer that learns from trade execution history to improve cycle selection.

### How It Works

The GNN optimizer:
1. **Learns from Every Trade**: Records expected vs. actual profit for each executed cycle
2. **Tracks Edge Performance**: Maintains success rates for each trading pair edge (e.g., BTC→ETH success rate)
3. **Scores Cycles**: Assigns a score to each potential cycle based on historical performance
4. **Filters Bad Cycles**: Automatically rejects cycles with score < 1.0 before execution
5. **Adapts Over Time**: Uses gradient descent to update predictions based on profit errors

### Configuration

The GNN optimizer is **enabled by default** and requires no configuration. To disable it, modify your strategy config:

```yaml
# In your strategy configuration
enable_gnn_optimizer: false  # Disable GNN scoring
```

### Data Persistence

GNN state is stored in `logs/gnn_state.json` and includes:
- Edge weights for each currency pair transition
- Success rate per edge
- Historical profit predictions per cycle
- Node features (trade counts, average profits)

### Example GNN Behavior

```python
# First trades (no history)
USDT→BTC→ETH→USDT: score = 1.0 (neutral, will execute)

# After 3 successful trades (+1.5% profit each)
USDT→BTC→ETH→USDT: score = 1.12 (good history, will execute)

# After 3 failed trades (-0.5% loss each)
USDT→DOGE→SHIB→USDT: score = 0.45 (poor history, REJECTED)
```

### Monitoring GNN Performance

```bash
# Run test to verify GNN is working
python tests/integration/test_gnn_scoring.py

# Expected output:
# GNN TEST: PASS
```

### Failure Analysis

The system also tracks cycle failure patterns:

```python
from triangular_arbitrage.execution_engine import StateManager

# Analyze recent failures
state_manager = StateManager()
failures = await state_manager.analyze_failures()
# Returns: {"GNN score too low": 12, "Insufficient depth": 8, ...}

# Get failure trends over time
trends = await state_manager.get_failure_trends()
# Returns: {"2025-10-10": {"GNN score too low": 5}, ...}
```

## Advanced Usage

### Custom Symbol Selection

Focus on specific trading pairs:

```bash
# Only trade major cryptocurrencies
SYMBOL_ALLOWLIST=BTC,ETH,SOL,AVAX,LINK \
TRIANGLE_BASES=USDT,USDC \
python run_clean.py 1
```

### Performance Optimization

Optimize for speed and efficiency:

```bash
# Reduce polling interval for faster detection
POLL_SEC=5 \
DEPTH_LEVELS=10 \
python run_clean.py 1
```

### Debug and Analysis

Enable detailed logging:

```bash
# Debug mode with full output
VERBOSITY=debug \
SHOW_DELTA=true \
REASON_BUCKETS=true \
python run_clean.py 1
```

## Troubleshooting

### Common Issues

**No opportunities found**
- Lower `MIN_PROFIT_THRESHOLD` to see more opportunities
- Increase `DEPTH_LEVELS` for better liquidity analysis
- Expand `SYMBOL_ALLOWLIST` to include more currencies

**Execution failures**
- Check API credentials are correct
- Verify exchange has sufficient balance
- Reduce `MAX_POSITION_SIZE` to avoid minimum order issues
- Check `MAX_LEG_LATENCY_MS` isn't too strict

**High rejection rate**
- Review rejection reasons with `REASON_BUCKETS=true`
- Adjust `MIN_PROFIT_THRESHOLD` if mostly threshold rejects
- Increase depth levels if mostly depth rejects
- Check fee calculations if mostly fee rejects

### Performance Issues

**Slow scanning**
- Reduce `DEPTH_LEVELS` (20 → 10)
- Decrease number of markets with `SYMBOL_ALLOWLIST`
- Increase `POLL_SEC` for less frequent scans

**Memory usage**
- The system clears the database on startup
- Old logs can be archived or deleted
- Consider reducing `EV_WINDOW` size

## Development

### Project Structure

```
Triangular-Arbitrage/
├── run_clean.py               # Main entry point
├── trading_arbitrage.py       # Core trading engine
├── fresh_arbitrage.py         # Alternative detector implementation
├── triangular_arbitrage/      # Package modules
│   ├── execution_helpers.py   # Helper functions
│   ├── execution_engine.py    # Strategy execution
│   ├── detector.py            # Opportunity detection
│   ├── risk_controls.py       # Risk management
│   ├── gnn_optimizer.py       # GNN cycle scoring (ML)
│   └── metrics.py             # Performance tracking
├── logs/                      # Output logs and data
│   ├── equity_timeseries.csv  # Portfolio tracking
│   ├── gnn_state.json         # GNN model state
│   └── trades_*.csv           # Trade history
├── tests/                     # Test suite
│   └── integration/
│       └── test_gnn_scoring.py  # GNN integration test
└── .env                       # Configuration (not in repo)
```

### Testing

```bash
# Run test suite
pytest

# Run with coverage
pytest --cov=triangular_arbitrage

# Run specific tests
pytest tests/unit/
pytest tests/integration/

# Test GNN optimizer
python tests/integration/test_gnn_scoring.py
```

### Contributing

1. Test changes in paper mode first
2. Run linting: `flake8 --max-line-length=127`
3. Ensure tests pass: `pytest`
4. Update documentation as needed

## License

[Add your license information here]

## Disclaimer

**⚠️ IMPORTANT: This software is for educational purposes only.**

- Cryptocurrency trading carries substantial risk of loss
- Past performance does not guarantee future results
- Always test thoroughly in paper mode before live trading
- Never trade with money you cannot afford to lose
- The authors assume no liability for financial losses
- Use at your own risk

## DEX/MEV Arbitrage

The system now includes support for decentralized exchange (DEX) arbitrage on Ethereum mainnet.

### Features
- **Uniswap V2 Cross-DEX**: Arbitrage between Uniswap V2 and SushiSwap
- **Paper Trading Mode**: Test strategies with real on-chain data (no wallet needed)
- **Realistic Modeling**: Accurate fee calculation, gas costs, and price impact
- **High Precision Math**: Decimal-based calculations for accuracy
- **Grid Search Optimization**: Finds optimal trade size across liquidity constraints

### Quick Start

```bash
# 1. Get a free RPC endpoint (Infura/Alchemy/etc)
# Sign up at https://infura.io or https://alchemy.com

# 2. Add to .env
RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY

# 3. Run paper trading
python run_dex.py
```

### Configuration

All settings in `.env`:

```bash
# RPC Configuration
RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY

# Gas Settings
GAS_PRICE_GWEI=12      # Current gas price (check etherscan.io)
GAS_LIMIT=180000       # Estimated gas for dual swap

# Trading Parameters
START_CASH_USDC=1000   # Starting capital (paper mode)
GRID_LO_USDC=10        # Minimum trade size
GRID_HI_USDC=10000     # Maximum trade size
GRID_STEPS=40          # Optimization granularity

# Scan Settings
SCAN_SEC=10            # Seconds between scans
```

### Example Output

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

### Pool Addresses (Ethereum Mainnet)

The system monitors these pools:
- **Uniswap V2 USDC/WETH**: `0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc`
- **SushiSwap USDC/WETH**: `0x397FF1542f962076d0BFE58eA045FfA2d347ACa0`

### Economics

**Fees:**
- Uniswap V2: 0.30% per swap
- SushiSwap: 0.30% per swap
- **Total round-trip**: 0.60% (buy + sell)

**Gas Costs:**
- Typical: ~180k gas
- At 12 gwei + $3000 ETH: ~$0.12 per arbitrage

**Breakeven:**
- Need gross profit > 0.60% + gas cost
- Example: $250 trade needs >$1.50 gross + $0.12 gas = $1.62 profit

### Next Steps

See `triangular_arbitrage_dex/README.md` for:
- Adding more pool pairs
- Uniswap V3 integration
- Multi-hop routes
- Live execution setup

## DEX Paper Trading (New V2 Scanner)

A lightweight, standalone DEX arbitrage paper trading scanner for cross-venue opportunities. This is a **console-based** tool that scans Uniswap V2-style pools across multiple DEXes in real-time.

### Features

- **Cross-DEX Arbitrage**: Find price differences between Uniswap, SushiSwap, BaseSwap, etc.
- **V2 Constant-Product Math**: Accurate swap simulation with fees embedded
- **Paper Mode Only**: No wallet needed, no transaction submission
- **Console UX**: Matches the CEX runner's "Scan N" style output
- **Configurable**: YAML-based config for tokens, DEXes, and parameters
- **Depth Guards**: Automatically rejects trades >10% of pool reserves
- **EMA Tracking**: Tracks EMA15 of gross/net profits over scans
- **Gas Awareness**: Optional gas cost override for realistic P&L

### Installation

```bash
# Install dependencies (web3, pyyaml already in requirements.txt)
pip install -r requirements.txt
```

### Configuration

1. **Copy the example config:**
   ```bash
   cp configs/dex_mev.example.yaml configs/dex_mev.yaml
   ```

2. **Edit `configs/dex_mev.yaml`:**
   ```yaml
   # RPC endpoint
   rpc_url: "https://mainnet.base.org"

   # Scanning
   poll_sec: 6
   once: false  # Set true for single scan (testing)

   # Trading parameters
   usd_token: "USDC"
   max_position_usd: 1000
   slippage_bps: 5  # 0.05% slippage cushion
   threshold_net_pct: 0.0  # Minimum net profit %

   # Gas (optional override)
   gas_price_gwei: 0.5
   gas_limit: 220000
   # gas_cost_usd_override: 0.05  # Uncomment to subtract per cycle

   # Tokens
   tokens:
     WETH:
       address: "0x4200000000000000000000000000000000000006"
       decimals: 18
     USDC:
       address: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
       decimals: 6

   # DEXes (replace placeholder addresses with real pool contracts!)
   dexes:
     - name: "uniswap"
       kind: "v2"
       fee_bps: 30
       pairs:
         - name: "WETH/USDC"
           address: "0xYOUR_UNISWAP_PAIR_ADDRESS"
           base: "WETH"
           quote: "USDC"
     - name: "sushiswap"
       kind: "v2"
       fee_bps: 30
       pairs:
         - name: "WETH/USDC"
           address: "0xYOUR_SUSHI_PAIR_ADDRESS"
           base: "WETH"
           quote: "USDC"
   ```

3. **Find real pool addresses:**
   - Go to BaseScan, Etherscan, or the DEX's interface
   - Search for the pair (e.g., "WETH/USDC pool")
   - Copy the pair contract address (not the router!)

### Running the Scanner

```bash
# Run continuous scanning (via unified interface)
python run_clean.py dex

# Use custom config
python run_clean.py dex --config configs/dex_mev.yaml

# Single scan (for testing/CI)
python run_clean.py dex --once

# Quiet mode (less verbose output)
python run_clean.py dex --quiet --once

# Or use the direct runner (advanced)
python3 run_dex_paper.py --config configs/dex_mev.yaml --quiet --once
```

### Example Output

```
================================================================================
📝 DEX PAPER MODE — scanning for cross-DEX arbitrage
================================================================================
🔍 Pools: 4 | Poll: 6s | Once: False
💰 Size: $1000 | Threshold: 0.10% NET
   (need gross ≥ 0.20% = thr(0.10%) + slip(0.05%) + gas(0.05%))
================================================================================

🔍 Scan 1
--------------------------------------------------------------------------------
   1. USDC -> WETH (uniswap) -> USDC (sushiswap) [WETH/USDC]: gross=+0.42% slip=0.05% gas=0.05% net=+0.32%
   2. USDC -> WETH (baseswap) -> USDC (uniswap) [WETH/USDC]: gross=+0.28% slip=0.05% gas=0.05% net=+0.18%
   3. USDC -> WETH (sushiswap) -> USDC (baseswap) [WETH/USDC]: gross=+0.15% slip=0.05% gas=0.05% net=+0.05%

  → 3 above 0.10% threshold | EMA15 g=+0.42% n=+0.32% | cycles=6 | size≈$1000 hyp_P&L=$9.60 | EV/scan=$3.20
--------------------------------------------------------------------------------

🔍 Scan 2
--------------------------------------------------------------------------------
   1. USDC -> WETH (uniswap) -> USDC (sushiswap) [WETH/USDC]: gross=+0.08% slip=0.05% gas=0.05% net=-0.02%

  ✗ why: best_net=-0.02% (< thr by -0.12%), gross=+0.08% – slip=0.05% gas=0.05%

  → 0 above 0.10% threshold | EMA15 g=+0.25% n=+0.15% | cycles=6 | size≈$1000 hyp_P&L=$0.00 | EV/scan=$1.60
--------------------------------------------------------------------------------
```

### How It Works

1. **Fetch Reserves**: Calls `getReserves()` on all configured V2 pairs
2. **Normalize Orientation**: Flips reserves if needed to match config's (base, quote)
3. **Simulate Cycles**: For each pair of venues with matching pairs:
   - Direction 1: Buy base on Dex A, sell base on Dex B
   - Direction 2: Buy base on Dex B, sell base on Dex A
4. **Constant Product Formula**:
   ```
   amountInWithFee = amountIn * (1 - fee)
   amountOut = (amountInWithFee * reserveOut) / (reserveIn + amountInWithFee)
   ```
5. **Apply Costs**:
   - Slippage haircut on final proceeds
   - Gas cost (if override set)
6. **Rank & Print**: Top 10 by net profit, with "why" line if below threshold

### Breakeven Calculation

```
breakeven_gross = threshold_net_pct + slippage_pct + gas_pct
```

Example:
- Threshold: 0.10%
- Slippage: 0.05%
- Gas: $0.50 / $1000 = 0.05%
- **Breakeven: 0.20% gross**

### Depth Guard

Trades consuming >10% of a pool's reserves are automatically rejected to prevent excessive slippage. Adjust `MAX_DEPTH_FRACTION` in `dex/runner.py` if needed.

### Testing

```bash
# Run unit tests
pytest tests/test_dex_paper.py -v

# Single scan for smoke test
python3 run_dex_paper.py --once

# Test with mock config
python3 -c "from dex.config import load_config; print(load_config('configs/dex_mev.yaml'))"
```

### Notes

- **Paper mode only**: No transactions will be submitted
- **V2 only**: V3 support is stubbed for future implementation
- **RPC rate limits**: Use a paid RPC provider for high-frequency scanning
- **Fees are embedded**: Pool fees are part of the swap math, not deducted separately
- **Gas is informational**: Unless `gas_cost_usd_override` is set, gas doesn't affect net%

### Roadmap

- [ ] Uniswap V3 support (Quoter integration)
- [ ] Multi-hop routes (A→B→C→D)
- [ ] Sandwich detection
- [ ] JIT liquidity monitoring
- [ ] Liquidation opportunities
- [ ] Live execution mode (wallet integration)

### Configuration Examples

See `configs/dex_mev.example.yaml` for:
- Multi-chain setups (Ethereum, Base, Arbitrum)
- Multiple token pairs
- Custom fee tiers
- Gas cost overrides

## Documentation

This project includes comprehensive documentation to help you get started and make the most of the system.

### 📚 Available Guides

| Document | Description |
|----------|-------------|
| **[README.md](README.md)** | Main documentation covering installation, configuration, and usage |
| **[TRADING_SETUP.md](TRADING_SETUP.md)** | Step-by-step guide for setting up live trading with API keys and safety configurations |
| **[WEB_DASHBOARD_README.md](WEB_DASHBOARD_README.md)** | Web interface setup and deployment guide (FastAPI + React) |
| **[DASHBOARD_FEATURES.md](DASHBOARD_FEATURES.md)** | Detailed web dashboard features, usage instructions, and API endpoints |
| **[CHANGELOG.md](CHANGELOG.md)** | Version history and release notes |
| **[CHANGELOG_v1.3.0.md](CHANGELOG_v1.3.0.md)** | Detailed changes for v1.3.0 (performance optimizations) |
| **[PR_TEMPLATE.md](PR_TEMPLATE.md)** | Pull request template for contributors |
| **[PR_READY_CHECKLIST.md](PR_READY_CHECKLIST.md)** | Pre-submission checklist for pull requests |

### 🎯 Quick Navigation

**Getting Started**
- New to the project? Start with [README.md](README.md) Quick Start section
- Want to trade with real money? See [TRADING_SETUP.md](TRADING_SETUP.md)
- Prefer a visual interface? Check [WEB_DASHBOARD_README.md](WEB_DASHBOARD_README.md)

**Configuration & Usage**
- Configuration options: See "Configuration" section in [README.md](README.md)
- Live trading safety: [TRADING_SETUP.md](TRADING_SETUP.md) Section 2 & 8
- Web dashboard controls: [DASHBOARD_FEATURES.md](DASHBOARD_FEATURES.md)

**Advanced Topics**
- GNN Machine Learning: [README.md](README.md) "Machine Learning: GNN Cycle Optimizer" section
- DEX/MEV Arbitrage: [README.md](README.md) "DEX/MEV Arbitrage" section
- Performance optimizations: [CHANGELOG_v1.3.0.md](CHANGELOG_v1.3.0.md)

**Development**
- Project structure: [README.md](README.md) "Development" section
- Version history: [CHANGELOG.md](CHANGELOG.md)
- Contributing: [PR_TEMPLATE.md](PR_TEMPLATE.md)

### 🛠️ Additional Resources

**Training Tools**
```bash
# GNN training and monitoring helper script
./train_gnn.sh
```

**Configuration Examples**
- `.env.example` - Environment variable template
- `configs/dex_mev.example.yaml` - DEX arbitrage configuration
- `configs/strategies/` - Strategy configuration examples

**Logs and Data**
- `logs/equity_timeseries.csv` - Portfolio value over time
- `logs/gnn_state.json` - Machine learning model state
- `logs/trades_*.csv` - Trade execution history

## Support

For issues, questions, or contributions:
- Review the [documentation guides](#documentation) above
- Check the [troubleshooting section](#troubleshooting)
- Review code comments and docstrings
- Test in paper mode to understand behavior
