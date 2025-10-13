#!/usr/bin/env python3
"""
FastAPI Web Server for Triangular Arbitrage Dashboard
Provides REST API and WebSocket endpoints for real-time monitoring
Supports both CEX and DEX/MEV trading modes
"""

import asyncio
import logging
import os
import sqlite3
import time
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import DecisionEngine for explicit trade execution decisions
from decision_engine import DecisionEngine

# ============================================================================
# Mode Enum - Single Source of Truth
# ============================================================================


class TradingMode(str, Enum):
    """Trading mode for DEX/MEV operations"""

    OFF = "off"
    PAPER_LIVE_CHAIN = "paper_live_chain"  # Paper trading with live chain data
    LIVE = "live"  # Live trading with real broadcasts


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

        # Parse opportunities: "1. USDT -> RVN -> USD: profit before costs=+0.46%
        # trading fees=0.30% final profit=+0.11%"
        opp_match = re.match(
            r"\d+\.\s+(.+?):\s+profit before costs=\+?([-\d.]+)%"
            r".*?final profit=\+?([-\d.]+)%",
            message,
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


# ============================================================================
# DEX/MEV Models and State Management
# ============================================================================


class DexOpportunity(BaseModel):
    id: str
    path: List[str]
    gross_bps: float
    net_bps: float
    gas_bps: float
    slip_bps: float
    size_usd: float
    legs: List[Dict[str, Any]]
    ts: float


class DexFill(BaseModel):
    id: str
    paper: bool
    tx_hash: Optional[str]
    net_bps: float
    pnl_usd: float
    ts: float
    simulation: Optional[
        Dict[str, Any]
    ] = None  # gas_used, success for paper_live_chain


class DexEquityPoint(BaseModel):
    ts: float
    equity_usd: float


class DexConfig(BaseModel):
    size_usd: Optional[float] = None
    min_profit_threshold_bps: Optional[float] = None
    slippage_mode: Optional[str] = None
    slippage_floor_bps: Optional[float] = None
    expected_maker_legs: Optional[int] = None
    gas_model: Optional[str] = None
    paper: Optional[bool] = None  # Legacy - maps to mode
    mode: Optional[str] = None  # paper_live_chain or live
    chain_id: Optional[int] = None
    rpc_url: Optional[str] = None
    gas_oracle: Optional[str] = None
    simulate_via: Optional[str] = None  # eth_call or mev_sim
    log_tx_objects: Optional[bool] = None
    rpc_label: Optional[str] = None


class DexControlRequest(BaseModel):
    action: str  # "start" or "stop"
    mode: Optional[str] = None  # "paper_live_chain" or "live" (for start action)
    config: Optional[DexConfig] = None


class DexStateManager:
    """Manages DEX/MEV trading state with ring buffers for efficient data access"""

    def __init__(self, max_opportunities: int = 50, max_fills: int = 100):
        self.running = False
        self.mode = TradingMode.PAPER_LIVE_CHAIN  # Default to safe mode
        self.chain_id = 1
        self.scan_interval_sec = 10
        self.pools_loaded = 0
        self.last_scan_ts = 0.0
        self.best_gross_bps = 0.0
        self.best_net_bps = 0.0

        # Ring buffers for efficient data storage
        self.opportunities: Deque[DexOpportunity] = deque(maxlen=max_opportunities)
        self.fills: Deque[DexFill] = deque(maxlen=max_fills)
        self.equity_history: Deque[DexEquityPoint] = deque(maxlen=1000)
        self.logs: Deque[str] = deque(maxlen=100)  # Keep last 100 logs

        # Decision history for debugging trade execution
        self.decisions: Deque[Dict[str, Any]] = deque(
            maxlen=100
        )  # Keep last 100 decisions
        self.last_decision: Optional[Dict[str, Any]] = None

        # Current config
        self.config = {
            "size_usd": 1000,
            "min_profit_threshold_bps": 0,
            "slippage_mode": "dynamic",
            "slippage_floor_bps": 5,
            "expected_maker_legs": 2,
            "gas_model": "fast",
            "rpc_url": "https://eth-mainnet.g.alchemy.com/v2/demo",
            "gas_oracle": "etherscan",
            "simulate_via": "eth_call",
            "log_tx_objects": False,
        }

        # Connected WebSocket clients (shared with main state)
        self.ws_clients: List[WebSocket] = []

        # Background task reference
        self.runner_task: Optional[asyncio.Task] = None

        # Initialize decision engine
        self.decision_engine: Optional[DecisionEngine] = None

    def update_config(self, config: DexConfig):
        """Update configuration from request"""
        if config.size_usd is not None:
            self.config["size_usd"] = config.size_usd
        if config.min_profit_threshold_bps is not None:
            self.config["min_profit_threshold_bps"] = config.min_profit_threshold_bps
        if config.slippage_mode is not None:
            self.config["slippage_mode"] = config.slippage_mode
        if config.slippage_floor_bps is not None:
            self.config["slippage_floor_bps"] = config.slippage_floor_bps
        if config.expected_maker_legs is not None:
            self.config["expected_maker_legs"] = config.expected_maker_legs
        if config.gas_model is not None:
            self.config["gas_model"] = config.gas_model

        # Handle mode - new way or legacy paper flag
        if config.mode is not None:
            if config.mode == "paper_live_chain":
                self.mode = TradingMode.PAPER_LIVE_CHAIN
            elif config.mode == "live":
                self.mode = TradingMode.LIVE
            else:
                self.mode = TradingMode.OFF
        elif config.paper is not None:
            # Legacy support: paper=True -> paper_live_chain, paper=False -> live
            self.mode = (
                TradingMode.PAPER_LIVE_CHAIN if config.paper else TradingMode.LIVE
            )

        if config.chain_id is not None:
            self.chain_id = config.chain_id
        if config.rpc_url is not None:
            self.config["rpc_url"] = config.rpc_url
        if config.gas_oracle is not None:
            self.config["gas_oracle"] = config.gas_oracle
        if config.simulate_via is not None:
            self.config["simulate_via"] = config.simulate_via
        if config.log_tx_objects is not None:
            self.config["log_tx_objects"] = config.log_tx_objects
        if config.rpc_label is not None:
            self.config["rpc_label"] = config.rpc_label

    def add_opportunity(self, opp: DexOpportunity):
        """Add opportunity and update best values"""
        self.opportunities.append(opp)
        self.best_gross_bps = max(self.best_gross_bps, opp.gross_bps)
        self.best_net_bps = max(self.best_net_bps, opp.net_bps)

    def add_fill(self, fill: DexFill):
        """Add fill to history"""
        self.fills.append(fill)

    def add_equity_point(self, equity_usd: float):
        """Add equity point to time series"""
        point = DexEquityPoint(ts=time.time(), equity_usd=equity_usd)
        self.equity_history.append(point)

    def add_log(self, message: str):
        """Add log message and broadcast to clients"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        # Broadcast log to connected clients
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    self.broadcast_ws({"type": "log", "message": log_entry})
                )
        except Exception as e:
            logger.debug(f"Could not broadcast log: {e}")

    def add_decision(self, decision_dict: Dict[str, Any]):
        """Record a trade decision with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        decision_entry = {"timestamp": timestamp, **decision_dict}
        self.decisions.append(decision_entry)
        self.last_decision = decision_entry

    def get_status(self) -> Dict[str, Any]:
        """Get current status snapshot"""
        status = {
            "mode": self.mode.value,
            "paper": self.mode != TradingMode.LIVE,  # True for paper_live_chain and off
            "chain_id": self.chain_id,
            "scan_interval_sec": self.scan_interval_sec,
            "pools_loaded": self.pools_loaded,
            "last_scan_ts": self.last_scan_ts,
            "best_gross_bps": self.best_gross_bps,
            "best_net_bps": self.best_net_bps,
            "config": self.config,
        }
        # Include last decision if available
        if self.last_decision:
            status["last_decision"] = self.last_decision
        return status

    async def broadcast_ws(self, message: Dict[str, Any]):
        """Broadcast message to all DEX WebSocket clients"""
        disconnected = []
        for client in self.ws_clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            if client in self.ws_clients:
                self.ws_clients.remove(client)


dex_state = DexStateManager()


# ============================================================================
# DEX/MEV API Endpoints
# ============================================================================


@app.get("/api/dex/status")
async def get_dex_status():
    """Get current DEX trading status"""
    status = dex_state.get_status()
    status["running"] = dex_state.running
    return {"status": status}


@app.get("/api/dex/opportunities")
async def get_dex_opportunities():
    """Get rolling list of DEX opportunities"""
    return {"opportunities": [opp.model_dump() for opp in dex_state.opportunities]}


@app.get("/api/dex/fills")
async def get_dex_fills():
    """Get recent DEX fills (paper or live)"""
    return {"fills": [fill.model_dump() for fill in dex_state.fills]}


@app.get("/api/dex/equity")
async def get_dex_equity():
    """Get equity time series"""
    return {"points": [point.model_dump() for point in dex_state.equity_history]}


@app.get("/api/dex/logs")
async def get_dex_logs():
    """Get recent DEX scanner logs"""
    return {"logs": list(dex_state.logs)}


@app.get("/api/dex/decisions")
async def get_dex_decisions():
    """Get recent DEX trade decisions for debugging"""
    return {"decisions": list(dex_state.decisions)}


@app.post("/api/dex/control")
async def control_dex(request: DexControlRequest):
    """Control DEX trading (start/stop) with config

    Accepts JSON payload:
    {
        "action": "start",
        "mode": "paper_live_chain",  // or "live"
        "config": {
            "size_usd": 1000,
            "min_profit_threshold_bps": 0,
            "slippage_floor_bps": 5,
            "expected_maker_legs": 2,
            "gas_model": "fast"
        }
    }
    or {"action": "stop"}
    """
    if request.action == "start":
        if dex_state.running:
            return {
                "status": "already_running",
                "running": True,
                "mode": dex_state.mode.value,
            }

        # Handle mode from top-level or config
        if request.mode:
            if request.mode == "paper_live_chain":
                dex_state.mode = TradingMode.PAPER_LIVE_CHAIN
            elif request.mode == "live":
                dex_state.mode = TradingMode.LIVE
            else:
                dex_state.mode = TradingMode.OFF

        # Update config if provided - cast numeric values
        if request.config:
            # Build a typed config object with proper casting
            typed_config = DexConfig()
            if request.config.size_usd is not None:
                typed_config.size_usd = float(request.config.size_usd)
            if request.config.min_profit_threshold_bps is not None:
                typed_config.min_profit_threshold_bps = float(
                    request.config.min_profit_threshold_bps
                )
            if request.config.slippage_floor_bps is not None:
                typed_config.slippage_floor_bps = float(
                    request.config.slippage_floor_bps
                )
            if request.config.expected_maker_legs is not None:
                typed_config.expected_maker_legs = int(
                    request.config.expected_maker_legs
                )
            if request.config.gas_model is not None:
                typed_config.gas_model = str(request.config.gas_model)
            if request.config.slippage_mode is not None:
                typed_config.slippage_mode = str(request.config.slippage_mode)
            if request.config.chain_id is not None:
                typed_config.chain_id = int(request.config.chain_id)
            if request.config.rpc_url is not None:
                typed_config.rpc_url = str(request.config.rpc_url)
            if request.config.gas_oracle is not None:
                typed_config.gas_oracle = str(request.config.gas_oracle)
            if request.config.simulate_via is not None:
                typed_config.simulate_via = str(request.config.simulate_via)
            if request.config.log_tx_objects is not None:
                typed_config.log_tx_objects = bool(request.config.log_tx_objects)
            if request.config.rpc_label is not None:
                typed_config.rpc_label = str(request.config.rpc_label)

            # Handle mode from config
            if request.config.mode is not None:
                typed_config.mode = str(request.config.mode)

            dex_state.update_config(typed_config)

        dex_state.running = True

        # Start background runner
        dex_state.runner_task = asyncio.create_task(run_dex_scanner())

        status_data = dex_state.get_status()
        status_data["running"] = True
        await dex_state.broadcast_ws({"type": "status", "data": status_data})

        return {
            "status": "started",
            "running": True,
            "mode": dex_state.mode.value,
            "config": dex_state.config,
        }

    elif request.action == "stop":
        if not dex_state.running:
            return {
                "status": "not_running",
                "running": False,
                "mode": dex_state.mode.value,
            }

        dex_state.running = False

        # Cancel background task
        if dex_state.runner_task and not dex_state.runner_task.done():
            dex_state.runner_task.cancel()
            try:
                await dex_state.runner_task
            except asyncio.CancelledError:
                pass

        # Set mode back to OFF
        dex_state.mode = TradingMode.OFF

        status_data = dex_state.get_status()
        status_data["running"] = False
        await dex_state.broadcast_ws({"type": "status", "data": status_data})

        return {"status": "stopped", "running": False, "mode": dex_state.mode.value}

    return {"status": "error", "message": f"Unknown action: {request.action}"}


@app.websocket("/ws/dex")
async def dex_websocket(websocket: WebSocket):
    """WebSocket endpoint for DEX real-time updates"""
    await websocket.accept()
    dex_state.ws_clients.append(websocket)
    logger.info(f"DEX client connected. Total: {len(dex_state.ws_clients)}")

    try:
        # Send initial state
        await websocket.send_json({"type": "status", "data": dex_state.get_status()})

        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            logger.info(f"DEX WS received: {data}")

    except WebSocketDisconnect:
        if websocket in dex_state.ws_clients:
            dex_state.ws_clients.remove(websocket)
        logger.info(f"DEX client disconnected. Total: {len(dex_state.ws_clients)}")


# ============================================================================
# DEX Scanner (Mock Runner with Live Chain Data Simulation)
# ============================================================================


class MockRPCClient:
    """Mock RPC client that simulates live chain data responses"""

    async def get_pool_reserves(self, pool_address: str) -> Dict[str, Any]:
        """Simulate pool reserve reads"""
        # In real implementation, this would call eth_call to read reserves
        return {
            "reserve0": 50000 * 10**6,  # USDC reserves
            "reserve1": 20 * 10**18,  # WETH reserves
            "timestamp": int(time.time()),
        }

    async def estimate_gas(self, tx_request: Dict[str, Any]) -> int:
        """Simulate gas estimation"""
        # In real implementation, this would call eth_estimateGas
        # Returns realistic gas estimate
        return 180000 + (hash(str(tx_request)) % 50000)

    async def call_transaction(self, tx_request: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate transaction execution via eth_call"""
        # In real implementation, this would call eth_call
        return {"success": True, "gas_used": 175000, "return_data": "0x" + "00" * 32}

    async def get_gas_price(self) -> int:
        """Get current gas price from chain"""
        # In real implementation, this would call eth_gasPrice or gas oracle API
        return 25 * 10**9  # 25 gwei


class DexExecutor:
    """Handles DEX trade execution with mode-aware broadcast control"""

    def __init__(self, rpc_client: MockRPCClient, mode: TradingMode):
        self.rpc = rpc_client
        self.mode = mode

    async def build_transaction_request(
        self, opportunity: DexOpportunity
    ) -> Dict[str, Any]:
        """Build transaction request object - shared by paper_live_chain and live"""
        # In production, this would build actual calldata for router contract
        tx_request = {
            "from": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
            "to": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2 Router
            "value": "0x0",
            "data": f"0x38ed1739{'0' * 200}",  # Mock swapExactTokensForTokens calldata
            "gas": 200000,
            "gasPrice": await self.rpc.get_gas_price(),
            "nonce": 42,  # Would be fetched from eth_getTransactionCount
            "chainId": 1,
        }

        # Log if configured
        if dex_state.config.get("log_tx_objects"):
            logger.info(f"Built tx request: {tx_request}")

        return tx_request

    async def estimate_and_simulate(self, tx_request: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate gas and simulate execution - shared by paper_live_chain and live"""
        gas_estimate = await self.rpc.estimate_gas(tx_request)

        # Simulate execution based on config
        simulate_via = dex_state.config.get("simulate_via", "eth_call")
        if simulate_via == "eth_call":
            result = await self.rpc.call_transaction(tx_request)
        elif simulate_via == "mev_sim":
            # In production, would call MEV simulator endpoint
            result = {"success": True, "gas_used": gas_estimate - 5000}
        else:
            result = {"success": True, "gas_used": gas_estimate}

        return {"gas_estimate": gas_estimate, "simulation": result}

    async def execute(self, opportunity: DexOpportunity) -> DexFill:
        """Execute opportunity according to mode"""
        # Build transaction (same for all modes)
        tx_request = await self.build_transaction_request(opportunity)

        # Estimate and simulate (same for all modes)
        estimates = await self.estimate_and_simulate(tx_request)

        # Calculate realized costs from estimates
        gas_used = estimates["simulation"]["gas_used"]
        gas_price_gwei = tx_request["gasPrice"] / 10**9
        gas_cost_usd = (
            (gas_used * gas_price_gwei * 10**9) / 10**18 * 2000
        )  # ETH price ~$2000
        gas_cost_bps = (gas_cost_usd / opportunity.size_usd) * 10000

        # Adjust net profit with realized gas
        realized_net_bps = opportunity.gross_bps - gas_cost_bps - opportunity.slip_bps

        # Mode-specific execution
        if self.mode == TradingMode.LIVE:
            # LIVE: Actually broadcast transaction
            # CRITICAL GUARD: Only allow broadcast in live mode
            tx_hash = await self._broadcast_transaction(tx_request)
            logger.info(f"LIVE: Broadcasted transaction {tx_hash}")
        else:
            # PAPER_LIVE_CHAIN: Simulate but don't broadcast
            tx_hash = None
            logger.info("PAPER: Simulated execution (no broadcast)")

        # Create fill record
        pnl_usd = realized_net_bps * opportunity.size_usd / 10000
        fill = DexFill(
            id=f"fill_{int(time.time() * 1000)}",
            paper=self.mode != TradingMode.LIVE,
            tx_hash=tx_hash,
            net_bps=realized_net_bps,
            pnl_usd=pnl_usd,
            ts=time.time(),
            simulation={
                "gas_used": gas_used,
                "success": estimates["simulation"]["success"],
                "gas_estimate": estimates["gas_estimate"],
            },
        )

        return fill

    async def _broadcast_transaction(self, tx_request: Dict[str, Any]) -> str:
        """Broadcast signed transaction to chain - ONLY in live mode"""
        # In production, this would:
        # 1. Sign the transaction with private key
        # 2. Call eth_sendRawTransaction
        # 3. Return transaction hash
        #
        # This method should NEVER be called in paper_live_chain mode
        if self.mode != TradingMode.LIVE:
            raise RuntimeError("CRITICAL: Attempted broadcast in non-live mode!")

        # Mock: generate fake tx hash
        return f"0x{'a' * 64}"


async def run_dex_scanner():
    """
    Background DEX scanner with paper_live_chain support.
    Uses live chain data for pricing, gas, and simulation.
    Only broadcasts transactions in live mode.
    """
    try:
        scan_count = 0
        current_equity = 1000.0

        # Initialize RPC client and executor
        rpc_client = MockRPCClient()
        executor = DexExecutor(rpc_client, dex_state.mode)

        # Initialize decision engine with config (convert bps to percent)
        dex_state.decision_engine = DecisionEngine(
            {
                "min_profit_threshold_pct": dex_state.config["min_profit_threshold_bps"]
                / 100.0,
                "max_position_usd": dex_state.config["size_usd"],
                "expected_maker_legs": dex_state.config.get("expected_maker_legs"),
            }
        )

        mode_text = (
            "PAPER (Live Chain)"
            if dex_state.mode == TradingMode.PAPER_LIVE_CHAIN
            else "LIVE"
        )
        logger.info(f"DEX scanner starting in {dex_state.mode.value} mode")
        dex_state.add_log(f"Scanner started in {mode_text} mode")
        dex_state.add_log(
            f"Scan interval: {dex_state.scan_interval_sec}s, Size: ${dex_state.config['size_usd']}"
        )

        while dex_state.running:
            scan_count += 1
            dex_state.last_scan_ts = time.time()

            # Log scan start
            if scan_count % 5 == 1:  # Log every 5th scan to avoid spam
                dex_state.add_log(
                    f"Scan #{scan_count}: Checking {dex_state.pools_loaded} pools"
                )

            # Simulate pool discovery (in production, would query chain)
            dex_state.pools_loaded = 125

            # Mock: Generate sample opportunity every 3rd scan
            if scan_count % 3 == 0:
                # In production, this would come from real pool data analysis
                opp = DexOpportunity(
                    id=f"dexop_{scan_count}",
                    path=["USDC", "WETH", "DAI"],
                    gross_bps=25.0,
                    net_bps=5.5,
                    gas_bps=18.0,
                    slip_bps=1.5,
                    size_usd=dex_state.config["size_usd"],
                    legs=[
                        {
                            "pair": "USDC/WETH",
                            "side": "buy",
                            "price": 2500.0,
                            "liq_usd": 50000.0,
                            "slip_bps_est": 0.5,
                        },
                        {
                            "pair": "WETH/DAI",
                            "side": "sell",
                            "price": 2505.0,
                            "liq_usd": 45000.0,
                            "slip_bps_est": 1.0,
                        },
                    ],
                    ts=time.time(),
                )
                dex_state.add_opportunity(opp)

                # Log opportunity found
                path_str = " → ".join(opp.path)
                dex_state.add_log(
                    f"Opportunity found: {path_str} | Net: +{opp.net_bps:.2f} bps"
                )

                # Broadcast opportunity
                await dex_state.broadcast_ws(
                    {"type": "opportunity", "data": opp.model_dump()}
                )

                # Evaluate opportunity with DecisionEngine (convert bps to percent)
                decision = dex_state.decision_engine.evaluate_opportunity(
                    gross_pct=opp.gross_bps / 100.0,
                    fees_pct=0.0,  # DEX fees typically in slippage
                    slip_pct=opp.slip_bps / 100.0,
                    gas_pct=opp.gas_bps / 100.0,
                    size_usd=opp.size_usd,
                    has_quote=True,  # Mock always has quotes
                    has_gas_estimate=True,  # Mock always has gas estimates
                )

                # Log the decision
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                decision_log = dex_state.decision_engine.format_decision_log(
                    decision, timestamp
                )
                logger.info(decision_log)
                dex_state.add_log(decision_log)

                # Record decision
                dex_state.add_decision(decision.to_dict())

                # Execute only if decision is EXECUTE
                if decision.action == "EXECUTE":
                    dex_state.add_log(f"Executing opportunity: {path_str}")
                    fill = await executor.execute(opp)

                    # Update equity
                    current_equity += fill.pnl_usd
                    dex_state.add_fill(fill)
                    dex_state.add_equity_point(current_equity)

                    # Log fill result
                    mode_label = "Paper" if fill.paper else "Live"
                    pnl_sign = "+" if fill.pnl_usd >= 0 else ""
                    dex_state.add_log(
                        f"{mode_label} fill: {pnl_sign}${fill.pnl_usd:.2f} "
                        f"({pnl_sign}{fill.net_bps:.2f} bps) | Equity: ${current_equity:.2f}"
                    )

                    # Broadcast fill
                    await dex_state.broadcast_ws(
                        {"type": "fill", "data": fill.model_dump()}
                    )
                else:
                    # Log skip with reasons
                    reasons_str = ", ".join(decision.reasons)
                    dex_state.add_log(
                        f"Skipping opportunity: {path_str} | Reasons: {reasons_str}"
                    )

            # Broadcast status update
            await dex_state.broadcast_ws(
                {"type": "status", "data": dex_state.get_status()}
            )

            # Wait for scan interval
            await asyncio.sleep(dex_state.scan_interval_sec)

    except asyncio.CancelledError:
        logger.info("DEX scanner stopped")
        dex_state.add_log("Scanner stopped")
        raise
    except Exception as e:
        logger.error(f"DEX scanner error: {e}", exc_info=True)
        dex_state.add_log(f"Scanner error: {str(e)}")
        dex_state.running = False


# ============================================================================
# CEX Configuration Endpoints (existing)
# ============================================================================


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
