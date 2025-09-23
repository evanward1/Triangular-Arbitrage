# Lightning-Fast Triangular Arbitrage Trading System

A professional-grade cryptocurrency arbitrage trading system that automatically scans 1,920+ triangular arbitrage opportunities and executes profitable trades immediately using real-time market data from major exchanges including Coinbase Advanced Trading API.

## Problem

Finding and executing profitable triangular arbitrage opportunities in volatile cryptocurrency markets presents several challenges:

- **Speed Requirements**: Arbitrage windows close rapidly, requiring automated execution
- **Risk Management**: Manual trading carries high risks of execution errors and capital loss
- **Technical Complexity**: Multi-leg transactions require sophisticated order management and failure recovery
- **Market Constraints**: Each exchange has unique rules for minimum order sizes, available trading pairs, and API limitations

## Solution

This system provides a lightning-fast, professional-grade arbitrage engine that:

- **⚡ Lightning Execution**: Executes profitable trades IMMEDIATELY when found (no ranking delays that kill opportunities)
- **🔍 Massive Coverage**: Scans 1,920+ triangular arbitrage combinations from 329 currencies across major exchanges
- **💰 Smart Profit Hunting**: Executes ALL profitable opportunities, not just the "best" one
- **🛡️ Risk Management**: Comprehensive controls including profit thresholds, position limits, and automatic loss prevention
- **🚀 Native API Integration**: Direct Coinbase Advanced Trading API support with proper credential handling

## Unique Value Proposition

Unlike basic arbitrage tools, this system offers:

- **⚡ Real-Time Execution**: Trades execute within seconds of opportunity detection (no scanning delays)
- **🎯 Professional-Grade Coverage**: Automatically generates and scans 1,920 triangular arbitrage cycles from all available markets
- **🏦 Native Exchange Support**: Direct Coinbase Advanced Trading API integration with proper credential handling
- **💎 Intelligent Profit Capture**: Executes ALL profitable opportunities simultaneously, maximizing returns
- **🛡️ Enterprise Risk Management**: Multi-layered protection with profit thresholds, position limits, and emergency controls
- **📊 Complete Transparency**: Real-time profit calculations and execution logging for full trade visibility

## Installation

### Prerequisites

Ensure you have Python 3.8+ installed, then install dependencies:

```bash
pip install -r requirements.txt
```

**Key Dependencies:**
- `pyyaml` - Strategy configuration processing
- `coinbase-advanced-py` - Native Coinbase Advanced Trading API
- `ccxt` - Multi-exchange support (Kraken, Binance, etc.)

### Setup

1. **Configure API Access**: Create a `.env` file in the project root with your Coinbase Advanced Trading credentials:

```env
EXCHANGE_API_KEY="organizations/your-org-id/apiKeys/your-key-id"
EXCHANGE_API_SECRET="-----BEGIN EC PRIVATE KEY-----\nYourPrivateKeyHere\n-----END EC PRIVATE KEY-----\n"
```

2. **Generate Arbitrage Opportunities**: Create comprehensive cycle files:

```bash
# Generate 1,920+ triangular arbitrage cycles from all Coinbase markets
python generate_all_cycles.py

# This creates:
# - coinbase_cycles_priority.csv (500 liquid token cycles)
# - coinbase_cycles_massive.csv (1,000 diverse cycles)
# - coinbase_cycles_complete.csv (all 1,920 cycles)
```

3. **Choose Strategy Configuration**: Use pre-configured strategies or create custom ones.

## Usage

### Quick Start

⚡ **Lightning Arbitrage Mode** - Execute ALL profitable opportunities immediately:

```bash
# Safe testing: Scan 500 cycles, execute up to 10 profitable trades
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run --cycles 10

# Live trading: Execute up to 5 profitable opportunities
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --cycles 5

# Comprehensive scan: Test with 1,000+ cycles (use priority file for speed)
python run_strategy.py --strategy configs/strategies/strategy_massive.yaml --dry-run --cycles 20
```

🎯 **The system will:**
1. Scan cycles sequentially for profitable opportunities
2. Execute trades IMMEDIATELY when profit ≥ threshold (default 7 basis points)
3. Continue hunting until max executions reached or cycles exhausted
4. Log real-time profit calculations and execution details

### Configuration

Strategy configurations use YAML files in `configs/strategies/`. Lightning arbitrage parameters:

**Core Settings:**
- `exchange`: `coinbase` (uses native Advanced Trading API) or `kraken`/`binance` (via ccxt)
- `trading_pairs_file`: Path to cycle file (`coinbase_cycles_priority.csv` for 500 cycles, `coinbase_cycles_massive.csv` for 1,000)
- `min_profit_bps`: Minimum profit threshold (default: 7 basis points = 0.07%)
- `capital_allocation`: Position sizing controls

**Lightning Arbitrage Configuration:**

```yaml
name: lightning_arbitrage
exchange: coinbase
trading_pairs_file: data/cycles/coinbase_cycles_priority.csv  # 500 high-liquidity cycles
min_profit_bps: 7        # Execute trades with ≥0.07% profit
max_slippage_bps: 9      # Maximum acceptable slippage
capital_allocation:
  mode: fixed_fraction
  fraction: 0.6          # Use 60% of available balance per trade
risk_controls:
  max_open_cycles: 3     # Max concurrent positions
  stop_after_consecutive_losses: 4
```

**Cycle File Options:**
- `coinbase_cycles_priority.csv` - 500 liquid token cycles (recommended for speed)
- `coinbase_cycles_massive.csv` - 1,000 diverse cycles (comprehensive coverage)
- `coinbase_cycles_complete.csv` - All 1,920 cycles (maximum opportunities)

### Monitoring

Monitor active trading cycles and system status:

```bash
# View currently active cycles
python monitor_cycles.py --active

# Review trading history
python monitor_cycles.py --history 20

# Examine specific cycle details
python monitor_cycles.py --details cycle_id_here

# Clean up old records
python monitor_cycles.py --cleanup 7
```

### Safe Testing

**Always test strategies before live trading:**

```bash
# Comprehensive dry run with full simulation
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run --log-level DEBUG

# Test recovery mechanisms
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run --recover

# Validate configuration without execution
python run_strategy.py --strategy configs/strategies/new_strategy.yaml --dry-run --cycles 1
```

## Key Features

### ⚡ Lightning Arbitrage Engine
- **Immediate Execution**: Trades execute within seconds of profitable opportunity detection
- **Zero Ranking Delays**: No time wasted sorting opportunities - executes profitable trades instantly
- **Massive Coverage**: Scans 1,920+ triangular arbitrage combinations across 329 currencies
- **Smart Profit Capture**: Executes ALL profitable opportunities (not just the "best" one)
- **Real-Time Profit Calculation**: Live basis point calculations with fee accounting

### 🏦 Native Exchange Integration
- **Coinbase Advanced Trading API**: Direct integration with proper credential handling
- **Multi-Exchange Support**: CCXT integration for Kraken, Binance, and other exchanges
- **Automatic Market Loading**: Real-time access to 793+ trading pairs
- **Optimized API Usage**: Efficient market data fetching and order execution

### 🛡️ Professional Risk Management
- **Profit Thresholds**: Configurable minimum profit requirements (default: 7 basis points)
- **Position Limits**: Maximum concurrent cycle limits and capital allocation controls
- **Loss Protection**: Automatic shutdown after consecutive losses
- **Pre-Trade Validation**: Ensures sufficient funds and valid markets before execution

### 📊 Advanced Monitoring & Analytics
- **Real-Time Logging**: Complete trade execution visibility with profit calculations
- **Progress Tracking**: Live scanning progress with profitable opportunity counts
- **Comprehensive Audit Trail**: Complete history of all trades and decisions
- **Debug Capabilities**: Detailed execution logging for optimization and troubleshooting

## Command Reference

### run_strategy.py
⚡ **Lightning Arbitrage Engine** - Execute profitable opportunities immediately.

**Arguments:**
- `--strategy PATH`: Path to YAML strategy configuration (required)
- `--cycles N`: Maximum profitable trades to execute (default: 1)
- `--dry-run`: Safe testing mode (no real money at risk)
- `--recover`: Attempt to recover any active cycles from previous sessions
- `--log-level LEVEL`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR)

**Lightning Arbitrage Examples:**
```bash
# Execute up to 10 profitable opportunities (recommended for active trading)
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --cycles 10

# Safe testing with comprehensive logging
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run --cycles 5 --log-level INFO

# Maximum opportunity scanning (use priority cycles for speed)
python run_strategy.py --strategy configs/strategies/strategy_massive.yaml --dry-run --cycles 20
```

**What Happens:**
1. System scans cycles sequentially for profitable opportunities
2. Executes trades IMMEDIATELY when profit ≥ min_profit_bps threshold
3. Continues hunting until max executions reached or cycles exhausted
4. Logs real-time profit calculations and execution details

### generate_all_cycles.py
🔍 **Massive Opportunity Generator** - Create comprehensive arbitrage cycle files.

**Purpose:** Automatically generates thousands of triangular arbitrage combinations from all available exchange markets.

**Usage:**
```bash
# Generate all possible triangular arbitrage cycles from Coinbase
python generate_all_cycles.py
```

**Output Files:**
- `coinbase_cycles_priority.csv` - 500 high-liquidity token cycles (recommended)
- `coinbase_cycles_massive.csv` - 1,000 diverse token combinations
- `coinbase_cycles_complete.csv` - All 1,920 possible cycles

**What It Does:**
1. Connects to Coinbase Advanced Trading API
2. Loads all 793 available trading pairs
3. Identifies 329 unique currencies
4. Generates all valid triangular arbitrage combinations
5. Prioritizes liquid tokens (BTC, ETH, USDT, etc.) for optimal execution

### monitor_cycles.py
Monitor and manage trading cycle states.

**Arguments:**
- `--active`: Display all currently active cycles
- `--history N`: Show last N completed cycles (default: 20)
- `--details ID`: Show detailed information for specific cycle
- `--cleanup N`: Remove cycle records older than N days (default: 7)

**Examples:**
```bash
python monitor_cycles.py --active
python monitor_cycles.py --history 50
python monitor_cycles.py --cleanup 30
```

## Architecture

The system follows a modular architecture with clear separation of concerns:

```
StrategyExecutionEngine (Orchestrator)
├── StateManager (Persistent Storage)
├── ConfigurationManager (YAML Processing)
├── OrderManager (Trade Execution)
└── FailureRecoveryManager (Error Handling)
```

Each component is independently testable and can be configured through the strategy files.

## Risk Management

The system implements multiple layers of risk protection:

1. **Pre-Trade Validation**: Verifies sufficient balances, valid markets, and minimum order requirements
2. **Position Limits**: Enforces maximum position sizes and concurrent cycle limits
3. **Loss Protection**: Automatic shutdown after configurable consecutive losses
4. **Emergency Procedures**: Panic-sell mechanism for immediate position liquidation
5. **State Persistence**: Maintains complete trade history for audit and recovery

## Troubleshooting

### Common Issues

**"Risk controls violated"**: Check consecutive loss count and active cycle limits in your strategy configuration.

**"Cycle validation failed"**: Verify that your account has sufficient balance and that all trading pairs are available on the exchange.

**"Strategy file not found"**: Ensure the path to your YAML configuration file is correct and the file exists.

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
python run_strategy.py --strategy config.yaml --log-level DEBUG --dry-run
```

## Contributing

This project follows standard development practices:

1. All changes should be tested in dry-run mode first
2. Configuration changes are preferred over code modifications
3. Maintain backward compatibility with existing strategy files
4. Add comprehensive logging for new features

## License

[Add your license information here]

## Support

For questions or issues:
1. Check the execution logs and monitor active cycles
2. Review the detailed documentation in `EXECUTION_ENGINE_DOCS.md`
3. Test problematic configurations in dry-run mode with DEBUG logging