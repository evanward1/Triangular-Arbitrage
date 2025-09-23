# Triangular Arbitrage Trading System

A robust, configuration-driven cryptocurrency arbitrage trading system that automatically detects and executes profitable triangular arbitrage opportunities across cryptocurrency exchanges.

## Problem

Finding and executing profitable triangular arbitrage opportunities in volatile cryptocurrency markets presents several challenges:

- **Speed Requirements**: Arbitrage windows close rapidly, requiring automated execution
- **Risk Management**: Manual trading carries high risks of execution errors and capital loss
- **Technical Complexity**: Multi-leg transactions require sophisticated order management and failure recovery
- **Market Constraints**: Each exchange has unique rules for minimum order sizes, available trading pairs, and API limitations

## Solution

This system provides a production-ready, fault-tolerant trading engine that:

- **Automates Discovery**: Continuously scans for profitable arbitrage cycles using efficient graph algorithms
- **Manages Risk**: Implements comprehensive risk controls, position limits, and automatic loss prevention
- **Ensures Reliability**: Features robust state management, automatic recovery, and panic-sell mechanisms
- **Scales Operations**: Supports multiple concurrent strategies with configurable parameters

## Unique Value Proposition

Unlike simple arbitrage scanners, this system offers:

- **Configuration-Driven Architecture**: YAML-based strategy files enable rapid deployment of different trading approaches without code changes
- **Fault Tolerance**: Persistent state storage and automatic recovery ensure continuity after system interruptions
- **Advanced Risk Controls**: Multi-layered protection including consecutive loss limits, position sizing, and emergency liquidation
- **Production Ready**: Comprehensive logging, monitoring, and debugging tools for reliable operation

## Installation

### Prerequisites

Ensure you have Python 3.8+ installed, then install dependencies:

```bash
pip install -r requirements.txt
```

### Setup

1. **Configure API Access**: Create a `.env` file in the project root:

```env
EXCHANGE_API_KEY=your_exchange_api_key
EXCHANGE_API_SECRET=your_exchange_secret_key
```

2. **Choose Strategy Configuration**: Select from pre-configured strategies in `configs/strategies/` or create your own based on the examples.

## Usage

### Quick Start

Execute a strategy with safety features enabled:

```bash
# Test strategy safely (no real trades)
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run

# Execute live strategy with automatic recovery
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --recover

# Run multiple cycles with monitoring
python run_strategy.py --strategy configs/strategies/strategy_robust_example.yaml --cycles 5 --log-level INFO
```

### Configuration

Strategy configurations are stored in YAML files under `configs/strategies/`. Key parameters include:

- **Capital Allocation**: Control position sizing with fixed amounts or portfolio fractions
- **Risk Controls**: Set maximum open positions, consecutive loss limits, and stop conditions
- **Order Management**: Configure order types, retry logic, and partial fill handling
- **Recovery Settings**: Enable panic-sell mechanisms and emergency liquidation paths

Example minimal configuration:

```yaml
name: my_strategy
exchange: binance
trading_pairs_file: data/cycles/binance_cycles.csv
min_profit_bps: 10
max_slippage_bps: 20
capital_allocation:
  mode: fixed_fraction
  fraction: 0.5
```

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

### Robust State Management
- Persistent SQLite database tracking all cycle states
- Automatic recovery after system restarts or crashes
- Complete audit trail of all trades and decisions

### Advanced Risk Controls
- Maximum concurrent cycle limits
- Consecutive loss protection with automatic shutdown
- Pre-trade validation ensuring sufficient funds and valid markets
- Configurable position sizing and capital allocation

### Intelligent Failure Recovery
- Panic-sell mechanism converting positions to stable currencies
- Multi-hop routing for emergency liquidation
- Partial fill handling with configurable behavior
- Exponential backoff retry logic for transient failures

### Configuration-Driven Operation
- YAML-based strategy files for easy modification
- No hardcoded parameters requiring code changes
- Support for multiple concurrent strategies
- Hot-reloading of configuration changes

## Command Reference

### run_strategy.py
Execute trading strategies with full lifecycle management.

**Arguments:**
- `--strategy PATH`: Path to YAML strategy configuration (required)
- `--recover`: Attempt to recover and complete any active cycles
- `--cycles N`: Number of cycles to execute (default: 1)
- `--dry-run`: Simulate execution without real trades
- `--log-level LEVEL`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR)

**Examples:**
```bash
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --recover --log-level INFO
python run_strategy.py --strategy configs/strategies/test.yaml --dry-run --cycles 3
```

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