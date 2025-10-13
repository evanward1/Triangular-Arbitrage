# Live Trading Setup

⚠️ **This system trades with real money. You can lose money. Only proceed if you understand the risks.**

## Quick Setup

### 1. Create Exchange API Keys

**Recommended exchanges:**
- Kraken (US-friendly, reliable)
- Coinbase Pro (US-based)
- Binance (high liquidity, restricted in some US states)

**API Permissions:**
- ✅ Read account balance
- ✅ Place orders
- ✅ Cancel orders
- ❌ Withdraw funds (keep disabled)

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env
KRAKEN_API_KEY=your_api_key_here
KRAKEN_API_SECRET=your_secret_here

# Safety settings (start small!)
TRADING_MODE=paper
MAX_POSITION_SIZE=50
MIN_PROFIT_THRESHOLD=1.0
```

### 3. Test in Paper Mode

```bash
python run_clean.py
# Choose option 1 (Paper Trading)
```

Verify the system finds opportunities and simulates trades correctly.

### 4. Switch to Live Trading

```bash
# Edit .env
TRADING_MODE=live

# Run
python run_clean.py
# Choose option 2 (Live Trading)
# Confirm with 'YES' when prompted
```

## Safety Limits

**Conservative (Recommended):**
```bash
MAX_POSITION_SIZE=50      # $50 per trade
MIN_PROFIT_THRESHOLD=1.0  # 1% minimum profit
```

**Aggressive (Advanced):**
```bash
MAX_POSITION_SIZE=500     # $500 per trade
MIN_PROFIT_THRESHOLD=0.3  # 0.3% minimum profit
```

## Monitoring

The system displays:
- Real-time trade execution
- Actual profit/loss per cycle
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

## Troubleshooting

**"API key invalid"**
- Verify API key and secret in `.env`
- Ensure trading permissions are enabled

**"Insufficient funds"**
- Check exchange account balance
- Lower `MAX_POSITION_SIZE`

**"No profitable opportunities"**
- Normal - system waits for good opportunities
- Lower `MIN_PROFIT_THRESHOLD` slightly if too restrictive

## Security Best Practices

1. Never share API keys
2. Keep `.env` file private (in .gitignore)
3. Use minimal API permissions (no withdrawals)
4. Start with small position sizes
5. Monitor trades closely initially

## Getting Started Checklist

- [ ] Create exchange account and verify identity
- [ ] Generate API keys (trading only, no withdrawals)
- [ ] Copy `.env.example` to `.env`
- [ ] Add API credentials to `.env`
- [ ] Set `TRADING_MODE=paper`
- [ ] Set small `MAX_POSITION_SIZE=50`
- [ ] Test with paper trading
- [ ] When satisfied, switch to `TRADING_MODE=live`
- [ ] Start with real money (small amounts!)

---

**Remember: Only invest what you can afford to lose.**
