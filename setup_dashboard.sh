#!/bin/bash
# Quick setup script for Web Dashboard

set -e

echo "🚀 Setting up Triangular Arbitrage Dashboard..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 16+ first."
    exit 1
fi

echo "✅ Python $(python3 --version) detected"
echo "✅ Node.js $(node --version) detected"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -q fastapi uvicorn websockets 2>/dev/null || pip3 install fastapi uvicorn websockets
echo "✅ Python dependencies installed"
echo ""

# Setup React frontend
echo "📦 Installing React dependencies..."
cd web_ui
npm install --silent
echo "✅ React dependencies installed"
echo ""

echo "🔨 Building React frontend..."
npm run build
echo "✅ React frontend built"
cd ..
echo ""

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file with defaults..."
    cat > .env << EOF
# Trading Configuration
TRADING_MODE=paper
PAPER_USDT=1000
PAPER_USDC=1000

# Filter Configuration (empty = allow all)
SYMBOL_ALLOWLIST=
TRIANGLE_BASES=
EXCLUDE_SYMBOLS=

# Trading Parameters
MIN_PROFIT_THRESHOLD=0.5
MAX_POSITION_SIZE=100

# Web Server
PORT=8000

# API Keys (for live trading - KEEP SECRET!)
# KRAKEN_API_KEY=your_key_here
# KRAKEN_API_SECRET=your_secret_here
# BINANCE_API_KEY=your_key_here
# BINANCE_API_SECRET=your_secret_here
EOF
    echo "✅ Created .env file"
else
    echo "✅ .env file already exists"
fi
echo ""

echo "✨ Setup complete!"
echo ""
echo "To start the dashboard, run:"
echo "  python web_server.py"
echo ""
echo "Then open your browser to:"
echo "  http://localhost:8000"
echo ""
