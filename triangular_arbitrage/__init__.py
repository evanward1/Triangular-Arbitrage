"""
Triangular Arbitrage Trading System.

A comprehensive trading system for detecting and executing triangular arbitrage
opportunities across cryptocurrency exchanges. Supports live trading, paper trading,
and backtesting with comprehensive risk controls and observability.
"""

PROJECT_NAME = "OctoBot-Triangular-Arbitrage"
VERSION = "1.3.0"

# Export main components for easier imports
from triangular_arbitrage.execution_engine import (
    StrategyExecutionEngine,
    StateManager,
    OrderManager,
    FailureRecoveryManager,
    ConfigurationManager,
    CycleState,
    OrderState,
    CycleInfo,
    OrderInfo,
)

# Export enhanced components if available
try:
    from triangular_arbitrage.enhanced_recovery_manager import (
        EnhancedFailureRecoveryManager,
        MarketCondition,
        LiquidationPath,
        ExecutionStep,
    )
except ImportError:
    pass

__all__ = [
    "PROJECT_NAME",
    "VERSION",
    "StrategyExecutionEngine",
    "StateManager",
    "OrderManager",
    "FailureRecoveryManager",
    "EnhancedFailureRecoveryManager",
    "ConfigurationManager",
    "CycleState",
    "OrderState",
    "CycleInfo",
    "OrderInfo",
    "MarketCondition",
    "LiquidationPath",
    "ExecutionStep",
]
