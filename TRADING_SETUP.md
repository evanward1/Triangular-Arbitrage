# Real Trading Setup Guide

## ⚠️ IMPORTANT WARNING
This system trades with REAL MONEY. You can lose money. Only proceed if you understand the risks.

## 1. Setup API Keys

### Step 1: Choose Your Exchange
Recommended for beginners:
- **Kraken**: Good for US users, reliable, reasonable fees
- **Coinbase Pro**: US-based, very reliable
- **Binance**: High liquidity, many pairs (not available in all US states)

### Step 2: Create API Keys
1. Log into your exchange account
2. Go to API settings
3. Create a new API key with these permissions:
   - **Read account balance** ✅
   - **Place orders** ✅
   - **Cancel orders** ✅
   - **Withdraw funds** ❌ (NOT needed, keep disabled for security)

### Step 3: Configure Environment
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your API credentials:
   ```bash
   # For Kraken:
   KRAKEN_API_KEY=your_actual_api_key_here
   KRAKEN_SECRET=your_actual_secret_here

   # Trading Configuration
   TRADING_MODE=paper  # Start with 'paper', change to 'live' when ready
   MAX_POSITION_SIZE=50  # Start small! Max $50 per trade
   MIN_PROFIT_THRESHOLD=1.0  # Require 1% profit minimum
   ```

## 2. Safety Settings

### Start Small
- `MAX_POSITION_SIZE=50` - Only risk $50 per trade initially
- `MIN_PROFIT_THRESHOLD=1.0` - Only trade if profit > 1%

## 3. Running the System

### Interactive Mode (Recommended)
Simply run:
```bash
python run_clean.py
```

You'll see:
```
🚀 Initializing arbitrage trading system...

Choose trading mode:
1. 📝 Paper Trading (Simulation - Safe)
2. 💰 Live Trading (Real Money - Risk)

Enter your choice (1 or 2):
```

- **Choose 1** for safe paper trading (simulation)
- **Choose 2** for live trading with real money

### What Happens When You Choose:

**Paper Trading (Option 1):**
```
📝 PAPER TRADING MODE - Simulation only
💰 Max position size: $100
📊 Min profit threshold: 0.5%
🎯 Monitoring markets for arbitrage opportunities...
```

**Live Trading (Option 2):**
```
⚠️  LIVE TRADING MODE - Using real money!
🔑 Checking API keys...
✅ API keys configured

⚠️  Are you absolutely sure you want to proceed with LIVE trading? Type 'YES':
```

## 4. Understanding the Output

## 5. Risk Management

### Built-in Safety Features:
- **Position limits**: Never trades more than MAX_POSITION_SIZE
- **Profit thresholds**: Only trades if profit > MIN_PROFIT_THRESHOLD
- **Confirmation prompts**: Asks before live trading
- **API permissions**: Only needs trading permissions, not withdrawals

### Recommended Limits for Beginners:
```env
MAX_POSITION_SIZE=50      # Start with $50 max per trade
MIN_PROFIT_THRESHOLD=1.0  # Require 1% minimum profit
```

### Advanced Users:
```env
MAX_POSITION_SIZE=500     # Up to $500 per trade
MIN_PROFIT_THRESHOLD=0.3  # Accept 0.3% minimum profit
```

## 6. Monitoring

The system will show:
- Real-time trade execution
- Actual profit/loss from each cycle
- Current account balance
- Win rate and performance metrics

Example output:
```
💰 STARTING CYCLE: USD -> EUR -> BTC -> USD
✅ COMPLETED: USD -> EUR -> BTC -> USD
💰 REAL BALANCE UPDATE:
   📊 Before: $10,000.00 → After: $10,012.50
   💵 Real Profit/Loss: $+12.50
```

## 7. Troubleshooting

### "API key invalid"
- Double-check your API key and secret in `.env`
- Make sure API key has trading permissions enabled

### "Insufficient funds"
- Check your exchange account balance
- Reduce MAX_POSITION_SIZE

### "No profitable opportunities"
- This is normal - the system waits for good opportunities
- Try lowering MIN_PROFIT_THRESHOLD slightly

## 8. Security Best Practices

1. **Never share your API keys**
2. **Keep `.env` file private** (it's in .gitignore)
3. **Use API keys with minimal permissions**
4. **Start with small amounts**
5. **Monitor trades closely initially**

## 9. Getting Started Checklist

- [ ] Create exchange account and verify identity
- [ ] Generate API keys with trading permissions only
- [ ] Copy `.env.example` to `.env`
- [ ] Add your API credentials to `.env`
- [ ] Set `TRADING_MODE=paper` for testing
- [ ] Set small `MAX_POSITION_SIZE=50`
- [ ] Test with `python run_clean.py`
- [ ] When satisfied, change to `TRADING_MODE=live`
- [ ] Run with real money (start small!)

---
**Remember: Only invest what you can afford to lose!**
