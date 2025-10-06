#!/usr/bin/env python3
"""
FastAPI Web Server for Triangular Arbitrage Dashboard
Provides REST API and WebSocket endpoints for real-time monitoring
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Triangular Arbitrage Dashboard")

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for API responses
class TradeHistoryItem(BaseModel):
    timestamp: str
    cycle: str
    profit_pct: float
    profit_usd: float
    status: str


class BalanceInfo(BaseModel):
    total_equity_usd: float
    cash_balance: float
    asset_balances: Dict[str, float]
    total_trades: int
    total_profit_usd: float


class OpportunityInfo(BaseModel):
    cycle: List[str]
    profit_pct: float
    expected_profit_usd: float
    timestamp: str


class SystemStats(BaseModel):
    uptime_seconds: int
    total_scans: int
    opportunities_found: int
    trades_executed: int
    success_rate: float


# Global state manager
class StateManager:
    def __init__(self):
        self.opportunities: List[OpportunityInfo] = []
        self.recent_trades: List[TradeHistoryItem] = []
        self.balance: BalanceInfo = BalanceInfo(
            total_equity_usd=1000.0,
            cash_balance=1000.0,
            asset_balances={},
            total_trades=0,
            total_profit_usd=0.0,
        )
        self.stats: SystemStats = SystemStats(
            uptime_seconds=0,
            total_scans=0,
            opportunities_found=0,
            trades_executed=0,
            success_rate=0.0,
        )
        self.logs: List[str] = []
        self.connected_clients: List[WebSocket] = []
        self.bot_running = False
        self.trading_mode = "paper"  # Default to paper trading
        self.start_time = datetime.now()
        self.bot_task = None  # Track the bot task for cancellation

    async def broadcast(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        disconnected = []
        for client in self.connected_clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)

        # Remove disconnected clients
        for client in disconnected:
            self.connected_clients.remove(client)

    def add_log(self, message: str):
        """Add log message and broadcast to clients"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        # Keep only last 100 logs
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]

        # Parse log messages to extract opportunities and trades
        self._parse_log_for_data(message, timestamp)

    def _parse_log_for_data(self, message: str, timestamp: str):
        """Parse log messages to extract opportunities and trades"""
        import re

        # Parse opportunities: "1. USDT -> RVN -> USD: gross=+0.46% fees=0.30% net=+0.11%"
        opp_match = re.match(
            r"\d+\.\s+(.+?):\s+gross=\+?([-\d.]+)%.*?net=\+?([-\d.]+)%", message
        )
        if opp_match:
            cycle_str = opp_match.group(1)
            net_pct = float(opp_match.group(3))

            # Extract cycle currencies
            cycle = [c.strip() for c in cycle_str.split("->")]

            # Normalize cycle to avoid duplicates (same cycle from different starting points)
            # Sort the cycle to create a canonical representation
            cycle_set = frozenset(cycle)

            # Check if this cycle already exists (by checking if all currencies match)
            is_duplicate = False
            for existing_opp in self.opportunities:
                if frozenset(existing_opp.cycle) == cycle_set:
                    # This is the same triangle, keep the one with higher profit
                    if net_pct > existing_opp.profit_pct:
                        self.opportunities.remove(existing_opp)
                        break
                    else:
                        is_duplicate = True
                        break

            if not is_duplicate:
                # Add to opportunities (keep last 10)
                opp = OpportunityInfo(
                    cycle=cycle,
                    profit_pct=net_pct,
                    expected_profit_usd=net_pct
                    * 10.0,  # Rough estimate based on $1000 balance
                    timestamp=timestamp,
                )
                self.opportunities.insert(0, opp)
                self.opportunities = self.opportunities[:10]

            # Update stats (only count unique cycles)
            if not is_duplicate:
                self.stats.opportunities_found += 1

        # Parse scan count for stats
        scan_match = re.match(r"🔍 Scan (\d+)", message)
        if scan_match:
            self.stats.total_scans = int(scan_match.group(1))

        # Parse equity for balance
        equity_match = re.search(r"💼 Equity: \$([,\d.]+)", message)
        if equity_match:
            equity_str = equity_match.group(1).replace(",", "")
            self.balance.total_equity_usd = float(equity_str)
            self.balance.cash_balance = float(equity_str)

        # Parse trade execution success
        if "✅ Opportunity" in message and "executed successfully" in message:
            # Extract opportunity number if possible
            opp_match = re.search(r"Opportunity (\d+)", message)
            if opp_match and self.opportunities:
                # Add to recent trades
                idx = int(opp_match.group(1)) - 1
                if idx < len(self.opportunities):
                    opp = self.opportunities[idx]
                    trade = TradeHistoryItem(
                        timestamp=timestamp,
                        cycle=" -> ".join(opp.cycle),
                        profit_pct=opp.profit_pct,
                        profit_usd=opp.expected_profit_usd,
                        status="completed",
                    )
                    self.recent_trades.insert(0, trade)
                    self.recent_trades = self.recent_trades[:20]  # Keep last 20

            self.stats.trades_executed += 1
            # Calculate success rate
            if self.stats.opportunities_found > 0:
                self.stats.success_rate = (
                    self.stats.trades_executed / self.stats.opportunities_found * 100
                )

        # Parse trade execution attempt (for paper trading logs)
        if "Executing trade" in message or "Paper trade:" in message:
            # Paper trading execution
            trade_match = re.search(r"Paper trade:.*?([-\d.]+)%", message)
            if trade_match:
                profit_pct = float(trade_match.group(1))
                if self.opportunities:
                    opp = self.opportunities[0]
                    trade = TradeHistoryItem(
                        timestamp=timestamp,
                        cycle=" -> ".join(opp.cycle),
                        profit_pct=profit_pct,
                        profit_usd=profit_pct * 10.0,
                        status="completed",
                    )
                    self.recent_trades.insert(0, trade)
                    self.recent_trades = self.recent_trades[:20]
                    self.stats.trades_executed += 1

    def update_from_db(self):
        """Update state from database"""
        try:
            conn = sqlite3.connect("trade_state.db")
            cursor = conn.cursor()

            # Check if equity_fills table exists
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='equity_fills'
            """
            )
            table_exists = cursor.fetchone() is not None

            if table_exists:
                # Get recent trades from equity_fills table
                cursor.execute(
                    """
                    SELECT timestamp, cycle_id, realized_pnl
                    FROM equity_fills
                    ORDER BY timestamp DESC
                    LIMIT 20
                """
                )
                trades = cursor.fetchall()

                self.recent_trades = [
                    TradeHistoryItem(
                        timestamp=trade[0],
                        cycle=str(trade[1]),
                        profit_pct=0.0,  # Calculate from realized_pnl if needed
                        profit_usd=trade[2] or 0.0,
                        status="completed",
                    )
                    for trade in trades
                ]

            conn.close()
        except Exception as e:
            logger.error(f"Error updating from DB: {e}")


state = StateManager()


# API Endpoints
@app.get("/")
async def root():
    """Serve the React dashboard"""
    return FileResponse("web_ui/build/index.html")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "bot_running": state.bot_running}


@app.get("/api/balance")
async def get_balance():
    """Get current balance information"""
    state.update_from_db()
    return state.balance


@app.get("/api/opportunities")
async def get_opportunities():
    """Get current arbitrage opportunities"""
    return {"opportunities": state.opportunities}


@app.get("/api/trades")
async def get_trade_history():
    """Get trade history"""
    state.update_from_db()
    return {"trades": state.recent_trades}


@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    state.stats.uptime_seconds = int(
        (datetime.now() - state.start_time).total_seconds()
    )
    return state.stats


@app.get("/api/logs")
async def get_logs():
    """Get recent logs"""
    return {"logs": state.logs[-50:]}  # Last 50 logs


@app.post("/api/bot/start")
async def start_bot(mode: str = "paper"):
    """Start the arbitrage bot

    Args:
        mode: Trading mode - 'paper' or 'live'
    """
    if state.bot_running:
        return {"status": "already_running"}

    if mode not in ["paper", "live"]:
        return {"status": "error", "message": "Invalid mode. Use 'paper' or 'live'"}

    # Check API keys if live mode
    if mode == "live":
        kraken_key = os.getenv("KRAKEN_API_KEY")
        binance_key = os.getenv("BINANCE_API_KEY")
        coinbase_key = os.getenv("COINBASE_API_KEY")

        if not any([kraken_key, binance_key, coinbase_key]):
            return {
                "status": "error",
                "message": "No API keys configured. Set API keys in .env file for live trading.",
            }

    state.bot_running = True
    state.trading_mode = mode

    mode_emoji = "📝" if mode == "paper" else "💰"
    mode_text = "PAPER TRADING" if mode == "paper" else "LIVE TRADING"
    state.add_log(f"{mode_emoji} Bot started in {mode_text} mode")

    await state.broadcast({"type": "bot_status", "running": True, "mode": mode})

    # Start bot in background and save task reference
    state.bot_task = asyncio.create_task(run_bot_background())

    return {"status": "started", "mode": mode}


@app.post("/api/bot/stop")
async def stop_bot():
    """Stop the arbitrage bot"""
    if not state.bot_running:
        return {"status": "not_running"}

    state.bot_running = False
    state.add_log("🛑 Stopping bot...")

    # Cancel the bot task if it exists
    if state.bot_task and not state.bot_task.done():
        state.bot_task.cancel()
        try:
            await state.bot_task
        except asyncio.CancelledError:
            pass  # Expected when canceling

    state.add_log("✅ Bot stopped via web interface")
    await state.broadcast({"type": "bot_status", "running": False})

    return {"status": "stopped"}


class ConfigUpdate(BaseModel):
    min_profit_threshold: Optional[float] = None
    topn: Optional[int] = None


@app.get("/api/config")
async def get_config():
    """Get current bot configuration"""
    return {
        "min_profit_threshold": float(os.getenv("MIN_PROFIT_THRESHOLD", "0.2")),
        "topn": int(os.getenv("TOPN", "3")),
    }


@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    """Update bot configuration (requires bot restart to take effect)"""
    updated = []

    if config.min_profit_threshold is not None:
        os.environ["MIN_PROFIT_THRESHOLD"] = str(config.min_profit_threshold)
        updated.append(f"MIN_PROFIT_THRESHOLD={config.min_profit_threshold}")

    if config.topn is not None:
        os.environ["TOPN"] = str(config.topn)
        updated.append(f"TOPN={config.topn}")

    if updated:
        state.add_log(f"⚙️ Configuration updated: {', '.join(updated)}")
        await state.broadcast(
            {
                "type": "config_updated",
                "config": {
                    "min_profit_threshold": float(
                        os.getenv("MIN_PROFIT_THRESHOLD", "0.2")
                    ),
                    "topn": int(os.getenv("TOPN", "3")),
                },
            }
        )

    return {
        "status": "updated",
        "changes": updated,
        "note": "Restart bot for changes to take effect",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    state.connected_clients.append(websocket)
    logger.info(f"Client connected. Total clients: {len(state.connected_clients)}")

    try:
        # Send initial state
        await websocket.send_json(
            {
                "type": "initial_state",
                "balance": state.balance.model_dump(),
                "stats": state.stats.model_dump(),
                "opportunities": [opp.model_dump() for opp in state.opportunities],
                "bot_running": state.bot_running,
                "trading_mode": state.trading_mode,
            }
        )

        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            # Handle client messages if needed
            logger.info(f"Received from client: {data}")

    except WebSocketDisconnect:
        state.connected_clients.remove(websocket)
        logger.info(
            f"Client disconnected. Total clients: {len(state.connected_clients)}"
        )


async def run_bot_background():
    """Run the arbitrage bot in the background"""
    import sys

    from trading_arbitrage import RealTriangularArbitrage

    state.add_log("Initializing arbitrage bot...")

    # Capture stdout/stderr to log to web UI
    class WebLogger:
        def __init__(self, original_stream):
            self.original = original_stream
            self.buffer = []

        def write(self, text):
            # Still write to original stream for debugging
            self.original.write(text)

            # Buffer partial lines
            if text:
                self.buffer.append(text)
                # Only process complete lines
                if "\n" in text:
                    full_text = "".join(self.buffer).strip()
                    if full_text:
                        state.add_log(full_text)
                        asyncio.create_task(
                            state.broadcast({"type": "log", "message": full_text})
                        )
                    self.buffer = []

        def flush(self):
            self.original.flush()

    # Replace stdout/stderr temporarily
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = WebLogger(original_stdout)
    sys.stderr = WebLogger(original_stderr)

    try:
        exchanges_to_try = ["binanceus", "kraken", "kucoin", "coinbase"]

        for exchange_name in exchanges_to_try:
            if not state.bot_running:
                break

            state.add_log(f"Trying {exchange_name}...")

            try:
                # Use the mode selected by the user
                trading_mode = state.trading_mode
                trader = RealTriangularArbitrage(exchange_name, trading_mode)

                # Run the bot
                state.add_log(
                    f"Connected to {exchange_name}, starting trading session..."
                )
                await trader.run_trading_session()
                break

            except Exception as e:
                error_msg = f"Failed to connect to {exchange_name}: {str(e)}"
                state.add_log(error_msg)
                logger.error(error_msg, exc_info=True)
                continue

    finally:
        # Restore original stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    state.bot_running = False
    state.add_log("Bot stopped")
    await state.broadcast({"type": "bot_status", "running": False})


# Background task to periodically update stats
async def update_stats_periodically():
    """Update stats every 5 seconds"""
    while True:
        await asyncio.sleep(5)
        if state.bot_running:
            state.update_from_db()
            await state.broadcast(
                {
                    "type": "update",
                    "balance": state.balance.model_dump(),
                    "opportunities": [opp.model_dump() for opp in state.opportunities],
                }
            )


@app.on_event("startup")
async def startup_event():
    """Run on server startup"""
    logger.info("Starting Triangular Arbitrage Dashboard Server")
    state.add_log("Dashboard server started")
    # Start background stats updater
    asyncio.create_task(update_stats_periodically())


@app.on_event("shutdown")
async def shutdown_event():
    """Run on server shutdown"""
    logger.info("Shutting down dashboard server")
    state.bot_running = False


# Mount static files (React build)
try:
    app.mount("/static", StaticFiles(directory="web_ui/build/static"), name="static")
except Exception:
    logger.warning("Static files directory not found. Build React app first.")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
