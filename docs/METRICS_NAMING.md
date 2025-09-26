# Metrics Naming Guide

This document defines the naming conventions and label standards for metrics in the triangular arbitrage system.

## Metric Naming Convention

All metrics should follow this pattern:
```
triangular_arbitrage_<component>_<metric_name>_<unit>
```

### Components

- `detector` - Opportunity detection metrics
- `execution` - Trade execution metrics
- `exchange` - Exchange interaction metrics
- `risk` - Risk management metrics
- `strategy` - Strategy-specific metrics
- `system` - System health metrics

### Units

Common unit suffixes:
- `_total` - Counters (monotonic increasing)
- `_seconds` - Time measurements in seconds
- `_milliseconds` - Time measurements in milliseconds
- `_bytes` - Size measurements
- `_ratio` - Percentage/ratio values (0.0-1.0)
- `_count` - Current count/gauge values

## Standard Labels

All metrics should include these standard labels where applicable:

### Required Labels

- `strategy` - Strategy name (e.g., "triangular_arbitrage")
- `mode` - Execution mode (`live`, `paper`, `backtest`)
- `exchange` - Exchange identifier (e.g., "binance", "coinbase")

### Optional Labels

- `pair` - Trading pair (e.g., "BTC-USDT", "ETH-BTC")
- `side` - Order side (`buy`, `sell`)
- `status` - Status value (`success`, `error`, `timeout`)
- `error_type` - Error classification for error metrics

## Metric Categories

### 1. Detection Metrics

```
triangular_arbitrage_detector_opportunities_total{strategy, mode, exchange}
triangular_arbitrage_detector_scan_duration_seconds{strategy, mode, exchange}
triangular_arbitrage_detector_profit_threshold_ratio{strategy, mode, exchange}
```

### 2. Execution Metrics

```
triangular_arbitrage_execution_cycles_total{strategy, mode, exchange, status}
triangular_arbitrage_execution_duration_seconds{strategy, mode, exchange}
triangular_arbitrage_execution_profit_ratio{strategy, mode, exchange}
triangular_arbitrage_execution_volume_btc{strategy, mode, exchange, pair}
```

### 3. Exchange Metrics

```
triangular_arbitrage_exchange_requests_total{strategy, mode, exchange, status}
triangular_arbitrage_exchange_latency_milliseconds{strategy, mode, exchange}
triangular_arbitrage_exchange_errors_total{strategy, mode, exchange, error_type}
triangular_arbitrage_exchange_rate_limit_remaining{strategy, mode, exchange}
```

### 4. Risk Management Metrics

```
triangular_arbitrage_risk_position_size_ratio{strategy, mode, exchange}
triangular_arbitrage_risk_drawdown_ratio{strategy, mode, exchange}
triangular_arbitrage_risk_violations_total{strategy, mode, exchange, risk_type}
triangular_arbitrage_risk_kill_switch_active{strategy, mode, exchange}
```

### 5. Strategy Metrics

```
triangular_arbitrage_strategy_state{strategy, mode, exchange, state}
triangular_arbitrage_strategy_uptime_seconds{strategy, mode, exchange}
triangular_arbitrage_strategy_cycles_completed_total{strategy, mode, exchange}
triangular_arbitrage_strategy_profit_accumulated_ratio{strategy, mode, exchange}
```

### 6. System Metrics

```
triangular_arbitrage_system_memory_bytes{strategy, mode}
triangular_arbitrage_system_cpu_ratio{strategy, mode}
triangular_arbitrage_system_connections_count{strategy, mode, exchange}
```

## Label Values

### Strategy Names

- Use snake_case for strategy names
- Keep names concise but descriptive
- Examples: `basic_triangular`, `cross_exchange`, `high_frequency`

### Mode Values

- `live` - Production trading with real money
- `paper` - Simulated trading with fake money
- `backtest` - Historical data testing

### Exchange Values

- Use lowercase exchange identifiers
- Examples: `binance`, `coinbase`, `kraken`, `bitfinex`

### Pair Format

- Use dash-separated format: `BASE-QUOTE`
- Examples: `BTC-USDT`, `ETH-BTC`, `ADA-ETH`

### Status Values

- `success` - Operation completed successfully
- `error` - Operation failed with error
- `timeout` - Operation timed out
- `cancelled` - Operation was cancelled
- `partial` - Operation partially completed

## Examples

### Good Metric Names

```python
# Counter for successful arbitrage cycles
triangular_arbitrage_execution_cycles_total{
    strategy="basic_triangular",
    mode="live",
    exchange="binance",
    status="success"
}

# Histogram for execution latency
triangular_arbitrage_execution_duration_seconds{
    strategy="basic_triangular",
    mode="paper",
    exchange="coinbase"
}

# Gauge for current profit
triangular_arbitrage_strategy_profit_accumulated_ratio{
    strategy="cross_exchange",
    mode="live",
    exchange="binance"
}
```

### Bad Metric Names

```python
# Too generic, missing component
arbitrage_count

# Inconsistent naming
triangular_arb_exec_time

# Missing standard labels
execution_duration_seconds{pair="BTC-USDT"}
```

## Implementation Guidelines

1. **Use the constants from `triangular_arbitrage.constants`**:
   ```python
   from triangular_arbitrage.constants import METRICS_CONSTANTS

   METRIC_PREFIX = METRICS_CONSTANTS['METRIC_PREFIX']
   ```

2. **Create metrics with consistent labels**:
   ```python
   metric = Counter(
       f"{METRIC_PREFIX}_execution_cycles_total",
       "Total number of arbitrage cycles executed",
       labelnames=["strategy", "mode", "exchange", "status"]
   )
   ```

3. **Use enums for label values**:
   ```python
   from triangular_arbitrage.constants import ExecutionMode, OrderStatus

   metric.labels(
       strategy="basic_triangular",
       mode=ExecutionMode.LIVE.value,
       exchange="binance",
       status=OrderStatus.FILLED.value
   ).inc()
   ```

## Migration Guide

When updating existing metrics:

1. Add the standard prefix if missing
2. Include required labels (strategy, mode, exchange)
3. Use consistent naming patterns
4. Update dashboards and alerts to use new metric names
5. Keep old metrics for a transition period before removal