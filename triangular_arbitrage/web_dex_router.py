"""
DEX/MEV API router extracted from web_server.py

This module contains all DEX-specific endpoints and state management,
separated for better code organization and maintainability.
"""

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, validator

# Import DecisionEngine for explicit trade execution decisions
from decision_engine import DecisionEngine

# Import live cost computation
from dex.live_costs import compute_costs_for_route

# Import single source of truth for opportunity math
from dex.opportunity_math import compute_opportunity_breakdown

# Import route deduplication
from dex.route_deduplication import RouteDeduplicator

logger = logging.getLogger(__name__)

# Try to import Web3 - optional dependency
try:
    from web3 import Web3

    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    Web3 = None


# ============================================================================
# Mode Enum - Single Source of Truth
# ============================================================================


class TradingMode(str, Enum):
    """Trading mode for DEX/MEV operations"""

    OFF = "off"
    PAPER_LIVE_CHAIN = "paper_live_chain"  # Paper trading with live chain data
    LIVE = "live"  # Live trading with real broadcasts


# ============================================================================
# Pydantic Models
# ============================================================================


class DexOpportunity(BaseModel):
    id: str
    path: List[str]
    gross_bps: float
    gross_pct: float  # gross_bps / 100
    fee_bps: float  # Exchange fees (e.g., 0.30% per swap)
    fee_pct: float  # fee_bps / 100
    slip_bps: float  # Slippage estimate
    slip_pct: float  # slip_bps / 100
    gas_bps: float  # Gas cost as basis points of trade size
    gas_pct: float  # gas_bps / 100
    net_bps: float  # Net profit after all costs
    net_pct: float  # net_bps / 100
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
    equity_usd: float  # Running balance (for internal tracking)
    cumulative_pnl_usd: float  # Cumulative PnL for chart display


class DexConfig(BaseModel):
    """Validated DEX configuration model."""

    size_usd: Optional[float] = Field(None, ge=1.0, le=1000000.0)
    min_profit_threshold_bps: Optional[float] = Field(None, ge=0.0, le=10000.0)
    slippage_mode: Optional[str] = Field(None, pattern="^(static|dynamic)$")
    slippage_floor_bps: Optional[float] = Field(None, ge=0.0, le=1000.0)
    expected_maker_legs: Optional[int] = Field(None, ge=0, le=3)
    gas_model: Optional[str] = Field(None, pattern="^(slow|standard|fast|rapid)$")
    paper: Optional[bool] = None  # Legacy - maps to mode
    mode: Optional[str] = Field(None, pattern="^(paper_live_chain|live|off)$")
    chain_id: Optional[int] = Field(None, ge=1)
    rpc_url: Optional[str] = Field(None, max_length=500)
    gas_oracle: Optional[str] = None
    simulate_via: Optional[str] = Field(None, pattern="^(eth_call|mev_sim)$")
    log_tx_objects: Optional[bool] = None
    rpc_label: Optional[str] = Field(None, max_length=100)


class DexControlRequest(BaseModel):
    """Validated DEX control request model."""

    action: str = Field(..., pattern="^(start|stop)$", description="Control action")
    mode: Optional[str] = Field(
        None, pattern="^(paper_live_chain|live)$", description="Trading mode"
    )
    config: Optional[DexConfig] = None

    @validator("mode")
    def validate_mode_for_start(cls, v, values):
        """Require mode when action is start."""
        if values.get("action") == "start" and v is None:
            raise ValueError("mode is required when action is 'start'")
        return v


# ============================================================================
# DEX State Manager
# ============================================================================


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

        # Connected WebSocket clients
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

        # Persist chain_id from UI selection
        if config.chain_id is not None:
            self.chain_id = int(config.chain_id)
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

    def add_equity_point(self, equity_usd: float, cumulative_pnl_usd: float):
        """Add equity point to time series"""
        point = DexEquityPoint(
            ts=time.time(), equity_usd=equity_usd, cumulative_pnl_usd=cumulative_pnl_usd
        )
        self.equity_history.append(point)

    def add_log(self, message: str):
        """Add log message and broadcast to clients"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)

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
            "paper": self.mode != TradingMode.LIVE,
            "chain_id": self.chain_id,
            "scan_interval_sec": self.scan_interval_sec,
            "pools_loaded": self.pools_loaded,
            "last_scan_ts": self.last_scan_ts,
            "best_gross_bps": self.best_gross_bps,
            "best_net_bps": self.best_net_bps,
            "config": self.config,
        }
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


# ============================================================================
# Create router and state
# ============================================================================

# Create router instance
router = APIRouter(prefix="/api/dex", tags=["DEX Trading"])

# Global DEX state manager
dex_state = DexStateManager()


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/status")
async def get_dex_status():
    """Get current DEX trading status"""
    status = dex_state.get_status()
    status["running"] = dex_state.running
    return {"status": status}


@router.get("/opportunities")
async def get_dex_opportunities():
    """Get rolling list of DEX opportunities"""
    return {"opportunities": [opp.model_dump() for opp in dex_state.opportunities]}


@router.get("/fills")
async def get_dex_fills():
    """Get recent DEX fills (paper or live)"""
    return {"fills": [fill.model_dump() for fill in dex_state.fills]}


@router.get("/equity")
async def get_dex_equity():
    """Get equity time series"""
    return {"points": [point.model_dump() for point in dex_state.equity_history]}


@router.get("/logs")
async def get_dex_logs():
    """Get recent DEX scanner logs"""
    return {"logs": list(dex_state.logs)}


@router.get("/decisions")
async def get_dex_decisions():
    """Get recent DEX trade decisions for debugging"""
    return {"decisions": list(dex_state.decisions)}


# Note: The /control and websocket endpoints will be added in web_server.py
# with authentication dependencies, as they need the security_manager instance
