#!/bin/bash
# Week 1: Optimized Paper Trading Monitor
# Runs scanner and collects performance metrics

set -e

LOG_DIR="logs/week1_paper_trading"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/scan_${TIMESTAMP}.log"
METRICS_FILE="$LOG_DIR/metrics_${TIMESTAMP}.txt"

echo "======================================================================"
echo "  WEEK 1: OPTIMIZED PAPER TRADING TEST"
echo "======================================================================"
echo ""
echo "Starting optimized paper trading scanner..."
echo "  Config: configs/dex_bsc_dynamic.yaml"
echo "  Log file: $LOG_FILE"
echo "  Metrics: $METRICS_FILE"
echo ""
echo "Optimizations enabled:"
echo "  ✓ Exact slippage formula (adaptive 1.2x buffer)"
echo "  ✓ Pool quality filter (min score: 55/100)"
echo "  ✓ Fast scanning (2s intervals)"
echo "  ✓ Smart filtering (0.15% min profit)"
echo ""
echo "Press Ctrl+C to stop..."
echo "======================================================================"
echo ""

# Create metrics file header
cat > "$METRICS_FILE" << 'EOF'
# Week 1 Performance Metrics
# Generated: TIMESTAMP_PLACEHOLDER
# Duration: 24-48 hours recommended

## Configuration
- Scan interval: 2 seconds
- Threshold: 0.15% net profit
- Slippage buffer: 1.2x (adaptive)
- Pool quality min: 55/100

## Metrics to Track
EOF

# Replace timestamp
sed -i '' "s/TIMESTAMP_PLACEHOLDER/$(date)/" "$METRICS_FILE" 2>/dev/null || sed -i "s/TIMESTAMP_PLACEHOLDER/$(date)/" "$METRICS_FILE"

# Function to extract metrics from logs
extract_metrics() {
    echo ""
    echo "======================================================================"
    echo "  PERFORMANCE METRICS SUMMARY"
    echo "======================================================================"

    if [ -f "$LOG_FILE" ]; then
        # Count total scans
        TOTAL_SCANS=$(grep -c "Top Arbitrage Routes (Scan" "$LOG_FILE" 2>/dev/null || echo "0")

        # Count opportunities found (profitable routes)
        OPPORTUNITIES=$(grep -c "PROFITABLE routes found" "$LOG_FILE" 2>/dev/null || echo "0")

        # Extract best net profit seen
        BEST_NET=$(grep "Net:" "$LOG_FILE" | grep -oE '\+[0-9]+\.[0-9]+%' | sort -t+ -k2 -nr | head -1 || echo "N/A")

        # Count pools scanned
        POOLS_SCANNED=$(grep "Fetched.*V2 pools" "$LOG_FILE" | tail -1 | grep -oE '[0-9]+' | head -1 || echo "N/A")

        # Count filtered pools
        POOLS_FILTERED=$(grep "Pool quality filter: kept" "$LOG_FILE" | tail -1 || echo "N/A")

        echo ""
        echo "Scans completed:      $TOTAL_SCANS"
        echo "Opportunities found:  $OPPORTUNITIES"
        echo "Best net profit:      $BEST_NET"
        echo "Pools scanned:        $POOLS_SCANNED"
        echo "Pool filtering:       $POOLS_FILTERED"
        echo ""

        # Save to metrics file
        cat >> "$METRICS_FILE" << METRICS_EOF

## Results ($(date))

### Overview
- Total scans: $TOTAL_SCANS
- Opportunities found: $OPPORTUNITIES
- Opportunities per scan: $(echo "scale=2; $OPPORTUNITIES / $TOTAL_SCANS" | bc 2>/dev/null || echo "N/A")
- Best net profit: $BEST_NET

### Pool Quality
- Pools scanned: $POOLS_SCANNED
- Filtering: $POOLS_FILTERED

### Sample Opportunities
METRICS_EOF

        # Extract top 5 opportunities
        grep "✓.*Net:" "$LOG_FILE" | head -5 >> "$METRICS_FILE" 2>/dev/null || echo "No opportunities in sample period" >> "$METRICS_FILE"

        echo "Metrics saved to: $METRICS_FILE"
        echo ""
    else
        echo "No log file found yet..."
    fi

    echo "======================================================================"
}

# Trap Ctrl+C to show metrics before exit
trap 'echo ""; echo "Stopping scanner..."; extract_metrics; exit 0' INT

# Run scanner with logging
python3 run_dex_paper.py --config configs/dex_bsc_dynamic.yaml 2>&1 | tee "$LOG_FILE"

# If script exits normally, show metrics
extract_metrics
