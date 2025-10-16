"""
Type definitions for the execution engine.
Contains enums and dataclasses used throughout execution.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class CycleState(Enum):
    """
    Enumeration for tracking the state of a triangular arbitrage trade cycle.

    States represent the progression of a three-leg arbitrage opportunity from
    detection through completion or failure.

    Values:
        PENDING: Cycle detected but not yet validated or executed
        VALIDATING: Cycle undergoing profitability and risk validation
        ACTIVE: Cycle execution in progress with orders placed
        PARTIALLY_FILLED: Some orders filled, others pending completion
        COMPLETED: All orders filled successfully, cycle complete
        FAILED: Cycle execution failed due to errors or market conditions
        RECOVERING: Cycle in recovery mode
        PANIC_SELLING: Emergency liquidation in progress
    """

    PENDING = "pending"
    VALIDATING = "validating"
    ACTIVE = "active"
    PARTIALLY_FILLED = "partially_filled"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"
    PANIC_SELLING = "panic_selling"


class OrderState(Enum):
    """Enum for tracking individual order states"""

    PENDING = "pending"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class OrderInfo:
    """Data class for order information"""

    id: str
    market_symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: Optional[float]
    state: OrderState
    filled_amount: float = 0.0
    remaining_amount: float = 0.0
    average_price: float = 0.0
    timestamp: float = 0.0
    retry_count: int = 0
    error_message: Optional[str] = None


@dataclass
class CycleInfo:
    """Data class for cycle information"""

    id: str
    strategy_name: str
    cycle: List[str]
    initial_amount: float
    current_amount: float
    current_currency: str
    state: CycleState
    current_step: int
    orders: List[OrderInfo]
    start_time: float
    end_time: Optional[float]
    profit_loss: Optional[float]
    error_message: Optional[str]
    metadata: Dict[str, Any]
