# Triangular Arbitrage Trading System

Automated cryptocurrency arbitrage detection and execution across CEX and DEX exchanges.

## Features

- **CEX Arbitrage**: Multi-exchange support (Binance, Kraken, KuCoin, Coinbase)
- **DEX Arbitrage**: Uniswap V2/V3 cross-DEX opportunities on Ethereum/Base
- **Decision Engine**: Explicit EXECUTE/SKIP logging with detailed reasoning
- **Web Dashboard**: React + FastAPI real-time monitoring and control
- **Paper Trading**: Risk-free testing with live market data
- **ML Optimization**: GNN-based cycle scoring learns from execution history

## Quick Start

### Installation

```bash
git clone <repository-url>
cd Triangular-Arbitrage
pip install -r requirements.txt
cp .env.example .env
```

### Running

**Interactive Menu** (Recommended)
```bash
python run_clean.py
```

**CEX Arbitrage**
```bash
# Paper mode (safe)
python run_clean.py cex --paper

# Live trading (requires API keys)
python run_clean.py cex --live
```

**DEX Arbitrage**
```bash
# Paper mode with live chain data
python run_clean.py dex --quiet

# Single scan test
python run_clean.py dex --quiet --once

# Live mode (requires wallet setup)
python run_clean.py dex --live --config configs/dex_mev.yaml
```

**Web Dashboard**
```bash
# Start server
python web_server.py

# Access at http://localhost:8000
# Build frontend: cd web_ui && npm run build
```

## Configuration

### Production Strategy Configuration

For live trading, use the production example configuration:

```bash
# Copy the production example
cp configs/strategies/strategy_production_example.yaml configs/strategies/my_strategy.yaml

# Edit your strategy
nano configs/strategies/my_strategy.yaml
```

**Key Configuration Options**:

```yaml
# Price Mode - Use bid/ask for more accurate profit estimation
use_bid_ask: true  # Recommended for live trading (more conservative)
                   # Set to false to use last price (faster but less accurate)

# Profit Thresholds
min_profit_bps: 20          # Minimum net profit (0.20% = 20 basis points)
max_slippage_bps: 30        # Maximum allowed slippage per leg
max_leg_latency_ms: 3000    # Maximum execution time per leg

# Safety Margins
safety_margin_bps: 10       # Extra buffer for market fluctuations
spread_buffer_bps: 5        # Additional buffer for wide spreads

# Feature Flags - Disable experimental features
feature_flags:
  enable_dex_arbitrage: false    # Only enable if fully tested
  enable_mev_solver: false       # Only enable if ready
  enable_precomputed_cycles: false  # Use cycle files for speed
```

### Environment Variables

Edit `.env` for basic settings:

```bash
# Trading
MAX_POSITION_SIZE=100
MIN_PROFIT_THRESHOLD=0.5
PAPER_USDT=1000

# Display
VERBOSITY=normal
TOPN=3

# Symbol filtering
SYMBOL_ALLOWLIST=BTC,ETH,SOL,AVAX,LINK
TRIANGLE_BASES=USD,USDT
```

For DEX, configure `configs/dex_mev.yaml`:

```yaml
rpc_url: "https://mainnet.infura.io/v3/YOUR_KEY"
max_position_usd: 1000
threshold_net_pct: 0.1
```

## Decision Engine

Every opportunity is evaluated and logged:

```
[16:30:15] Decision EXECUTE reasons=[] metrics: gross=0.80% net=0.40% breakeven=0.60% fees=0.30% slip=0.05% gas=0.05% size=$1000.00

[16:30:20] Decision SKIP reasons=[threshold: net 0.04% < 0.20%] metrics: gross=0.39% net=0.04% breakeven=0.55% fees=0.30% slip=0.05% gas=0.20% size=$100.00
```

**Debug API**:
```bash
# Check why trades aren't executing
curl http://localhost:8000/api/dex/decisions | jq '.decisions[:5]'

# Review rejection patterns
curl http://localhost:8000/api/dex/decisions | jq '.decisions[] | select(.action == "SKIP") | .reasons'
```

## Architecture

```
┌─────────────────┐
│  React Frontend │  Web dashboard (port 3000/8000)
└────────┬────────┘
         │ WebSocket + REST
┌────────▼────────┐
│  FastAPI Server │  Real-time updates, decision tracking
└────────┬────────┘
         │
┌────────▼────────┐
│ Trading Engines │  CEX (trading_arbitrage.py)
│                 │  DEX (run_dex_scanner in web_server.py)
└─────────────────┘
```

**Key Components**:
- `decision_engine.py` - Unified trade execution decisions
- `trading_arbitrage.py` - CEX arbitrage engine
- `web_server.py` - FastAPI backend with DEX scanner
- `web_ui/` - React dashboard

## Testing

```bash
# Decision engine tests
pytest tests/test_decision_engine.py -v

# All tests
pytest -v

# With coverage
pytest --cov=triangular_arbitrage
```

## Web Dashboard

### Start Backend
```bash
python web_server.py
```

### Build Frontend
```bash
cd web_ui
npm install
npm run build
cd ..
```

### Access
Open http://localhost:8000

**Features**:
- Real-time opportunity feed
- Trade history and fills
- Equity curve tracking
- Decision trace debugging
- System logs
- Control panel (start/stop, configure)

**API Endpoints**:
- `GET /api/dex/status` - Current status with last decision
- `GET /api/dex/opportunities` - Opportunity feed
- `GET /api/dex/fills` - Recent fills
- `GET /api/dex/decisions` - Decision history (debugging)
- `POST /api/dex/control` - Start/stop with config

## Documentation

- **[WEB_DASHBOARD_README.md](WEB_DASHBOARD_README.md)** - Dashboard setup and decision debugging
- **[TRADING_SETUP.md](TRADING_SETUP.md)** - Live trading setup and API keys
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

## Safety

**Built-in Protections**:
- Position limits
- Profit thresholds
- Depth validation
- Slippage estimation
- Decision engine gates
- Paper mode testing

**Always**:
- Test in paper mode first
- Use small position sizes initially
- Monitor decision logs
- Check rejection reasons
- Review `/api/dex/decisions` endpoint

## Troubleshooting

**No trades executing**:
```bash
# Check decisions
curl http://localhost:8000/api/dex/decisions | jq -r '.decisions[] | "\(.action) \(.reasons | join(", "))"'

# Lower threshold if too many "threshold" rejects
curl -X POST http://localhost:8000/api/dex/control -H "Content-Type: application/json" -d '{"action": "start", "mode": "paper_live_chain", "config": {"min_profit_threshold_bps": 5}}'
```

**Size issues**:
- Minimum: $10 per trade
- Per-leg minimum: $5 (CEX)
- Adjust `size_usd` in config

**See [WEB_DASHBOARD_README.md](WEB_DASHBOARD_README.md) "Debugging Decisions" section for comprehensive troubleshooting**

## License

MIT License

## Disclaimer

⚠️ **For educational purposes only. Cryptocurrency trading carries substantial risk. Always test in paper mode first. Never trade with money you cannot afford to lose. Use at your own risk.**
