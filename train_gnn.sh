#!/bin/bash
# GNN Training Helper Script
# This script helps you train and monitor the GNN optimizer

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🧠 GNN Training & Monitoring Tool${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to show current GNN status
show_status() {
    echo -e "${GREEN}📊 Current GNN Status:${NC}"
    python3 << 'EOF'
from triangular_arbitrage.gnn_optimizer import GNNArbitrageOptimizer
import os

if not os.path.exists("logs/gnn_state.json"):
    print("  ⚠️  No training data yet (logs/gnn_state.json not found)")
    print("  💡 Run option 1 or 2 to start training")
else:
    gnn = GNNArbitrageOptimizer()
    stats = gnn.get_statistics()
    print(f"  ✅ Tracked edges: {stats['tracked_edges']}")
    print(f"  ✅ Unique cycles: {stats['unique_cycles']}")
    print(f"  ✅ Total trades: {stats['total_trades']}")

    # Training level
    trades = stats['total_trades']
    if trades == 0:
        level = "Not Started"
        emoji = "⚪"
    elif trades < 20:
        level = "Beginner"
        emoji = "🟡"
    elif trades < 50:
        level = "Learning"
        emoji = "🟠"
    elif trades < 100:
        level = "Intermediate"
        emoji = "🔵"
    else:
        level = "Expert"
        emoji = "🟢"

    print(f"\n  {emoji} Training Level: {level} ({trades} trades)")
EOF
    echo ""
}

# Function to show top learned cycles
show_learned() {
    echo -e "${GREEN}📚 Top Learned Cycles:${NC}"
    python3 << 'EOF'
from triangular_arbitrage.gnn_optimizer import GNNArbitrageOptimizer
import os

if os.path.exists("logs/gnn_state.json"):
    gnn = GNNArbitrageOptimizer()

    # Get some example scores
    test_cycles = [
        ["BTC", "ETH", "USDT"],
        ["ETH", "BNB", "USDT"],
        ["DOGE", "SHIB", "USDT"],
        ["BTC", "SOL", "USDT"],
    ]

    print("  Cycle                    Score    Status")
    print("  " + "-" * 45)
    for cycle in test_cycles:
        score = gnn.get_cycle_score(cycle)
        status = "✅ APPROVED" if score >= 1.0 else "❌ BLOCKED"
        cycle_str = "->".join(cycle)
        print(f"  {cycle_str:20} {score:6.4f}   {status}")
else:
    print("  ⚠️  No training data yet")
EOF
    echo ""
}

# Show current status
show_status

# Menu
echo -e "${YELLOW}Choose training option:${NC}"
echo "  1) Quick Test Training (30 sample trades, ~1 second)"
echo "  2) Paper Trading (Safe, no real money)"
echo "  3) Live Trading (Real money, use after paper training)"
echo "  4) Show Detailed GNN State"
echo "  5) Show Learning Progress"
echo "  6) Reset GNN (Clear all training)"
echo "  7) Exit"
echo ""
read -p "Enter choice [1-7]: " choice

case $choice in
    1)
        echo -e "${BLUE}🧪 Running quick test training...${NC}"
        python tests/integration/test_gnn_scoring.py
        echo ""
        show_status
        show_learned
        ;;
    2)
        echo -e "${BLUE}📝 Starting paper trading...${NC}"
        echo -e "${YELLOW}💡 Press Ctrl+C to stop${NC}"
        echo ""
        python run_clean.py cex --paper
        ;;
    3)
        echo -e "${RED}⚠️  WARNING: This uses REAL MONEY!${NC}"
        read -p "Are you sure? Type 'YES' to continue: " confirm
        if [ "$confirm" = "YES" ]; then
            echo -e "${BLUE}💰 Starting live trading...${NC}"
            python run_clean.py cex --live
        else
            echo "Cancelled."
        fi
        ;;
    4)
        echo -e "${BLUE}📄 GNN State File:${NC}"
        if [ -f "logs/gnn_state.json" ]; then
            cat logs/gnn_state.json | python -m json.tool | head -100
        else
            echo "No state file found yet."
        fi
        ;;
    5)
        echo -e "${BLUE}📈 Learning Progress:${NC}"
        show_learned
        ;;
    6)
        echo -e "${RED}⚠️  This will delete all training data!${NC}"
        read -p "Are you sure? Type 'YES' to confirm: " confirm
        if [ "$confirm" = "YES" ]; then
            rm -f logs/gnn_state.json
            echo -e "${GREEN}✅ GNN reset complete${NC}"
        else
            echo "Cancelled."
        fi
        ;;
    7)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac
