# Web Dashboard

Real-time monitoring and control for CEX and DEX arbitrage trading.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
cd web_ui && npm install && npm run build && cd ..

# Start server
python web_server.py

# Access at http://localhost:8000
```

## Features

### CEX Tab
- Live balance, equity, and performance metrics
- Real-time opportunity feed and trade history
- System logs with auto-scroll
- Start/stop bot control

### DEX Tab
- **Paper (Live Chain)**: Uses live RPC data but never broadcasts transactions (safe testing)
- **Live Trading**: Full execution with real transaction broadcasts
- Control panel with size, thresholds, slippage, gas configuration
- Real-time opportunities with profit/gas/slippage breakdown
- Equity chart and fills history
- **Decision Trace**: Debug why trades execute or skip

## Configuration

### DEX Control Panel

```bash
# Start paper mode (safe - no broadcasts)
curl -X POST http://localhost:8000/api/dex/control \
  -H "Content-Type: application/json" \
  -d '{
    "action": "start",
    "mode": "paper_live_chain",
    "config": {
      "size_usd": 1000,
      "min_profit_threshold_bps": 10,
      "slippage_floor_bps": 5,
      "gas_model": "fast"
    }
  }'

# Stop scanner
curl -X POST http://localhost:8000/api/dex/control \
  -H "Content-Type: application/json" \
  -d '{"action": "stop"}'
```

## API Endpoints

**CEX**
- `GET /api/balance` - Current balance and equity
- `GET /api/opportunities` - Arbitrage opportunities
- `GET /api/trades` - Trade history
- `POST /api/bot/start` - Start CEX bot
- `POST /api/bot/stop` - Stop CEX bot

**DEX**
- `GET /api/dex/status` - Current status with last decision
- `GET /api/dex/opportunities` - Opportunity feed (max 50)
- `GET /api/dex/fills` - Recent fills (max 100)
- `GET /api/dex/equity` - Equity time series
- `GET /api/dex/decisions` - Decision history for debugging
- `POST /api/dex/control` - Start/stop with config

**WebSocket**
- `WS /ws` - CEX real-time updates
- `WS /ws/dex` - DEX real-time updates

## Debugging Decisions

Every opportunity is evaluated and logged as EXECUTE or SKIP with detailed reasoning.

### Check Decisions via API

```bash
# Get recent decisions
curl http://localhost:8000/api/dex/decisions | jq '.decisions[:5]'

# Get last decision from status
curl http://localhost:8000/api/dex/status | jq '.status.last_decision'

# Find all SKIP reasons
curl http://localhost:8000/api/dex/decisions | jq '.decisions[] | select(.action == "SKIP") | .reasons'
```

### Decision Format

```
[timestamp] Decision EXECUTE reasons=[] metrics: gross=0.80% net=0.40% breakeven=0.60% fees=0.30% slip=0.05% gas=0.05% size=$1000.00

[timestamp] Decision SKIP reasons=[threshold: net 0.04% < 0.20%] metrics: gross=0.39% net=0.04% breakeven=0.55% fees=0.30% slip=0.05% gas=0.20% size=$100.00
```

### Common Skip Reasons

- `threshold` - Net profit below configured minimum
- `size` - Position size too small (<$10) or too large
- `depth` - Depth-limiting reduced size below minimum
- `leg1/leg2/leg3` - Per-leg notional below $5 (CEX only)
- `maker_legs` - Insufficient maker legs for fee optimization
- `concurrent` - Too many trades executing simultaneously
- `cooldown` - Not enough time since last trade
- `exchange` - Exchange connection not ready
- `quote` - Missing quote data (DEX)
- `gas` - Missing gas estimate (DEX)

### Troubleshooting

**No trades executing?**

1. Check threshold:
   ```bash
   curl http://localhost:8000/api/dex/status | jq '.status.config.min_profit_threshold_bps'
   ```

2. Review rejections:
   ```bash
   curl http://localhost:8000/api/dex/decisions | jq '.decisions[] | select(.action == "SKIP") | .reasons'
   ```

3. Lower threshold if needed:
   ```bash
   curl -X POST http://localhost:8000/api/dex/control \
     -H "Content-Type: application/json" \
     -d '{"action": "start", "mode": "paper_live_chain", "config": {"min_profit_threshold_bps": 5}}'
   ```

**Size constraints:**
- Minimum: $10 per trade
- Maximum: Configured `size_usd`
- Per-leg minimum: $5 (CEX only)

## Development Mode

```bash
# Terminal 1: Backend
python web_server.py

# Terminal 2: Frontend (hot reload)
cd web_ui && npm start
```

Frontend at http://localhost:3000, backend at http://localhost:8000

## Docker Deployment

```bash
docker-compose up -d
```

Access at http://localhost:8000

## Security Notes

For production:
1. Change CORS settings in `web_server.py` (not `"*"`)
2. Use HTTPS/WSS for secure connections
3. Enable authentication
4. Use environment variables for sensitive data

## License

MIT License - See LICENSE file for details
