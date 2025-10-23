#!/bin/bash
# Week 2: Dry-Run Execution Test
# Tests execution logic without real transactions

set -e

LOG_DIR="logs/week2_dry_run"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/execution_${TIMESTAMP}.log"
METRICS_FILE="$LOG_DIR/execution_metrics_${TIMESTAMP}.txt"

echo "======================================================================"
echo "  WEEK 2: DRY-RUN EXECUTION TEST"
echo "======================================================================"
echo ""
echo "Starting dry-run execution mode..."
echo "  Config: configs/dex_bsc_dynamic.yaml"
echo "  Mode: DRY RUN (no real transactions)"
echo "  Log file: $LOG_FILE"
echo "  Metrics: $METRICS_FILE"
echo ""
echo "Tests to perform:"
echo "  ✓ Verify 'would execute' decisions"
echo "  ✓ Check safety mechanisms"
echo "  ✓ Validate opportunity selection"
echo "  ✓ Confirm rate limiting (5s)"
echo "  ✓ Test profit threshold enforcement"
echo ""
echo "Press Ctrl+C to stop..."
echo "======================================================================"
echo ""

# Create metrics file
cat > "$METRICS_FILE" << 'EOF'
# Week 2 Dry-Run Execution Metrics
# Generated: TIMESTAMP_PLACEHOLDER

## Test Objectives
1. Verify execution logic triggers on profitable opportunities
2. Confirm safety checks prevent bad trades
3. Validate rate limiting works correctly
4. Test profit threshold enforcement
5. Check execution statistics tracking

## Configuration
- Mode: DRY RUN (simulated)
- Min profit: $5.00 (default)
- Rate limit: 5 seconds
- Auto-execute: ON

## Results
EOF

sed -i '' "s/TIMESTAMP_PLACEHOLDER/$(date)/" "$METRICS_FILE" 2>/dev/null || sed -i "s/TIMESTAMP_PLACEHOLDER/$(date)/" "$METRICS_FILE"

# Function to extract execution metrics
extract_execution_metrics() {
    echo ""
    echo "======================================================================"
    echo "  DRY-RUN EXECUTION METRICS"
    echo "======================================================================"

    if [ -f "$LOG_FILE" ]; then
        # Count "would execute" decisions
        WOULD_EXECUTE=$(grep -c "\[DRY RUN\] Would execute" "$LOG_FILE" 2>/dev/null || echo "0")

        # Count opportunities found
        OPP_FOUND=$(grep -c "OPPORTUNITY FOUND" "$LOG_FILE" 2>/dev/null || echo "0")

        # Count safety blocks
        SAFETY_BLOCKS=$(grep -c "Execution blocked" "$LOG_FILE" 2>/dev/null || echo "0")

        # Count rate limit blocks
        RATE_LIMITS=$(grep -c "rate limit" "$LOG_FILE" 2>/dev/null || echo "0")

        # Extract simulated profits
        TOTAL_PROFIT=$(grep "profit: \$" "$LOG_FILE" | grep -oE '\$[0-9]+\.[0-9]+' | tr -d '$' | awk '{s+=$1} END {printf "%.2f", s}' || echo "0.00")

        echo ""
        echo "Execution Attempts:"
        echo "  Opportunities found:     $OPP_FOUND"
        echo "  Would execute:           $WOULD_EXECUTE"
        echo "  Blocked by safety:       $SAFETY_BLOCKS"
        echo "  Blocked by rate limit:   $RATE_LIMITS"
        echo ""
        echo "Simulated Performance:"
        echo "  Total simulated profit:  \$$TOTAL_PROFIT"
        echo "  Avg profit per trade:    \$$(echo "scale=2; $TOTAL_PROFIT / $WOULD_EXECUTE" | bc 2>/dev/null || echo "N/A")"
        echo ""

        # Save to metrics file
        cat >> "$METRICS_FILE" << METRICS_EOF

### Execution Statistics ($(date))

#### Decisions
- Opportunities found: $OPP_FOUND
- Would execute: $WOULD_EXECUTE
- Blocked by safety checks: $SAFETY_BLOCKS
- Blocked by rate limiting: $RATE_LIMITS
- Execution rate: $(echo "scale=1; $WOULD_EXECUTE * 100 / $OPP_FOUND" | bc 2>/dev/null || echo "N/A")%

#### Simulated Performance
- Total profit: \$$TOTAL_PROFIT
- Average per trade: \$$(echo "scale=2; $TOTAL_PROFIT / $WOULD_EXECUTE" | bc 2>/dev/null || echo "N/A")

#### Safety Check Examples
METRICS_EOF

        # Extract safety check examples
        grep "Execution blocked" "$LOG_FILE" | head -3 >> "$METRICS_FILE" 2>/dev/null || echo "No blocked executions" >> "$METRICS_FILE"

        cat >> "$METRICS_FILE" << METRICS_EOF

#### Successful Simulation Examples
METRICS_EOF

        grep "\[DRY RUN\] Would execute" "$LOG_FILE" | head -5 >> "$METRICS_FILE" 2>/dev/null || echo "No simulated executions" >> "$METRICS_FILE"

        echo "✓ Safety checks working: $([ "$SAFETY_BLOCKS" -gt "0" ] && echo "YES" || echo "UNKNOWN (no blocks yet)")"
        echo "✓ Rate limiting working: $([ "$RATE_LIMITS" -gt "0" ] && echo "YES" || echo "UNKNOWN (no limits hit)")"
        echo "✓ Execution logic working: $([ "$WOULD_EXECUTE" -gt "0" ] && echo "YES" || echo "NO (no profitable opps)")"
        echo ""
        echo "Metrics saved to: $METRICS_FILE"
        echo ""
    else
        echo "No log file found yet..."
    fi

    echo "======================================================================"
}

# Trap Ctrl+C
trap 'echo ""; echo "Stopping dry-run test..."; extract_execution_metrics; exit 0' INT

# Run with dry-run execution enabled
echo "Starting execution-enabled scanner in DRY-RUN mode..."
echo ""

python3 run_dex_with_execution.py \
    --config configs/dex_bsc_dynamic.yaml \
    --dry-run \
    --auto-execute \
    --min-profit 5.0 \
    2>&1 | tee "$LOG_FILE"

# Show metrics on normal exit
extract_execution_metrics
