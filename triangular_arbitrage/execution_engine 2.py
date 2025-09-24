# triangular_arbitrage/execution_engine.py

import asyncio
import json
import sqlite3
import time
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class CycleState(Enum):
    """Enum for tracking the state of a trade cycle"""
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


class StateManager:
    """Manages persistent state storage for trade cycles"""

    def __init__(self, db_path: str = "trade_state.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cycles (
                id TEXT PRIMARY KEY,
                strategy_name TEXT,
                cycle_json TEXT,
                initial_amount REAL,
                current_amount REAL,
                current_currency TEXT,
                state TEXT,
                current_step INTEGER,
                orders_json TEXT,
                start_time REAL,
                end_time REAL,
                profit_loss REAL,
                error_message TEXT,
                metadata_json TEXT,
                updated_at REAL
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_state ON cycles(state)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_strategy ON cycles(strategy_name)
        ''')

        conn.commit()
        conn.close()

    def save_cycle(self, cycle_info: CycleInfo):
        """Save or update a cycle in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO cycles VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        ''', (
            cycle_info.id,
            cycle_info.strategy_name,
            json.dumps(cycle_info.cycle),
            cycle_info.initial_amount,
            cycle_info.current_amount,
            cycle_info.current_currency,
            cycle_info.state.value,
            cycle_info.current_step,
            json.dumps([asdict(o) for o in cycle_info.orders]),
            cycle_info.start_time,
            cycle_info.end_time,
            cycle_info.profit_loss,
            cycle_info.error_message,
            json.dumps(cycle_info.metadata),
            time.time()
        ))

        conn.commit()
        conn.close()

    def get_active_cycles(self, strategy_name: Optional[str] = None) -> List[CycleInfo]:
        """Retrieve all active cycles from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = '''
            SELECT * FROM cycles
            WHERE state IN (?, ?, ?, ?)
        '''
        params = [
            CycleState.ACTIVE.value,
            CycleState.PARTIALLY_FILLED.value,
            CycleState.RECOVERING.value,
            CycleState.PANIC_SELLING.value
        ]

        if strategy_name:
            query += ' AND strategy_name = ?'
            params.append(strategy_name)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        cycles = []
        for row in rows:
            orders = [
                OrderInfo(**o) for o in json.loads(row[8])
            ]
            for order in orders:
                order.state = OrderState(order.state)

            cycle = CycleInfo(
                id=row[0],
                strategy_name=row[1],
                cycle=json.loads(row[2]),
                initial_amount=row[3],
                current_amount=row[4],
                current_currency=row[5],
                state=CycleState(row[6]),
                current_step=row[7],
                orders=orders,
                start_time=row[9],
                end_time=row[10],
                profit_loss=row[11],
                error_message=row[12],
                metadata=json.loads(row[13])
            )
            cycles.append(cycle)

        return cycles

    def cleanup_old_cycles(self, days: int = 7):
        """Remove completed/failed cycles older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_time = time.time() - (days * 24 * 3600)

        cursor.execute('''
            DELETE FROM cycles
            WHERE state IN (?, ?)
            AND updated_at < ?
        ''', (
            CycleState.COMPLETED.value,
            CycleState.FAILED.value,
            cutoff_time
        ))

        conn.commit()
        conn.close()


class ConfigurationManager:
    """Manages strategy configuration loading and validation"""

    def __init__(self):
        self.strategies = {}

    def load_strategy(self, strategy_path: str) -> Dict[str, Any]:
        """Load and validate a strategy configuration"""
        path = Path(strategy_path)

        if not path.exists():
            raise FileNotFoundError(f"Strategy file not found: {strategy_path}")

        with open(path, 'r') as f:
            config = yaml.safe_load(f)

        # Validate required fields
        required_fields = [
            'name', 'exchange', 'min_profit_bps',
            'max_slippage_bps', 'capital_allocation'
        ]

        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")

        # Set defaults for optional fields
        config.setdefault('risk_controls', {
            'max_open_cycles': 3,
            'stop_after_consecutive_losses': 5
        })

        config.setdefault('order', {
            'type': 'market',
            'allow_partial_fills': True,
            'max_retries': 3,
            'retry_delay_ms': 1000
        })

        config.setdefault('panic_sell', {
            'enabled': True,
            'base_currencies': ['USDC', 'USD', 'USDT'],
            'max_slippage_bps': 100
        })

        self.strategies[config['name']] = config
        return config

    def get_strategy(self, name: str) -> Dict[str, Any]:
        """Get a loaded strategy configuration"""
        if name not in self.strategies:
            raise ValueError(f"Strategy not loaded: {name}")
        return self.strategies[name]


class OrderManager:
    """Manages order placement, monitoring, and confirmation"""

    def __init__(self, exchange, config: Dict[str, Any]):
        self.exchange = exchange
        self.config = config
        self.order_config = config.get('order', {})
        self.max_retries = self.order_config.get('max_retries', 3)
        self.retry_delay = self.order_config.get('retry_delay_ms', 1000) / 1000.0

    async def place_order(
        self,
        market_symbol: str,
        side: str,
        amount: float,
        order_type: str = None
    ) -> OrderInfo:
        """Place an order with retry logic"""
        order_type = order_type or self.order_config.get('type', 'market')

        order_info = OrderInfo(
            id="",
            market_symbol=market_symbol,
            side=side,
            amount=amount,
            price=None,
            state=OrderState.PENDING,
            timestamp=time.time()
        )

        for attempt in range(self.max_retries):
            try:
                if order_type == 'market':
                    if side == 'buy':
                        order = await self.exchange.create_market_buy_order(
                            market_symbol, amount
                        )
                    else:
                        order = await self.exchange.create_market_sell_order(
                            market_symbol, amount
                        )
                else:
                    # For limit orders, we'd need to fetch the current price
                    ticker = await self.exchange.fetch_ticker(market_symbol)
                    price = ticker['bid'] if side == 'sell' else ticker['ask']

                    if side == 'buy':
                        order = await self.exchange.create_limit_buy_order(
                            market_symbol, amount, price
                        )
                    else:
                        order = await self.exchange.create_limit_sell_order(
                            market_symbol, amount, price
                        )

                order_info.id = order['id']
                order_info.state = OrderState.PLACED
                order_info.price = order.get('price')

                logger.info(f"Order placed successfully: {order_info.id}")
                return order_info

            except Exception as e:
                order_info.retry_count = attempt + 1
                order_info.error_message = str(e)

                logger.warning(
                    f"Order placement attempt {attempt + 1} failed: {e}"
                )

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    order_info.state = OrderState.FAILED
                    raise

        return order_info

    async def monitor_order(
        self,
        order_info: OrderInfo,
        timeout: float = 30.0
    ) -> OrderInfo:
        """Monitor an order until it's filled or times out"""
        start_time = time.time()
        check_interval = 0.5

        while time.time() - start_time < timeout:
            try:
                order = await self.exchange.fetch_order(
                    order_info.id,
                    order_info.market_symbol
                )

                order_info.filled_amount = order.get('filled', 0)
                order_info.remaining_amount = order.get('remaining', 0)
                order_info.average_price = order.get('average', order.get('price', 0))

                status = order.get('status', '').lower()

                if status == 'closed' or status == 'filled':
                    order_info.state = OrderState.FILLED
                    logger.info(f"Order {order_info.id} filled completely")
                    return order_info

                elif status == 'canceled' or status == 'cancelled':
                    order_info.state = OrderState.CANCELLED
                    logger.warning(f"Order {order_info.id} was cancelled")
                    return order_info

                elif order_info.filled_amount > 0:
                    order_info.state = OrderState.PARTIALLY_FILLED

                    # If partial fills are allowed, we might proceed
                    if self.order_config.get('allow_partial_fills', False):
                        logger.info(
                            f"Order {order_info.id} partially filled: "
                            f"{order_info.filled_amount}/{order_info.amount}"
                        )

            except Exception as e:
                logger.error(f"Error monitoring order {order_info.id}: {e}")

            await asyncio.sleep(check_interval)
            check_interval = min(check_interval * 1.5, 2.0)

        # Timeout reached
        if order_info.filled_amount > 0:
            order_info.state = OrderState.PARTIALLY_FILLED
        else:
            order_info.state = OrderState.FAILED
            order_info.error_message = "Order timeout"

        return order_info

    async def cancel_order(self, order_info: OrderInfo) -> bool:
        """Cancel an open order"""
        try:
            await self.exchange.cancel_order(
                order_info.id,
                order_info.market_symbol
            )
            order_info.state = OrderState.CANCELLED
            logger.info(f"Order {order_info.id} cancelled successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_info.id}: {e}")
            return False


class FailureRecoveryManager:
    """Manages failure recovery and panic sell mechanisms"""

    def __init__(self, exchange, config: Dict[str, Any]):
        self.exchange = exchange
        self.config = config
        self.panic_config = config.get('panic_sell', {})
        self.base_currencies = self.panic_config.get(
            'base_currencies',
            ['USDC', 'USD', 'USDT']
        )
        self.max_slippage_bps = self.panic_config.get('max_slippage_bps', 100)

    async def execute_panic_sell(
        self,
        current_currency: str,
        amount: float
    ) -> Tuple[bool, float, str]:
        """
        Execute a panic sell to convert current holdings to a stable base currency

        Returns:
            Tuple of (success, final_amount, final_currency)
        """
        if current_currency in self.base_currencies:
            logger.info(f"Already holding base currency {current_currency}")
            return True, amount, current_currency

        markets = await self.exchange.load_markets()

        # Find the best path to a base currency
        for base in self.base_currencies:
            # Try direct market
            direct_symbol = f"{base}/{current_currency}"
            reverse_symbol = f"{current_currency}/{base}"

            if direct_symbol in markets:
                return await self._execute_panic_trade(
                    direct_symbol, 'buy', amount, base
                )
            elif reverse_symbol in markets:
                return await self._execute_panic_trade(
                    reverse_symbol, 'sell', amount, base
                )

        # If no direct path, try through intermediary (usually BTC or ETH)
        intermediaries = ['BTC', 'ETH']
        for inter in intermediaries:
            if inter == current_currency:
                continue

            # Check path: current -> intermediary -> base
            to_inter = f"{inter}/{current_currency}"
            from_inter = f"{current_currency}/{inter}"

            inter_market = None
            inter_side = None

            if to_inter in markets:
                inter_market = to_inter
                inter_side = 'buy'
            elif from_inter in markets:
                inter_market = from_inter
                inter_side = 'sell'

            if inter_market:
                for base in self.base_currencies:
                    to_base = f"{base}/{inter}"
                    from_base = f"{inter}/{base}"

                    if to_base in markets or from_base in markets:
                        # Execute two-hop panic sell
                        success, inter_amount, _ = await self._execute_panic_trade(
                            inter_market, inter_side, amount, inter
                        )

                        if success:
                            base_market = to_base if to_base in markets else from_base
                            base_side = 'buy' if to_base in markets else 'sell'

                            return await self._execute_panic_trade(
                                base_market, base_side, inter_amount, base
                            )

        logger.error(f"Could not find panic sell path from {current_currency}")
        return False, amount, current_currency

    async def _execute_panic_trade(
        self,
        market_symbol: str,
        side: str,
        amount: float,
        target_currency: str
    ) -> Tuple[bool, float, str]:
        """Execute a single panic trade"""
        try:
            logger.info(
                f"Executing panic {side} on {market_symbol} for {amount}"
            )

            # Use market order for immediate execution
            if side == 'buy':
                order = await self.exchange.create_market_buy_order(
                    market_symbol, amount
                )
            else:
                order = await self.exchange.create_market_sell_order(
                    market_symbol, amount
                )

            # Wait for confirmation
            await asyncio.sleep(1)

            order_details = await self.exchange.fetch_order(
                order['id'], market_symbol
            )

            filled_amount = order_details.get('filled', 0)

            if side == 'buy':
                final_amount = filled_amount
            else:
                final_amount = order_details.get('cost', 0)

            logger.info(
                f"Panic sell completed: {final_amount} {target_currency}"
            )

            return True, final_amount, target_currency

        except Exception as e:
            logger.error(f"Panic sell failed: {e}")
            return False, amount, target_currency


class StrategyExecutionEngine:
    """Main execution engine that orchestrates all components"""

    def __init__(self, exchange, strategy_config: Dict[str, Any]):
        self.exchange = exchange
        self.config = strategy_config
        self.state_manager = StateManager()
        self.order_manager = OrderManager(exchange, strategy_config)
        self.recovery_manager = FailureRecoveryManager(exchange, strategy_config)

        # Risk controls
        self.risk_controls = strategy_config.get('risk_controls', {})
        self.max_open_cycles = self.risk_controls.get('max_open_cycles', 3)
        self.consecutive_losses = 0
        self.max_consecutive_losses = self.risk_controls.get(
            'stop_after_consecutive_losses', 5
        )

        # Profit/slippage thresholds
        self.min_profit_bps = strategy_config.get('min_profit_bps', 10)
        self.max_slippage_bps = strategy_config.get('max_slippage_bps', 20)

        # Capital allocation
        self.capital_config = strategy_config.get('capital_allocation', {})

    async def execute_cycle(
        self,
        cycle: List[str],
        initial_amount: float,
        cycle_id: Optional[str] = None,
        is_recovery: bool = False
    ) -> CycleInfo:
        """
        Execute a complete arbitrage cycle with full state management
        """
        # Create or recover cycle info
        if cycle_id and is_recovery:
            # Recover existing cycle
            cycles = self.state_manager.get_active_cycles(self.config['name'])
            cycle_info = next((c for c in cycles if c.id == cycle_id), None)

            if not cycle_info:
                raise ValueError(f"Cannot recover cycle {cycle_id}")
        else:
            # Create new cycle
            cycle_id = cycle_id or f"{self.config['name']}_{int(time.time()*1000)}"

            cycle_info = CycleInfo(
                id=cycle_id,
                strategy_name=self.config['name'],
                cycle=cycle,
                initial_amount=initial_amount,
                current_amount=initial_amount,
                current_currency=cycle[0],
                state=CycleState.PENDING,
                current_step=0,
                orders=[],
                start_time=time.time(),
                end_time=None,
                profit_loss=None,
                error_message=None,
                metadata={}
            )

        try:
            # Check risk controls
            if not await self._check_risk_controls():
                cycle_info.state = CycleState.FAILED
                cycle_info.error_message = "Risk controls violated"
                self.state_manager.save_cycle(cycle_info)
                return cycle_info

            # Validate the cycle
            cycle_info.state = CycleState.VALIDATING
            self.state_manager.save_cycle(cycle_info)

            if not await self._validate_cycle(cycle_info):
                cycle_info.state = CycleState.FAILED
                cycle_info.error_message = "Cycle validation failed"
                self.state_manager.save_cycle(cycle_info)
                return cycle_info

            # Execute the cycle
            cycle_info.state = CycleState.ACTIVE
            self.state_manager.save_cycle(cycle_info)

            success = await self._execute_cycle_trades(cycle_info)

            if success:
                cycle_info.state = CycleState.COMPLETED
                cycle_info.profit_loss = (
                    cycle_info.current_amount - cycle_info.initial_amount
                )

                if cycle_info.profit_loss > 0:
                    self.consecutive_losses = 0
                else:
                    self.consecutive_losses += 1
            else:
                cycle_info.state = CycleState.FAILED

                # Attempt panic sell if enabled
                if self.recovery_manager.panic_config.get('enabled', True):
                    await self._handle_panic_sell(cycle_info)

                self.consecutive_losses += 1

        except Exception as e:
            logger.error(f"Cycle execution error: {e}")
            cycle_info.state = CycleState.FAILED
            cycle_info.error_message = str(e)

            # Attempt panic sell on any error
            if self.recovery_manager.panic_config.get('enabled', True):
                await self._handle_panic_sell(cycle_info)

        finally:
            cycle_info.end_time = time.time()
            self.state_manager.save_cycle(cycle_info)

        return cycle_info

    async def _check_risk_controls(self) -> bool:
        """Check if risk controls allow new cycle execution"""
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning(
                f"Max consecutive losses reached: {self.consecutive_losses}"
            )
            return False

        # Check open cycles
        active_cycles = self.state_manager.get_active_cycles(self.config['name'])
        if len(active_cycles) >= self.max_open_cycles:
            logger.warning(
                f"Max open cycles reached: {len(active_cycles)}"
            )
            return False

        return True

    async def _validate_cycle(self, cycle_info: CycleInfo) -> bool:
        """Validate that a cycle can be executed"""
        from_currency = cycle_info.cycle[0]
        amount = cycle_info.initial_amount
        trade_path = cycle_info.cycle + [cycle_info.cycle[0]]
        markets = await self.exchange.load_markets()

        for i in range(len(trade_path) - 1):
            to_currency = trade_path[i+1]

            market_symbol_forward = f"{to_currency}/{from_currency}"
            market_symbol_backward = f"{from_currency}/{to_currency}"

            market = None
            order_side = None

            if market_symbol_forward in markets:
                market = markets[market_symbol_forward]
                order_side = 'buy'
            elif market_symbol_backward in markets:
                market = markets[market_symbol_backward]
                order_side = 'sell'
            else:
                logger.error(
                    f"No market found for {from_currency} -> {to_currency}"
                )
                return False

            # Check minimum order requirements
            min_order_amount = market.get('limits', {}).get('amount', {}).get('min')
            min_order_cost = market.get('limits', {}).get('cost', {}).get('min')

            if order_side == 'sell' and min_order_amount and amount < min_order_amount:
                logger.error(
                    f"Order amount too small: {amount} < {min_order_amount}"
                )
                return False

            if order_side == 'buy' and min_order_cost and amount < min_order_cost:
                logger.error(
                    f"Order value too small: {amount} < {min_order_cost}"
                )
                return False

            # Estimate amount for next step
            try:
                ticker = await self.exchange.fetch_ticker(market['symbol'])
                price = ticker['last']

                # Apply expected slippage
                slippage = 1 - (self.max_slippage_bps / 10000)

                if order_side == 'buy':
                    amount = (amount / price) * slippage
                else:
                    amount = (amount * price) * slippage
            except Exception as e:
                logger.warning(f"Could not fetch ticker for validation: {e}")

            from_currency = to_currency

        return True

    async def _execute_cycle_trades(self, cycle_info: CycleInfo) -> bool:
        """Execute all trades in a cycle"""
        trade_path = cycle_info.cycle + [cycle_info.cycle[0]]
        markets = await self.exchange.load_markets()

        # Start from current step (for recovery)
        for i in range(cycle_info.current_step, len(trade_path) - 1):
            from_currency = cycle_info.current_currency
            to_currency = trade_path[i+1]
            amount = cycle_info.current_amount

            logger.info(
                f"Step {i+1}: Trading {from_currency} -> {to_currency}, "
                f"Amount: {amount}"
            )

            # Determine market and side
            market_symbol_forward = f"{to_currency}/{from_currency}"
            market_symbol_backward = f"{from_currency}/{to_currency}"

            if market_symbol_forward in markets:
                market_symbol = market_symbol_forward
                order_side = 'buy'
            elif market_symbol_backward in markets:
                market_symbol = market_symbol_backward
                order_side = 'sell'
            else:
                cycle_info.error_message = (
                    f"No market for {from_currency} -> {to_currency}"
                )
                return False

            # Place and monitor order
            try:
                order_info = await self.order_manager.place_order(
                    market_symbol,
                    order_side,
                    amount
                )

                cycle_info.orders.append(order_info)
                self.state_manager.save_cycle(cycle_info)

                # Monitor order completion
                order_info = await self.order_manager.monitor_order(
                    order_info,
                    timeout=30.0
                )

                if order_info.state != OrderState.FILLED:
                    if order_info.state == OrderState.PARTIALLY_FILLED:
                        # Handle partial fill if allowed
                        if self.config['order'].get('allow_partial_fills', False):
                            if order_side == 'buy':
                                cycle_info.current_amount = order_info.filled_amount
                            else:
                                # For sell, the cost is what we received
                                cycle_info.current_amount = (
                                    order_info.filled_amount * order_info.average_price
                                )

                            logger.warning(
                                f"Proceeding with partial fill: {cycle_info.current_amount}"
                            )
                        else:
                            cycle_info.error_message = "Order not fully filled"
                            return False
                    else:
                        cycle_info.error_message = f"Order failed: {order_info.error_message}"
                        return False
                else:
                    # Update amount based on actual fill
                    if order_side == 'buy':
                        cycle_info.current_amount = order_info.filled_amount
                    else:
                        cycle_info.current_amount = (
                            order_info.filled_amount * order_info.average_price
                        )

                # Update cycle state
                cycle_info.current_currency = to_currency
                cycle_info.current_step = i + 1
                self.state_manager.save_cycle(cycle_info)

            except Exception as e:
                logger.error(f"Trade execution failed: {e}")
                cycle_info.error_message = str(e)
                return False

        return True

    async def _handle_panic_sell(self, cycle_info: CycleInfo):
        """Handle panic sell for failed cycle"""
        logger.info(
            f"Initiating panic sell for cycle {cycle_info.id}"
        )

        cycle_info.state = CycleState.PANIC_SELLING
        self.state_manager.save_cycle(cycle_info)

        success, final_amount, final_currency = await self.recovery_manager.execute_panic_sell(
            cycle_info.current_currency,
            cycle_info.current_amount
        )

        if success:
            cycle_info.current_amount = final_amount
            cycle_info.current_currency = final_currency
            cycle_info.metadata['panic_sell_executed'] = True
            cycle_info.metadata['panic_sell_currency'] = final_currency
            cycle_info.metadata['panic_sell_amount'] = final_amount

            logger.info(
                f"Panic sell successful: {final_amount} {final_currency}"
            )
        else:
            logger.error("Panic sell failed")
            cycle_info.metadata['panic_sell_failed'] = True

    async def recover_active_cycles(self):
        """Recover and attempt to complete any active cycles after restart"""
        active_cycles = self.state_manager.get_active_cycles(self.config['name'])

        logger.info(f"Found {len(active_cycles)} active cycles to recover")

        for cycle_info in active_cycles:
            logger.info(f"Recovering cycle {cycle_info.id}")

            try:
                # Attempt to complete the cycle
                await self.execute_cycle(
                    cycle_info.cycle,
                    cycle_info.initial_amount,
                    cycle_info.id,
                    is_recovery=True
                )
            except Exception as e:
                logger.error(f"Failed to recover cycle {cycle_info.id}: {e}")

                # Mark as failed and attempt panic sell
                cycle_info.state = CycleState.FAILED
                cycle_info.error_message = f"Recovery failed: {e}"

                if self.recovery_manager.panic_config.get('enabled', True):
                    await self._handle_panic_sell(cycle_info)

                self.state_manager.save_cycle(cycle_info)


# Backward compatibility wrapper
async def execute_cycle(exchange, cycle, initial_amount, is_dry_run=False):
    """
    Backward compatible wrapper for the old execute_cycle function.
    This loads a default configuration and uses the new engine.
    """
    if is_dry_run:
        # For dry runs, use the old simple logic
        from . import trade_executor as old_executor
        return await old_executor.execute_cycle(exchange, cycle, initial_amount, is_dry_run)

    # Create a minimal configuration
    config = {
        'name': 'default',
        'exchange': exchange.id,
        'min_profit_bps': 10,
        'max_slippage_bps': 20,
        'capital_allocation': {
            'mode': 'fixed_amount',
            'amount': initial_amount
        },
        'risk_controls': {
            'max_open_cycles': 1,
            'stop_after_consecutive_losses': 5
        },
        'order': {
            'type': 'market',
            'allow_partial_fills': True,
            'max_retries': 3,
            'retry_delay_ms': 1000
        },
        'panic_sell': {
            'enabled': True,
            'base_currencies': ['USDC', 'USD', 'USDT'],
            'max_slippage_bps': 100
        }
    }

    # Create and use the new engine
    engine = StrategyExecutionEngine(exchange, config)
    cycle_info = await engine.execute_cycle(cycle, initial_amount)

    # Log the result
    if cycle_info.state == CycleState.COMPLETED:
        logger.info(
            f"Cycle completed successfully. P/L: {cycle_info.profit_loss}"
        )
    else:
        logger.error(
            f"Cycle failed: {cycle_info.error_message}"
        )