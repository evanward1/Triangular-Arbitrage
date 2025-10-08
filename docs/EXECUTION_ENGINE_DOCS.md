# Robust Strategy Execution Engine Documentation

> **⚡ LIGHTNING ARBITRAGE UPDATE**: This documentation covers the legacy execution engine. The system now features **Lightning Arbitrage Mode** with immediate execution of profitable opportunities. See `README.md` for the latest lightning arbitrage capabilities including real-time scanning of 1,920+ cycles and immediate execution.

## Overview

The Strategy Execution Engine provides a fault-tolerant, configuration-driven system for executing cryptocurrency arbitrage cycles. This engine works alongside the new Lightning Arbitrage Mode for comprehensive trading capabilities.

## Key Features

### 1. Configuration-Driven Execution
- All parameters loaded from YAML strategy files
- No hardcoded values
- Dynamic strategy switching
- Support for multiple concurrent strategies

### 2. Robust State Management
- Persistent state storage using SQLite
- Automatic recovery after crashes
- Track cycle states: `pending`, `validating`, `active`, `partially_filled`, `completed`, `failed`, `recovering`, `panic_selling`
- Complete audit trail of all trades

### 3. Advanced Order Management
- Automatic retries with exponential backoff
- Real-time order status monitoring
- Partial fill handling
- Slippage calculation and control
- Support for market and limit orders

### 4. Intelligent Failure Recovery
- Panic sell mechanism to minimize losses
- Automatic conversion to stable base currencies (USDC, USD, USDT)
- Multi-hop routing when direct paths unavailable
- Configurable retry logic

### 5. Risk Controls
- Maximum open cycles limit
- Stop after consecutive losses
- Position size limits
- Daily loss limits
- Pre-trade validation

## Architecture

```
StrategyExecutionEngine (Main Orchestrator)
    ├── StateManager (Persistent Storage)
    │   └── SQLite Database
    ├── ConfigurationManager (YAML Loading)
    │   └── Strategy Configurations
    ├── OrderManager (Trade Execution)
    │   ├── Order Placement
    │   ├── Status Monitoring
    │   └── Retry Logic
    └── FailureRecoveryManager (Error Handling)
        ├── Panic Sell
        └── Recovery Mechanisms
```

## Usage

### Basic Usage (Backward Compatible)

The engine maintains backward compatibility with the original interface:

```python
from triangular_arbitrage.trade_executor import execute_cycle

# Works exactly like before
await execute_cycle(exchange, cycle, initial_amount, is_dry_run=False)
```

### Advanced Usage with Configuration

```python
from triangular_arbitrage.execution_engine import (
    StrategyExecutionEngine,
    ConfigurationManager
)

# Load strategy configuration
config_manager = ConfigurationManager()
config = config_manager.load_strategy('configs/strategies/strategy_1.yaml')

# Create engine
engine = StrategyExecutionEngine(exchange, config)

# Recover any active cycles (after restart)
await engine.recover_active_cycles()

# Execute new cycle
cycle_info = await engine.execute_cycle(
    cycle=['BTC', 'ETH', 'USDT'],
    initial_amount=1000.0
)
```

### Command-Line Execution

Run a strategy from the command line:

```bash
# Execute strategy with recovery
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --recover

# Execute multiple cycles
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --cycles 5

# Dry run simulation
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run
```

### Monitoring

Monitor active and historical cycles:

```bash
# Show active cycles
python monitor_cycles.py --active

# Show cycle history
python monitor_cycles.py --history 50

# Show specific cycle details
python monitor_cycles.py --details cycle_id_here

# Clean up old records
python monitor_cycles.py --cleanup 30
```

## Configuration Reference

### Minimal Configuration

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

### Full Configuration

See `configs/strategies/strategy_robust_example.yaml` for all available options.

## State Persistence

The engine stores all cycle states in `trade_state.db` (SQLite database). This includes:

- Cycle ID and strategy name
- Current state and step
- All orders with their status
- Current holdings
- Error messages
- Execution timestamps
- Profit/loss calculations

### Database Schema

```sql
CREATE TABLE cycles (
    id TEXT PRIMARY KEY,           -- Unique cycle identifier
    strategy_name TEXT,             -- Strategy configuration name
    cycle_json TEXT,                -- JSON array of currencies
    initial_amount REAL,            -- Starting amount
    current_amount REAL,            -- Current holdings
    current_currency TEXT,          -- Current currency held
    state TEXT,                     -- Cycle state enum
    current_step INTEGER,           -- Current position in cycle
    orders_json TEXT,               -- JSON array of orders
    start_time REAL,                -- Unix timestamp
    end_time REAL,                  -- Unix timestamp
    profit_loss REAL,               -- Final P/L
    error_message TEXT,             -- Error details
    metadata_json TEXT,             -- Additional metadata
    updated_at REAL                 -- Last update timestamp
)
```

## Panic Sell Mechanism

When a cycle fails mid-execution, the panic sell mechanism automatically:

1. Identifies the current holdings
2. Finds the best path to a stable base currency
3. Executes market orders for immediate conversion
4. Minimizes losses by accepting configured slippage

### Routing Priority

1. Direct conversion to base currency (e.g., ETH/USDC)
2. Two-hop conversion through major pairs (e.g., ALT → BTC → USDC)
3. Multi-hop routing through liquidity pools

## Recovery After Restart

The engine automatically recovers active cycles after a restart:

1. Loads all active cycles from the database
2. Validates current exchange state
3. Attempts to complete partially executed cycles
4. Applies panic sell if cycles cannot be completed

## Error Handling

The engine handles various failure scenarios:

- **Network errors**: Automatic retry with exponential backoff
- **Insufficient balance**: Pre-trade validation prevents execution
- **Order rejection**: Retry with adjusted parameters
- **Partial fills**: Continue with actual filled amounts
- **Exchange maintenance**: Pause and retry later
- **Critical errors**: Panic sell to minimize losses

## Performance Considerations

- State persistence adds ~10-50ms overhead per operation
- Recovery check on startup takes ~100-500ms
- Panic sell execution typically completes in 2-5 seconds
- Database cleanup recommended weekly

## Security Notes

- API credentials should be stored in `.env` file
- Database contains sensitive trading information
- Consider encrypting `trade_state.db` in production
- Implement rate limiting for API calls
- Use read-only API keys when possible

## Migration from Old System

1. The new engine is backward compatible
2. Existing code using `execute_cycle()` will work unchanged
3. Gradually migrate to configuration-driven approach
4. Old dry-run functionality preserved

## Troubleshooting

### Common Issues

1. **"Risk controls violated"**: Check consecutive losses and open cycles
2. **"Cycle validation failed"**: Verify minimum order amounts
3. **"Panic sell failed"**: Ensure base currencies are available
4. **Database locked**: Close other monitoring processes
5. **Strategy not found**: Check YAML file path and syntax

### Debug Mode

Enable debug logging for detailed execution traces:

```bash
python run_strategy.py --strategy config.yaml --log-level DEBUG
```

## Best Practices

1. Always run recovery after unexpected shutdowns
2. Monitor active cycles regularly
3. Set appropriate risk controls for your capital
4. Use dry-run mode for testing new strategies
5. Clean up old database records periodically
6. Keep panic sell enabled for production
7. Use conservative slippage settings initially
8. Test strategies on testnet first

## Support

For issues or questions:
1. Check the logs in the configured log file
2. Review active cycles with `monitor_cycles.py`
3. Examine the database directly if needed
4. Enable DEBUG logging for detailed traces
