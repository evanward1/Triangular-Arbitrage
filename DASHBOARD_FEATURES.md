# Dashboard Features

## Overview

The web dashboard now supports **two modes** via a tabbed interface:
1. **CEX Tab**: Centralized exchange triangular arbitrage
2. **DEX & MEV Tab**: Decentralized exchange and MEV opportunities

## ✨ What's New

### Trading Mode Selection
You can now choose between **Paper Trading** and **Live Trading** directly from the web interface!

#### When Bot is Stopped:
- **Mode Selector Dropdown** appears in the header
- Choose between:
  - 📝 **Paper Trading** (Safe simulation - no real money)
  - 💰 **Live Trading** (Real money - requires API keys)
- Click **▶️ Start Bot** to begin trading in the selected mode

#### When Bot is Running:
- **Mode Indicator** shows current trading mode
  - Paper mode: Blue badge with 📝
  - Live mode: Orange pulsing badge with 💰 (warning indicator)
- Click **⏹ Stop Bot** to stop trading

### Safety Features

#### Live Trading Protection:
1. **API Key Validation**: Bot checks for API keys before starting in live mode
2. **Error Messages**: Clear alerts if API keys are missing
3. **Visual Warning**: Live mode has a pulsing orange indicator to remind you real money is at risk
4. **Mode Visibility**: Always shows which mode the bot is running in

#### Paper Trading Default:
- Default mode is always **Paper Trading**
- Safe to click Start without changing anything
- Perfect for testing and learning

## 🎨 UI/UX Improvements

### Header Controls (Left to Right):
```
🔺 Triangular Arbitrage Dashboard
    [🟢 Connected] [📝 Paper Trading / Mode Selector] [▶️ Start Bot]
```

### Real-time Features:
- ✅ Live log streaming in System Logs panel
- ✅ All bot output captured (print statements, errors, warnings)
- ✅ WebSocket broadcasts for instant updates
- ✅ Auto-scroll logs to show latest messages

### Dashboard Sections:
1. **Top Stats Grid**: Equity, Balance, Profit, Trades, Uptime, Success Rate
2. **Opportunities Panel**: Current arbitrage opportunities detected
3. **Trade History**: Recent executed trades with P&L
4. **System Logs**: Real-time bot output and system messages

## 🚀 Quick Start

```bash
# 1. Rebuild frontend (only needed once after code changes)
cd web_ui
npm run build
cd ..

# 2. Start the web server
python web_server.py

# 3. Open browser
open http://localhost:8000
```

## 📝 How to Use

### Paper Trading (Recommended for Testing):
1. Open dashboard at http://localhost:8000
2. Keep mode selector on "📝 Paper Trading" (default)
3. Click **▶️ Start Bot**
4. Watch live logs and opportunities
5. Click **⏹ Stop Bot** when done

### Live Trading (Real Money):
1. Set up API keys in `.env` file:
   ```bash
   KRAKEN_API_KEY=your_key_here
   KRAKEN_API_SECRET=your_secret_here
   ```
2. Open dashboard at http://localhost:8000
3. Select "💰 Live Trading" from dropdown
4. Click **▶️ Start Bot**
5. ⚠️ **Confirm you want to use real money**
6. Monitor carefully (orange pulsing indicator)
7. Click **⏹ Stop Bot** to stop

## 🔍 What to Expect in Logs

When you start the bot, you'll see:
```
[timestamp] 📝 Bot started in PAPER TRADING mode
[timestamp] Initializing arbitrage bot...
[timestamp] Trying binanceus...
[timestamp] Connected to binanceus, starting trading session...
[timestamp] Fetching market data...
[timestamp] Building graph with X currencies and Y edges...
[timestamp] Scanning for opportunities...
[timestamp] ✅ Found opportunity: BTC → ETH → USDT → BTC (0.25% profit)
```

## ⚙️ Configuration

Environment variables in `.env`:
```bash
# Trading mode (only used when not started from web UI)
TRADING_MODE=paper

# Paper trading balances
PAPER_USDT=1000
PAPER_USDC=1000

# Trading parameters
MIN_PROFIT_THRESHOLD=0.5    # Minimum 0.5% profit
MAX_POSITION_SIZE=100       # Max $100 per trade

# Filters (empty = all symbols allowed)
SYMBOL_ALLOWLIST=           # Leave empty for all
TRIANGLE_BASES=             # Leave empty for all
EXCLUDE_SYMBOLS=            # Leave empty for none

# API Keys (for live trading)
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
BINANCE_API_KEY=
BINANCE_API_SECRET=
COINBASE_API_KEY=
COINBASE_API_SECRET=
```

## 🔐 Security Best Practices

1. **Never commit API keys** to git (.env is in .gitignore)
2. **Use API key restrictions** on exchange (IP whitelist, permissions)
3. **Start with paper trading** to test the bot
4. **Use small position sizes** when starting live trading
5. **Monitor closely** during live trading sessions
6. **Set up 2FA** on your exchange accounts

## 🐛 Troubleshooting

### Bot starts but no logs appear:
- Wait 5-10 seconds for connection to establish
- Check browser console for WebSocket errors
- Verify backend is running on port 8000

### "No API keys configured" error:
- Create/edit `.env` file in project root
- Add your exchange API keys
- Restart web server: `python web_server.py`

### Mode selector not appearing:
- Make sure bot is stopped
- Refresh browser page
- Clear browser cache (Cmd+Shift+R / Ctrl+Shift+R)

### Live mode starts in paper mode:
- Rebuild React frontend: `cd web_ui && npm run build`
- Restart web server
- Hard refresh browser

## 🔷 DEX & MEV Tab Features

### Control Panel
Configure your DEX scanner with:
- **Mode**: Paper or Live trading
- **Chain**: Ethereum (1), Polygon (137), Arbitrum (42161)
- **Size (USD)**: Position size per opportunity
- **Min Profit (bps)**: Minimum profit threshold in basis points
- **Slippage Floor (bps)**: Minimum slippage assumption
- **Expected Maker Legs**: Number of maker orders expected
- **Gas Model**: slow, standard, fast, or instant

All controls are disabled when scanner is running for safety.

### Status Panel
Real-time display of:
- Current mode (Paper/Live)
- Active chain
- Number of pools loaded
- Scan interval (seconds)
- Best gross profit (bps)
- Best net profit (bps)
- Last scan timestamp

### Opportunities Table
- **Sortable columns**: Click headers to sort by Gross, Net, Gas, or Slip
- **Path display**: Shows full token path (e.g., USDC → WETH → DAI)
- **Color coding**: Green for positive net profit, red for negative
- **Row selection**: Click to open detailed drawer
- **Live updates**: New opportunities stream in via WebSocket

### Opportunity Details Drawer
Opens on the right when you select an opportunity:
- Full path breakdown
- Gross/net profit with gas and slippage breakdown
- **Leg-by-leg details**:
  - Pair and side (buy/sell)
  - Price and liquidity
  - Estimated slippage per leg

### Equity Chart
- Live equity curve using Recharts
- Shows paper or live trading performance
- Updates in real-time as fills execute
- Hover for timestamp and equity value

### Fills Table
Recent execution history:
- Timestamp
- Mode badge (Paper/Live)
- Net profit in basis points
- P&L in USD
- **Transaction link**: Click "View" to see on block explorer (live mode only)

### Trading Modes

The DEX tab supports two execution modes:

#### Paper (Live Chain) - Default & Recommended
- Uses **live RPC data** from real blockchain
- Reads pool reserves, prices, and liquidity from chain
- Calculates gas costs using live gas oracles
- Simulates transactions with `eth_call` or `eth_estimateGas`
- Records realistic PnL with actual gas and slippage
- **Never broadcasts** transactions - simulation only
- Safe for testing with real market conditions

#### Live Trading
- Full execution with real transaction broadcasts
- Requires private keys and funded wallet
- Actually sends transactions to blockchain
- Use with extreme caution

### Mode Indicator
The status panel shows:
- **"Paper (Live Chain)"** - Green, safe mode
- **"Live"** - Red, real money at risk

### Simulation Details
Every fill in Paper (Live Chain) mode includes:
- `gas_used`: Actual gas consumed in simulation
- `success`: Whether simulation succeeded
- `gas_estimate`: Pre-execution gas estimate
- `paper`: Always true for paper mode
- `tx_hash`: Always null (no broadcast)

## 📊 API Endpoints

### CEX Endpoints

```bash
# Check health
curl http://localhost:8000/api/health

# Get current balance
curl http://localhost:8000/api/balance

# Start bot in paper mode
curl -X POST http://localhost:8000/api/bot/start?mode=paper

# Start bot in live mode
curl -X POST http://localhost:8000/api/bot/start?mode=live

# Stop bot
curl -X POST http://localhost:8000/api/bot/stop

# Get logs
curl http://localhost:8000/api/logs
```

### DEX/MEV Endpoints

```bash
# Get DEX status
curl http://localhost:8000/api/dex/status

# Get opportunities
curl http://localhost:8000/api/dex/opportunities

# Get fills
curl http://localhost:8000/api/dex/fills

# Get equity time series
curl http://localhost:8000/api/dex/equity

# Start DEX scanner with config
curl -X POST http://localhost:8000/api/dex/control \
  -H "Content-Type: application/json" \
  -d '{
    "action": "start",
    "config": {
      "size_usd": 1000,
      "min_profit_threshold_bps": 0,
      "paper": true
    }
  }'

# Stop DEX scanner
curl -X POST http://localhost:8000/api/dex/control \
  -H "Content-Type: application/json" \
  -d '{"action": "stop"}'
```

## 🎯 Next Steps

- Test paper trading thoroughly
- Monitor for opportunities
- Analyze profitability
- Fine-tune parameters
- Consider live trading (at your own risk!)

---

**Remember**: Always test with paper trading first. Live trading involves real financial risk!
