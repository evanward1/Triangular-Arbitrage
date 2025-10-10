# DEX Paper Trading - Quick Start Guide

## 🚀 Run It Now (Zero Config)

```bash
python3 run_dex_paper.py
```

That's it! The scanner will:
- ✅ Connect to Ethereum mainnet
- ✅ Fetch Uniswap V2 & SushiSwap pools
- ✅ Scan for arbitrage every 10 seconds
- ✅ Print top opportunities with P&L breakdown

Press `Ctrl+C` to stop.

---

## 📊 What You'll See

```
🔍 Scan 1
--------------------------------------------------------------------------------
   1. USDC -> WETH (uniswap_v2) -> USDC (sushiswap) [WETH/USDC]: gross=-0.45% slip=0.05% gas=0.25% net=-0.75%
   2. USDC -> WETH (sushiswap) -> USDC (uniswap_v2) [WETH/USDC]: gross=-0.74% slip=0.05% gas=0.25% net=-1.04%

  ✗ why: best_net=-0.75% (< thr by -0.75%), gross=-0.45% – slip=0.05% gas=0.25%

  → 0 above 0.00% threshold | EMA15 g=-0.45% n=-0.75% | cycles=2 | size≈$1000 hyp_P&L=$-0.00 | EV/scan=$-7.55
--------------------------------------------------------------------------------

🔍 Scan 2
...
```

### Understanding the Output

- **gross** - Raw profit before costs (negative = loss)
- **slip** - Slippage haircut (0.05% = 5 bps)
- **gas** - Gas cost as % of position ($2.50 / $1000 = 0.25%)
- **net** - Final P&L after all costs
- **✗ why** - Explains why no trade was executed
- **EMA15** - 15-period exponential moving average
- **EV/scan** - Expected value per scan

**Negative results are normal!** Uniswap & SushiSwap are very efficient, so cross-DEX arbitrage is rare.

---

## ⚙️ Configuration

### Change Scan Frequency

Edit `configs/dex_mev_eth_test.yaml`:
```yaml
poll_sec: 5  # Scan every 5 seconds instead of 10
```

### Adjust Position Size

```yaml
max_position_usd: 500  # Use $500 instead of $1000
```

### Change Threshold

```yaml
threshold_net_pct: 0.1  # Only show opportunities > 0.1% net profit
```

### Single Scan Mode

```bash
python3 run_dex_paper.py --once
```

Or set in config:
```yaml
once: true
```

---

## 🌐 Switching to Base

When you have Base pool addresses:

1. **Edit `configs/dex_mev.yaml`:**
   ```yaml
   dexes:
     - name: "baseswap"
       kind: "v2"
       fee_bps: 25
       pairs:
         - name: "WETH/USDC"
           address: "0xYOUR_VERIFIED_ADDRESS"
           base: "WETH"
           quote: "USDC"
   ```

2. **Run on Base:**
   ```bash
   python3 run_dex_paper.py --config configs/dex_mev.yaml
   ```

### Finding Base Pools

**Option A: Use Alchemy (Recommended)**
```bash
# Sign up: https://www.alchemy.com (free tier)
python3 scripts/scan_base_pairs.py \
  --rpc https://base-mainnet.g.alchemy.com/v2/YOUR_KEY \
  --blocks 500000
```

**Option B: Manual Discovery**
1. Go to https://basescan.org
2. Search for DEX pair contracts
3. Verify with:
   ```bash
   python3 scripts/check_pair.py https://mainnet.base.org 0xADDRESS
   ```

---

## 🛠️ Advanced Usage

### Run Tests
```bash
pytest tests/test_dex_paper.py -v
```

### Verify a Pool Address
```bash
python3 scripts/check_pair.py <rpc_url> <pair_address>
```

### Scan for Pools (Any Chain)
```bash
python3 scripts/scan_base_pairs.py --rpc <url> --blocks 500000
```

### Custom Config
```bash
python3 run_dex_paper.py --config my_custom_config.yaml
```

---

## 📈 Monitoring Tips

### Watch for Real Opportunities

Real arbitrage will show:
- **Positive net %** (e.g., `net=+0.42%`)
- **Above threshold** count > 0
- **Execution logged** (in paper mode, just simulated)

### Track Performance Over Time

The scanner tracks:
- **EMA15** - Moving averages of gross/net profits
- **EV/scan** - Expected value per scan
- **Hyp P&L** - Hypothetical P&L if all above-threshold opportunities executed

### Optimize Parameters

If you see opportunities but negative net:
- Reduce `slippage_bps` (if you're overcautious)
- Lower `threshold_net_pct` (to see more opportunities)
- Increase `max_position_usd` (to dilute gas cost %)

---

## 🎯 Common Use Cases

### 1. Monitor Ethereum DEX Spreads
```bash
# Run continuously, scan every 10s
python3 run_dex_paper.py
```

### 2. Test on Base (When Ready)
```bash
# Single scan to verify config
python3 run_dex_paper.py --config configs/dex_mev.yaml --once

# Continuous monitoring
python3 run_dex_paper.py --config configs/dex_mev.yaml
```

### 3. Quick Sanity Check
```bash
# Run once and exit
python3 run_dex_paper.py --once
```

### 4. High-Frequency Scanning
Edit config:
```yaml
poll_sec: 2  # Scan every 2 seconds
```

**Note:** Free RPCs may rate-limit you. Use Alchemy/Infura for high frequency.

---

## 🆘 Troubleshooting

### "Config error: At least one DEX must be configured"
You're using `configs/dex_mev.yaml` which is empty.

**Solution:** Use the Ethereum config:
```bash
python3 run_dex_paper.py --config configs/dex_mev_eth_test.yaml
```
Or just:
```bash
python3 run_dex_paper.py
```
(It defaults to Ethereum now!)

### "Failed to fetch pool: execution reverted"
The pool address is invalid or not a V2 pair.

**Solution:** Verify with:
```bash
python3 scripts/check_pair.py <rpc_url> <address>
```

### "RPC rate limit exceeded"
Free RPCs have rate limits.

**Solutions:**
- Increase `poll_sec` (scan less frequently)
- Use paid RPC (Alchemy/Infura free tiers are generous)
- Add `time.sleep()` between scans

### Only runs once
Check config:
```yaml
once: false  # Should be false for continuous scanning
```

Or override with CLI:
```bash
python3 run_dex_paper.py  # Runs continuously by default
```

---

## 📚 More Documentation

- **Full docs:** `README.md` (DEX Paper Trading section)
- **Script help:** `scripts/README.md`
- **Status:** `DEX_PAPER_STATUS.md`
- **Tests:** `tests/test_dex_paper.py`

---

## 🎉 You're Ready!

The scanner is production-ready and works out of the box. Just run:

```bash
python3 run_dex_paper.py
```

Happy arbitrage hunting! 🚀
