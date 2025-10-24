#!/bin/bash
# Quick status check for Week 1 monitoring

echo "======================================================================"
echo "  WEEK 1 MONITORING STATUS"
echo "======================================================================"
echo ""

# Check if log exists
LOG_FILE=$(ls -t logs/week1_paper_trading/scan_*.log 2>/dev/null | head -1)

if [ -z "$LOG_FILE" ]; then
    echo "❌ No log file found"
    echo "   Scanner may not be running"
    exit 1
fi

echo "✓ Scanner is running"
echo "  Log file: $LOG_FILE"
echo ""

# Get start time
START_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOG_FILE" 2>/dev/null || stat -c "%y" "$LOG_FILE" 2>/dev/null | cut -d. -f1)
echo "Started: $START_TIME"

# Calculate runtime
if command -v stat &> /dev/null; then
    LOG_SIZE=$(ls -lh "$LOG_FILE" | awk '{print $5}')
    echo "Log size: $LOG_SIZE"
fi

echo ""
echo "────────────────────────────────────────────────────────────────"
echo "  RECENT ACTIVITY (last 20 lines)"
echo "────────────────────────────────────────────────────────────────"
echo ""

tail -20 "$LOG_FILE"

echo ""
echo "────────────────────────────────────────────────────────────────"

# Check for opportunities
OPP_COUNT=$(grep -c "PROFITABLE" "$LOG_FILE" 2>/dev/null || echo "0")
SCAN_COUNT=$(grep -c "Top Arbitrage Routes" "$LOG_FILE" 2>/dev/null || echo "0")

if [ "$SCAN_COUNT" -gt "0" ]; then
    echo "  STATISTICS"
    echo "────────────────────────────────────────────────────────────────"
    echo ""
    echo "Scans completed:      $SCAN_COUNT"
    echo "Opportunities found:  $OPP_COUNT"
    echo "Opportunities/scan:   $(echo "scale=2; $OPP_COUNT / $SCAN_COUNT" | bc 2>/dev/null || echo "N/A")"
    echo ""

    # Best opportunity
    BEST=$(grep "Net:" "$LOG_FILE" | grep -oE '\+[0-9]+\.[0-9]+%' | sort -t+ -k2 -nr | head -1 || echo "N/A")
    echo "Best net profit seen: $BEST"
    echo ""
fi

echo "======================================================================"
echo ""
echo "Commands:"
echo "  View live log:     tail -f $LOG_FILE"
echo "  Stop monitoring:   pkill -f monitor_week1.sh"
echo "  Check again:       ./check_status.sh"
echo ""
