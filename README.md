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

**CEX Arbitrage (Centralized Exchanges)**
```bash
# Interactive mode - choose paper or live trading
python run_clean.py

# Paper trading mode (safe simulation)
python run_clean.py 1

# Live trading mode (real money - requires API keys)
python run_clean.py 2
```

**DEX/MEV Arbitrage (Decentralized Exchanges)**
```bash
# Show setup requirements
make dex_setup

# Run paper trading scan (finds 20-40 bps opportunities)
make dex_paper

# Configure for your chain
cp configs/dex_mev.example.yaml configs/dex_mev.yaml
# Edit configs/dex_mev.yaml with your settings
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

The system now includes support for decentralized exchange (DEX) arbitrage with MEV protection.

### Features
- **Ethereum DEX Support**: Uniswap V3 integration via Web3
- **Paper Trading Mode**: Test strategies with mock data
- **Realistic Profits**: 20-40 bps net profit after gas and slippage
- **MEV Protection**: Configurable Flashbots support
- **Multi-Route Detection**: Discovers base → mid → alt → base cycles

### Quick Start

```bash
# Install web3 dependency
pip install web3

# View setup requirements
make dex_setup

# Run paper trading scan
make dex_paper
```

### Configuration

Edit `configs/dex_mev.example.yaml`:

```yaml
chain_id: 1  # Ethereum mainnet
base_asset: "USDC"
min_profit_bps: 10  # 0.1% minimum profit
max_slippage_bps: 10  # 0.1% max slippage
use_flashbots: true  # Enable MEV protection

# Required environment variables
# ETH_RPC_URL - Ethereum RPC endpoint (Alchemy, Infura)
# PRIVATE_KEY - Wallet private key (0x prefixed)
```

### Example Output

```
📊 Found 1 profitable opportunities:

#1 Arbitrage Opportunity - Uniswap V3
Path: USDC → WETH → USDT → USDC
Notional Amount: 1000.0 USDC

  Step 1: 1000.000000 USDC → 0.498500 WETH
  Step 2: 0.498500 WETH → 995.251511 USDT
  Step 3: 995.251511 USDT → 1010.126540 USDC

💰 Gross Profit: 101.27 bps
💸 Net Profit:   41.16 bps (after gas & slippage)
✅ Good opportunity
```

## Support

For issues, questions, or contributions:
- Review this documentation
- Check the troubleshooting section
- Review code comments and docstrings
- Test in paper mode to understand behavior
