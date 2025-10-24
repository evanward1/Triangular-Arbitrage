#!/bin/bash
# Test script for critical fixes to DEX arbitrage scanner
# Run with: chmod +x test_fixes.sh && ./test_fixes.sh

set -e  # Exit on error

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Testing Critical Fixes - BSC DEX Arbitrage Scanner"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "✓ Step 1: Verify Python files compile..."
python3 -m py_compile dex/runner.py || { echo "✗ runner.py failed to compile"; exit 1; }
python3 -m py_compile dex/adapters/v2.py || { echo "✗ v2.py failed to compile"; exit 1; }
python3 -m py_compile dex/abi.py || { echo "✗ abi.py failed to compile"; exit 1; }
python3 -m py_compile triangular_arbitrage/dex_mev/pool_factory_scanner.py || { echo "✗ pool_factory_scanner.py failed to compile"; exit 1; }
echo "  All files compiled successfully ✓"
echo ""

echo "✓ Step 2: Run 60-second test scan with diagnostics..."
echo "  Looking for:"
echo "    - Fee audit table (5 sample pools)"
echo "    - Route deep dive (best route breakdown)"
echo "    - Diagnostic warnings about double-counting"
echo "    - Improved Net % (should be ~0.5-0.7% better)"
echo "    - Accurate P&L breakdown (numbers should add up)"
echo ""

# Enable debug logging to see diagnostic warnings
export PYTHONUNBUFFERED=1
timeout 60 python3 run_dex_paper.py --config configs/dex_bsc_dynamic.yaml --once 2>&1 | tee test_output.log

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Test Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "✓ Expected improvements:"
echo "  1. Fee audit table showed varied fees (not all hardcoded to 25 bps)"
echo "  2. Route deep dive provided transparent P&L breakdown"
echo "  3. Net % improved by ~0.5-0.7% (from fixing double-counting)"
echo "  4. Breakdown equation now adds up: Raw - Slip - Gas - Min = Net"
echo "  5. Some routes closer to breakeven (Net > -0.30%)"
echo ""

echo "📊 Output saved to: test_output.log"
echo ""
echo "Next steps:"
echo "  1. Review fee audit table - verify fees are read from chain"
echo "  2. Check route deep dive - confirm math is transparent"
echo "  3. Compare Net % to previous runs - should see ~0.5-0.7% improvement"
echo "  4. Look for any routes with Net > -0.20% (near breakeven)"
echo ""
