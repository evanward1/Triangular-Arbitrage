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
- **🛡️ Advanced Risk Management**: Comprehensive controls including latency safeguards, slippage protection with cooldowns, profit thresholds, position limits, and automatic loss prevention
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

Choose your preferred installation method:

### 🐳 Docker Quick Start (Recommended)

Get started in under 2 minutes with Docker:

```bash
# Clone the repository
git clone <repository-url>
cd Triangular-Arbitrage

# Set up environment variables
cp .env.example .env
# Edit .env with your exchange API credentials

# Start the development environment
make docker-dev

# Run paper trading mode
make docker-test
```

The Docker setup includes:
- ✅ All dependencies pre-installed
- ✅ Prometheus metrics server
- ✅ Grafana dashboards
- ✅ Isolated environment

### 📦 Local Installation

For local development and customization:

```bash
# Clone and setup
git clone <repository-url>
cd Triangular-Arbitrage

# Install dependencies and setup development environment
make setup

# Run tests to verify installation
make test
```

### Prerequisites

- **Docker & Docker Compose** (for Docker installation)
- **Python 3.8+** (for local installation)

**Key Dependencies:**
- `pydantic` - Configuration validation
- `pyyaml` - Strategy configuration processing
- `coinbase-advanced-py` - Native Coinbase Advanced Trading API
- `ccxt` - Multi-exchange support (Kraken, Binance, etc.)
- `prometheus-client` - Metrics and monitoring

### Configuration Setup

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

## Execution Modes

The system supports three distinct execution modes with full feature parity and comprehensive observability:

### 1. **Live Trading** (Production)
Execute real trades on the exchange with actual capital and risk management.

```bash
# Standard live trading
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode live

# With recovery and cooldown resume
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode live --recover --resume
```

**Features:**
- Real order execution with exchange APIs
- Complete risk control integration
- Cooldown state persistence
- Real-time P&L tracking

### 2. **Paper Trading** (Simulation)
Test strategies against live market data without risking capital. Features sophisticated order simulation with realistic slippage and partial fills.

```bash
# Basic paper trading
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode paper

# Paper trading with custom balances
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode paper \
  --paper-balance BTC 2.0 --paper-balance USDT 100000

# Deterministic paper trading for testing
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode paper \
  --random-seed 42 --cycles 10
```

**Advanced Paper Trading Configuration:**
```yaml
execution:
  mode: paper
  paper:
    fee_bps: 30                    # Realistic trading fees
    fill_ratio: 0.95               # 95% fill probability
    spread_padding_bps: 5          # Market spread simulation
    random_seed: 42                # Deterministic testing
    latency_sim_ms: 50             # Simulated network latency

    initial_balances:
      BTC: 1.0
      ETH: 10.0
      USDT: 50000.0

    # Advanced slippage modeling
    slippage_model:
      base_slippage_bps: 2         # Base execution cost
      random_component_bps: 3      # Market noise
      adverse_selection_bps: 1     # Information asymmetry

    # Market impact for large orders
    market_impact:
      enabled: true
      impact_coefficient: 0.1      # bps per $1000 notional
      max_impact_bps: 50

    # Realistic partial fill simulation
    partial_fill_model:
      enabled: true
      min_fill_ratio: 0.3
      fill_time_spread_ms: 500
      large_order_threshold: 1000
```

### 3. **Backtesting** (Historical Analysis)
Deterministic replay of historical market data with comprehensive performance attribution.

```bash
# Standard backtesting
python backtests/run_backtest.py --strategy configs/strategies/strategy_robust_example.yaml

# Extended backtest with custom parameters
python backtests/run_backtest.py \
  --strategy configs/strategies/strategy_robust_example.yaml \
  --max-cycles 100 \
  --random-seed 12345 \
  --data-file data/backtests/custom_feed.csv

# Time-bounded backtest
python backtests/run_backtest.py \
  --strategy configs/strategies/strategy_robust_example.yaml \
  --start-time 1700000000 \
  --end-time 1700010000 \
  --time-acceleration 10.0
```

**Comprehensive Backtest Output:**
```
=== BACKTEST SUMMARY: backtest_1732583470 ===
Strategy: strategy_robust_example
Start Time: 2024-11-25T21:44:30.123456+00:00
End Time: 2024-11-25T21:44:35.987654+00:00
Wall Clock Duration: 5.86s
Simulation Duration: 15.00s

CYCLE STATISTICS
Cycles Started: 42
Cycles Filled: 38
Cycles Partial: 2
Cycles Rejected: 2
Canceled by Slippage: 1
Canceled by Latency: 0
Partials Resolved: 2

PERFORMANCE METRICS
Net P&L: +1,247.850000
Basis Points Captured: +187.3
Win Rate: 90.5%
Profit Factor: 3.45
Max Drawdown: 89.200000
Sharpe Ratio: 2.31
Avg Cycle Duration: 387ms

FINAL BALANCES
BTC: 1.002489
ETH: 4.998734
USDT: 51247.85

CONFIGURATION
Data File: data/backtests/sample_feed.csv
Random Seed: 12345
Fill Probability: 0.98
```

**Advanced Backtesting Configuration:**
```yaml
execution:
  mode: backtest
  backtest:
    data_file: data/backtests/sample_feed.csv
    start_time: null              # Unix timestamp or null
    end_time: null                # Unix timestamp or null
    time_acceleration: 1.0        # Simulation speed multiplier
    random_seed: 12345           # Deterministic execution

    initial_balances:
      BTC: 1.0
      ETH: 5.0
      USDT: 50000.0

    # Sophisticated slippage modeling
    slippage_model:
      base_slippage_bps: 3
      size_impact_coefficient: 0.05  # Market impact scaling
      max_slippage_bps: 100
      random_component_bps: 2

    # Realistic fill behavior
    fill_model:
      fill_probability: 0.98        # Order success rate
      partial_fill_threshold: 1000  # USD threshold for partials
      min_fill_ratio: 0.3          # Minimum partial fill
      max_fill_time_ms: 1000       # Time to complete fills
```
## Monitoring and Observability

The system includes comprehensive monitoring capabilities with Prometheus metrics, Grafana dashboards, and detailed cycle tracking.

### Cycle Monitoring

Monitor trading activity and performance with enhanced cycle tracking:

```bash
# View recent cycle history with execution mode breakdown
python monitor_cycles.py --history 50

# Filter by execution mode
python monitor_cycles.py --history 20 --mode paper
python monitor_cycles.py --history 30 --mode live

# Performance comparison across modes
python monitor_cycles.py --mode-performance

# Execution mode statistics
python monitor_cycles.py --mode-summary

# Active cycles and cooldowns
python monitor_cycles.py --active --cooldowns
```

**Enhanced Monitoring Output:**
```
=== CYCLE HISTORY (Last 20) ===
┌──────────┬──────────┬──────┬────────────┬────────────┬──────────┬─────────────┐
│ Cycle ID │ Strategy │ Mode │ State      │ Start Time │ Duration │ P/L         │
├──────────┼──────────┼──────┼────────────┼────────────┼──────────┼─────────────┤
│ abc123.. │ robust   │ paper│ ✓ completed│ 14:25:33   │ 0.8s     │ +0.000125   │
│ def456.. │ robust   │ live │ ✓ completed│ 14:25:31   │ 1.2s     │ +0.000087   │
│ ghi789.. │ robust   │ paper│ ✗ failed   │ 14:25:29   │ N/A      │ N/A         │
└──────────┴──────────┴──────┴────────────┴────────────┴──────────┴─────────────┘

=== EXECUTION MODE BREAKDOWN ===
┌───────────┬───────┬───────────┬────────┬─────────┬──────────────┬─────────────┐
│ Mode      │ Total │ Completed │ Failed │ Partial │ Success Rate │ Total P/L   │
├───────────┼───────┼───────────┼────────┼─────────┼──────────────┼─────────────┤
│ LIVE      │   45  │    42     │   3    │    0    │    93.3%     │  0.003847   │
│ PAPER     │  123  │   118     │   5    │    0    │    95.9%     │  0.012456   │
│ BACKTEST  │   87  │    84     │   3    │    0    │    96.6%     │  0.008923   │
└───────────┴───────┴───────────┴────────┴─────────┴──────────────┴─────────────┘
```

### Prometheus Metrics

The system exposes comprehensive metrics for monitoring and alerting:

```bash
# Start metrics server (automatically started with strategies)
python -c "from triangular_arbitrage.metrics import get_metrics;
import asyncio;
metrics = get_metrics();
asyncio.run(metrics.start_server(port=8000))"

# View metrics
curl http://localhost:8000/metrics
curl http://localhost:8000/health
```

**Key Metrics Categories:**

1. **Cycle Performance**
   - `triangular_arbitrage_cycles_started_total` - Cycles initiated
   - `triangular_arbitrage_cycles_filled_total` - Successfully completed
   - `triangular_arbitrage_cycles_canceled_by_slippage_total` - Slippage cancellations
   - `triangular_arbitrage_cycles_canceled_by_latency_total` - Latency cancellations

2. **Execution Quality**
   - `triangular_arbitrage_leg_latency_seconds` - Individual leg latencies
   - `triangular_arbitrage_slippage_basis_points` - Order slippage
   - `triangular_arbitrage_order_fill_ratio` - Fill success rate
   - `triangular_arbitrage_cycle_duration_seconds` - Complete cycle times

3. **Profitability**
   - `triangular_arbitrage_realized_profit_basis_points` - Per-cycle profits
   - `triangular_arbitrage_total_profit_loss` - Cumulative P&L
   - `triangular_arbitrage_execution_fees_total` - Trading fees

4. **Risk Management**
   - `triangular_arbitrage_cooldown_count` - Active cooldowns
   - `triangular_arbitrage_consecutive_losses` - Loss streaks
   - `triangular_arbitrage_risk_violations_total` - Risk events

### Grafana Dashboard

Complete Grafana setup with pre-configured dashboards:

```bash
# See docs/grafana_setup.md for complete configuration

# Example Prometheus config
scrape_configs:
  - job_name: 'triangular-arbitrage'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 10s
```

**Dashboard Panels:**
- Real-time success rates and cycle throughput
- P95/P99 latency distributions
- Profit attribution and drawdown analysis
- Risk control effectiveness
- Balance and position tracking

### Advanced Configuration

The system supports extensive configuration for production deployment:

```yaml
# Enhanced strategy configuration
execution:
  mode: live  # or paper, backtest

# Observability settings
observability:
  metrics:
    enabled: true
    port: 8000
    path: /metrics
    expose:
      - cycles_started_total
      - cycles_filled_total
      - realized_profit_basis_points

  logging:
    level: INFO
    trade_csv: logs/trades_strategy.csv
    risk_json: logs/risk_events_strategy.json
    daily_rolling: true
    structured_format: true

# Risk control configuration
risk_controls:
  max_open_cycles: 3
  stop_after_consecutive_losses: 4
  slippage_cooldown_seconds: 300
  enable_latency_checks: true
  enable_slippage_checks: true

# Reconciliation settings
reconciliation:
  partial_fills:
    enabled: true
    hedge_threshold_bps: 50
    cancel_threshold_bps: 200
    max_wait_time_ms: 5000

  position_tracking:
    enabled: true
    tolerance_bps: 1
    reconcile_on_cycle_end: true
```

## Testing and CI/CD

Comprehensive testing framework with multiple test categories:

```bash
# Run full test suite
pytest

# Run specific test categories
pytest tests/unit/ -v                    # Unit tests
pytest tests/integration/ -v             # Integration tests
pytest tests/performance/ -v --benchmark-only  # Performance benchmarks

# Run with coverage
pytest --cov=triangular_arbitrage --cov-report=html

# Test specific execution modes
pytest tests/unit/test_exchanges.py -k "paper"
pytest tests/integration/test_backtest_integration.py
```

**CI/CD Pipeline Features:**
- Automated testing on Python 3.9, 3.10, 3.11
- Security scanning with Bandit and Safety
- Performance benchmarking
- Docker image building
- Documentation generation
- Artifact archiving on failures

## Advanced Usage

### Custom Exchange Adapters

Extend support to additional exchanges:

```python
from triangular_arbitrage.exchanges.base_adapter import ExchangeAdapter

class CustomExchange(ExchangeAdapter):
    async def create_market_order(self, symbol, side, amount):
        # Custom implementation
        pass
```

### Custom Metrics

Add application-specific metrics:

```python
from triangular_arbitrage.metrics import get_metrics

metrics = get_metrics()
metrics.record_cycle_started("my_strategy", "custom_mode")
metrics.update_balance("my_strategy", "BTC", 1.5)
```

### Strategy Development

Create and test new strategies:

```bash
# Test strategy in paper mode
python run_strategy.py --strategy my_strategy.yaml --mode paper --cycles 10

# Backtest strategy performance
python backtests/run_backtest.py --strategy my_strategy.yaml --max-cycles 100

# Monitor strategy performance
python monitor_cycles.py --mode-performance
```

backtest:
  data_file: data/backtests/sample_feed.csv
  start_time: null                      # Optional: Unix timestamp
  end_time: null                        # Optional: Unix timestamp
  market_impact_threshold: 10000        # Notional USD threshold
  market_impact_rate_bps: 2             # Impact rate for large orders
```

## Usage

### Quick Start

⚡ **Lightning Arbitrage Mode** - Execute ALL profitable opportunities immediately:

```bash
# Safe testing: Scan 500 cycles, execute up to 10 profitable trades
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --dry-run --cycles 10

# Live trading: Execute up to 5 profitable opportunities
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --cycles 5

# Resume with persisted cooldowns from previous run
python run_strategy.py --strategy configs/strategies/strategy_1.yaml --resume --cycles 5

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
max_slippage_bps: 9      # Maximum acceptable slippage per leg
max_leg_latency_ms: 264  # Maximum acceptable latency per leg (milliseconds)
capital_allocation:
  mode: fixed_fraction
  fraction: 0.6          # Use 60% of available balance per trade
risk_controls:
  max_open_cycles: 3     # Max concurrent positions
  stop_after_consecutive_losses: 4
  slippage_cooldown_seconds: 300  # Cooldown period after slippage violations
  enable_latency_checks: true     # Enable latency safeguards
  enable_slippage_checks: true    # Enable slippage protection
```

**Cycle File Options:**
- `coinbase_cycles_priority.csv` - 500 liquid token cycles (recommended for speed)
- `coinbase_cycles_massive.csv` - 1,000 diverse cycles (comprehensive coverage)
- `coinbase_cycles_complete.csv` - All 1,920 cycles (maximum opportunities)

### Monitoring & Operator Controls

#### Basic Monitoring
Monitor active trading cycles and system status:

```bash
# View currently active cycles
python monitor_cycles.py --active

# View execution summary (cycles started, filled, partials, PnL)
python monitor_cycles.py --summary

# Review trading history
python monitor_cycles.py --history 20

# Examine specific cycle details
python monitor_cycles.py --details cycle_id_here

# View risk statistics (stop rates, PnL, latencies, duplicate suppression, heartbeats)
python monitor_cycles.py --stats

# View risk control violations (latency/slippage)
python monitor_cycles.py --risk-stats 24  # Last 24 hours

# View active cooldowns with remaining time
python monitor_cycles.py --cooldowns

# View recently suppressed duplicate events
python monitor_cycles.py --suppressed 10  # Last 10 suppressed events

# View suppression summary metrics
python monitor_cycles.py --suppression-summary 300  # Last 300 seconds (5 minutes)

# Clear a specific cooldown (with confirmation)
python monitor_cycles.py --clear-cooldown "BTC->ETH->USDT"

# Extend a cooldown by N seconds
python monitor_cycles.py --extend-cooldown "BTC->ETH->USDT" 60

# Shorten a cooldown by N seconds
python monitor_cycles.py --shorten-cooldown "BTC->ETH->USDT" 30

# Clear all active cooldowns (with confirmation)
python monitor_cycles.py --clear-all-cooldowns

# Clean up old records
python monitor_cycles.py --cleanup 7
```

#### Circuit Breaker Controls
Manage automatic safety mechanisms:

```bash
# Check current circuit breaker status
python monitor_cycles.py breaker status

# Manually pause trading for 5 minutes (default)
python monitor_cycles.py breaker pause

# Pause trading for custom duration (e.g., 10 minutes)
python monitor_cycles.py breaker pause --seconds 600

# Resume trading after manual pause
python monitor_cycles.py breaker resume
```

#### Cooldown Management
Clear trading pair cooldowns when market stabilizes:

```bash
# View all active cooldowns
python monitor_cycles.py cooldown status

# Clear cooldown for specific trading pair
python monitor_cycles.py cooldown clear BTC

# Clear all active cooldowns
python monitor_cycles.py cooldown clear-all
```

#### Operational Snapshot & Health Check

Capture current risk state or run health checks for CI/CD:

```bash
# Create snapshot (JSON + MD) with current risk state
python monitor_cycles.py snapshot
python monitor_cycles.py snapshot --out-dir logs/ops --recent 10 --window 300

# Health check with exit code (0=OK, 1=FAIL)
python monitor_cycles.py health
python monitor_cycles.py health --window 300 --max-suppression-rate 90
```

**Snapshot includes:**
- System metadata (hostname, Python version, platform)
- Current config (max_slippage_bps, max_leg_latency_ms, etc.)
- Active cooldowns
- Suppression summary (last N seconds)
- Recent suppressed events

**Use cases:**
- Support ticket artifact (attach snapshot files)
- CI/CD health probe (check exit code)
- On-call checklist (quick system state review)
- Pre/post-deployment comparison

#### System Heartbeat
Monitor system health through automatic heartbeat events:

The system sends periodic heartbeat events to confirm it's alive and processing, especially useful when no trades occur for extended periods:

- **Purpose**: Confirm system is running even during quiet periods
- **Frequency**: Configurable via `risk_logging.heartbeat_interval_seconds` (default: 60 seconds, 0 to disable)
- **Monitoring**: View heartbeat count in `python monitor_cycles.py --stats`
- **Logs**: Heartbeat events appear in JSON logs with `event_type: "heartbeat"`

Configure heartbeat interval in your strategy YAML:
```yaml
risk_logging:
  heartbeat_interval_seconds: 60  # Send heartbeat every 60 seconds (0 to disable)
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

### 🔍 Audit & Postmortem Analysis

- **Configuration Tracking**: Every run saves a config snapshot with SHA256 hash
- **Incident Replay**: Analyze past incidents with counterfactual "what-if" scenarios
- **Daily Risk Reports**: Generate comprehensive reports with statistics and trends
- **Full Traceability**: Link any event back to its exact configuration
- **Duplicate Event Suppression**: Automatically prevents spam from identical risk events within configurable time windows (default: 2 seconds)

#### Generate Risk Reports
```bash
# Daily risk report
python monitor_cycles.py report today

# Historical report
python monitor_cycles.py report 2024-01-15
```

#### Replay Incidents
```bash
# Analyze recent incidents with different thresholds
python tools/replay_incidents.py --start 1h --slippage-grid 15,20,25,30
```

### ⚡ Performance & Resilience Testing

- **Performance Budgets**: Enforce maximum decision latency with automatic cycle skipping
- **Quote Freshness Guards**: Reject cycles based on stale market data timestamps
- **Chaos Testing**: Inject controlled failures in paper/backtest modes for resilience testing
- **Canary Rollouts**: Test new guardrail values on a percentage of traffic before full deployment

#### Generate Guardrail Suggestions
```bash
# Analyze recent data and suggest optimal thresholds
python tools/suggest_guardrails.py --hours 24
```

#### Enable Chaos Testing (Paper Mode Only)
```yaml
chaos:
  enable: true
  reject_rate_pct: 10.0
  latency_spike_ms: 1000
```

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

## Observability & Metrics

### Prometheus Metrics Server

The system exposes Prometheus metrics for monitoring:

```python
from triangular_arbitrage.metrics_server import get_metrics_server

metrics = get_metrics_server(port=9090)
metrics.start()
```

**Available Metrics:**
- `arbitrage_cycles_started_total` - Total cycles initiated
- `arbitrage_cycles_filled_total` - Successfully completed cycles
- `arbitrage_cycles_canceled_slippage_total` - Slippage cancellations
- `arbitrage_cycles_canceled_latency_total` - Latency cancellations
- `arbitrage_leg_latency_seconds` - Execution latency per leg
- `arbitrage_realized_basis_points` - Realized profit distribution
- `arbitrage_active_cooldowns` - Active cooldown count
- `arbitrage_open_cycles` - Currently executing cycles

**Scrape Endpoint:** `http://localhost:9090/metrics`

See [GRAFANA_METRICS.md](GRAFANA_METRICS.md) for detailed Grafana dashboard setup and example queries.

## Architecture

The system follows a modular architecture with clear separation of concerns:

```
StrategyExecutionEngine (Orchestrator)
├── StateManager (Persistent Storage)
├── ConfigurationManager (YAML Processing)
├── OrderManager (Trade Execution)
├── FailureRecoveryManager (Error Handling)
└── ExchangeAdapter (Live/Paper/Backtest)
    ├── PaperExchange (Simulated execution)
    └── BacktestExchange (Historical replay)
```

Each component is independently testable and can be configured through the strategy files.

## Risk Management

The system implements multiple layers of risk protection:

1. **Pre-Trade Validation**: Verifies sufficient balances, valid markets, and minimum order requirements
2. **Position Limits**: Enforces maximum position sizes and concurrent cycle limits
3. **Loss Protection**: Automatic shutdown after configurable consecutive losses
4. **Emergency Procedures**: Panic-sell mechanism for immediate position liquidation
5. **State Persistence**: Maintains complete trade history for audit and recovery

## Documentation

### Quick Links

- **[Developer Guide](DEVELOPER_GUIDE.md)** - Comprehensive guide for developers including troubleshooting, testing, and recent improvements
- **[Configuration Reference](docs/CONFIG_REFERENCE.md)** - Complete parameter reference for all execution modes
- **[Execution Engine Docs](EXECUTION_ENGINE_DOCS.md)** - Detailed technical documentation

### Getting Help

**For developers**:
1. See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for troubleshooting common issues
2. Check [CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) for configuration options
3. Run tests: `pytest tests/ -v`

**For users**:
1. Enable debug logging: `--log-level DEBUG`
2. Test with dry-run mode: `--dry-run`
3. Review execution logs in `logs/` directory

## Contributing

Development workflow:

1. **Test changes**: Always test in dry-run mode first
2. **Follow standards**: Maintain 80%+ docstring coverage
3. **Run quality checks**:
   ```bash
   pytest tests/ -v
   flake8 triangular_arbitrage/ --max-line-length=127
   interrogate triangular_arbitrage/ --fail-under=80
   ```
4. **Update docs**: Keep configuration and troubleshooting guides current

See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for detailed contribution guidelines.

## Development

### Makefile Commands

This project includes a comprehensive Makefile for all development tasks:

```bash
# Show all available commands
make help

# Development setup
make setup              # Install dependencies and pre-commit hooks
make dev-setup         # Complete development environment setup

# Code quality
make fmt               # Format code with black and isort
make lint              # Run linting checks with flake8
make type              # Run type checking with mypy
make validate          # Run all validation checks (lint + type)

# Testing
make test              # Run full test suite with coverage
make ci                # Run all CI checks locally

# Trading modes
make paper             # Run paper trading mode
make backtest          # Run backtesting mode

# Docker operations
make docker-build      # Build Docker image
make docker-test       # Run tests in Docker container
make docker-dev        # Start development environment
make docker-down       # Stop development environment

# Maintenance
make clean             # Clean up build artifacts and caches
make build             # Build distribution packages
```

### Code Quality and Formatting

The Makefile automates all code quality checks:

```bash
# Format and validate code
make fmt validate

# Set up pre-commit hooks (runs automatically on commits)
make setup
```

### Configuration Validation

Validate configuration files before running strategies:

```bash
# Validate a single configuration file
python tools/validate_config.py configs/strategies/strategy_example.yaml

# Validate multiple files
python tools/validate_config.py configs/strategies/*.yaml

# Validate with strict mode (exits on first error)
python tools/validate_config.py configs/strategies/strategy_example.yaml --strict
```

### Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=triangular_arbitrage --cov-report=html

# Run specific test categories
pytest tests/unit/          # Unit tests
pytest tests/integration/   # Integration tests
pytest tests/performance/   # Performance tests
```

### Project Structure

```
triangular_arbitrage/
├── __init__.py                 # Main package exports
├── constants.py               # Enums and system constants
├── exceptions.py              # Custom exception hierarchy
├── interfaces.py              # Dependency injection interfaces
├── utils.py                   # Common utilities and helpers
├── config_loader.py           # Configuration loading and normalization
├── config_schema.py           # Pydantic validation schemas
├── execution_engine.py        # Core trading engine
├── detector.py                # Arbitrage opportunity detection
├── trade_executor.py          # Trade execution coordination
├── risk_controls.py           # Risk management system
├── metrics.py                 # Prometheus metrics server
└── exchanges/                 # Exchange adapter implementations
    ├── base_adapter.py        # Abstract exchange interface
    ├── paper_exchange.py      # Paper trading simulation
    └── backtest_exchange.py   # Historical data backtesting
```

## License

[Add your license information here]

## Support

For questions or issues:
1. Check [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) troubleshooting section
2. Review logs in `logs/` directory
3. File issues at [GitHub Issues](https://github.com/anthropics/claude-code/issues)