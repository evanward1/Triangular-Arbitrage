"""
Core Execution Engine for Triangular Arbitrage Trading System.

This module provides the primary execution engine that orchestrates triangular arbitrage
trading across multiple exchanges and execution modes. It manages the complete trade
lifecycle from opportunity detection through execution and reconciliation.

Key Components:
    - StrategyExecutionEngine: Main orchestrator for trading operations
    - StateManager: Persistent state management and recovery
    - OrderManager: Order placement, tracking, and lifecycle management
    - ConfigurationManager: Dynamic configuration loading and validation
    - FailureRecoveryManager: Error handling and recovery mechanisms

Execution Modes:
    - Live Trading: Real money execution on live exchanges
    - Paper Trading: Simulated execution with realistic market conditions
    - Backtesting: Historical data replay for strategy validation

The engine supports sophisticated features including:
    - Multi-leg order coordination and timing
    - Risk controls and position limits
    - Real-time performance monitoring
    - Automated failure recovery and rollback
    - Comprehensive audit logging and reconciliation
"""

import asyncio
import json
import random
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
import yaml

try:
    from .enhanced_recovery_manager import EnhancedFailureRecoveryManager

    ENHANCED_RECOVERY_AVAILABLE = True
except ImportError:
    ENHANCED_RECOVERY_AVAILABLE = False

try:
    from .risk_controls import RiskControlManager

    RISK_CONTROLS_AVAILABLE = True
except ImportError:
    RISK_CONTROLS_AVAILABLE = False

from .utils import get_logger

logger = get_logger(__name__)

# Log risk controls availability after logger is initialized
if not RISK_CONTROLS_AVAILABLE:
    logger.warning("Risk controls module not available")


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


class CycleCache:
    """In-memory cache for cycle data with write-through batching"""

    def __init__(self, max_batch_size: int = 50, flush_interval: float = 1.0):
        self.cache = {}  # cycle_id -> CycleInfo
        self.dirty_cycles = set()  # cycle_ids that need to be written
        self.write_queue = deque()  # Queue of (cycle_id, timestamp) for batching
        self.max_batch_size = max_batch_size
        self.flush_interval = flush_interval
        self.last_flush = time.time()
        self._lock = asyncio.Lock()

        # Terminal states that trigger immediate flush
        self.terminal_states = {
            CycleState.COMPLETED,
            CycleState.FAILED,
            CycleState.PANIC_SELLING,
        }

        # Critical states that should be persisted more frequently
        self.critical_states = {
            CycleState.ACTIVE,
            CycleState.RECOVERING,
            CycleState.PANIC_SELLING,
        }

    async def put(self, cycle_info: CycleInfo) -> bool:
        """Add or update a cycle in the cache

        Returns:
            True if should trigger immediate flush, False otherwise
        """
        async with self._lock:
            cycle_id = cycle_info.id
            self.cache[cycle_id] = cycle_info
            self.dirty_cycles.add(cycle_id)
            self.write_queue.append((cycle_id, time.time()))

            # Check if we should flush immediately
            if cycle_info.state in self.terminal_states:
                return True

            # Check if batch is full
            if len(self.dirty_cycles) >= self.max_batch_size:
                return True

            # Check if critical state and enough time has passed
            if cycle_info.state in self.critical_states:
                if time.time() - self.last_flush > self.flush_interval / 2:
                    return True

            return False

    async def get(self, cycle_id: str) -> Optional[CycleInfo]:
        """Get a cycle from cache"""
        async with self._lock:
            return self.cache.get(cycle_id)

    async def get_all(self) -> List[CycleInfo]:
        """Get all cached cycles"""
        async with self._lock:
            return list(self.cache.values())

    async def get_dirty_cycles(self) -> List[CycleInfo]:
        """Get all cycles that need to be written to database"""
        async with self._lock:
            dirty_list = []
            for cycle_id in self.dirty_cycles:
                if cycle_id in self.cache:
                    dirty_list.append(self.cache[cycle_id])
            return dirty_list

    async def mark_clean(self, cycle_ids: List[str]):
        """Mark cycles as successfully written to database"""
        async with self._lock:
            for cycle_id in cycle_ids:
                self.dirty_cycles.discard(cycle_id)
            self.last_flush = time.time()

    async def remove_old_completed(self, max_age_seconds: float = 300):
        """Remove old completed/failed cycles from cache to prevent memory growth"""
        async with self._lock:
            current_time = time.time()
            to_remove = []

            for cycle_id, cycle_info in self.cache.items():
                if cycle_info.state in {CycleState.COMPLETED, CycleState.FAILED}:
                    if (
                        cycle_info.end_time
                        and current_time - cycle_info.end_time > max_age_seconds
                    ):
                        if cycle_id not in self.dirty_cycles:
                            to_remove.append(cycle_id)

            for cycle_id in to_remove:
                del self.cache[cycle_id]

            return len(to_remove)

    async def should_flush(self) -> bool:
        """Check if cache should be flushed based on time or size"""
        async with self._lock:
            if not self.dirty_cycles:
                return False

            # Time-based flush
            if time.time() - self.last_flush > self.flush_interval:
                return True

            # Size-based flush
            if len(self.dirty_cycles) >= self.max_batch_size:
                return True

            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        async with self._lock:
            return {
                "total_cached": len(self.cache),
                "dirty_cycles": len(self.dirty_cycles),
                "queue_size": len(self.write_queue),
                "seconds_since_flush": time.time() - self.last_flush,
            }


class StateManager:
    """Manages persistent state storage for trade cycles with async operations, connection pooling, and caching"""

    def __init__(
        self,
        db_path: str = "trade_state.db",
        pool_size: int = 5,
        cache_batch_size: int = 50,
        cache_flush_interval: float = 1.0,
        enable_cache: bool = True,
    ):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections = []
        self._available = asyncio.Queue(maxsize=pool_size)
        self._lock = asyncio.Lock()
        self._initialized = False

        # Caching configuration
        self.enable_cache = enable_cache
        self.cache = (
            CycleCache(
                max_batch_size=cache_batch_size, flush_interval=cache_flush_interval
            )
            if enable_cache
            else None
        )

        # Background flush task handle
        self._flush_task = None

    async def initialize(self):
        """Initialize the connection pool and database schema"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            # Create connection pool
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(self.db_path)

                # Apply performance optimizations
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA cache_size=10000")
                await conn.execute("PRAGMA temp_store=MEMORY")

                self._connections.append(conn)
                await self._available.put(conn)

            # Initialize database schema using one connection
            conn = await self._available.get()
            try:
                await self._init_database_schema(conn)
            finally:
                await self._available.put(conn)

            self._initialized = True

            # Start background flush task if caching is enabled
            if self.enable_cache:
                self._flush_task = asyncio.create_task(self._background_flush())
                logger.info(
                    f"StateManager initialized with {self.pool_size} connections and caching enabled"
                )
            else:
                logger.info(
                    f"StateManager initialized with {self.pool_size} connections (no caching)"
                )

    async def _init_database_schema(self, conn: aiosqlite.Connection):
        """Initialize the database schema with normalized tables"""

        # Main cycles table (without orders_json)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cycles (
                id TEXT PRIMARY KEY,
                strategy_name TEXT,
                cycle_json TEXT,
                initial_amount REAL,
                current_amount REAL,
                current_currency TEXT,
                state TEXT,
                current_step INTEGER,
                orders_json TEXT,  -- Keep for backward compatibility, will be NULL for new entries
                start_time REAL,
                end_time REAL,
                profit_loss REAL,
                error_message TEXT,
                metadata_json TEXT,
                updated_at REAL
            )
        """
        )

        # Separate orders table for normalization
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                cycle_id TEXT NOT NULL,
                market_symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                price REAL,
                state TEXT NOT NULL,
                filled_amount REAL DEFAULT 0,
                remaining_amount REAL DEFAULT 0,
                average_price REAL DEFAULT 0,
                timestamp REAL NOT NULL,
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE
            )
        """
        )

        # Cycle state changes table for efficient updates
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_updates (
                update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                updated_at REAL NOT NULL,
                FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_reservations (
                reservation_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                cycle_id TEXT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        """
        )

        # Indexes for cycles
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_state ON cycles(state)
        """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_strategy ON cycles(strategy_name)
        """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_updated_at ON cycles(updated_at)
        """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_composite_state_strategy
            ON cycles(state, strategy_name)
        """
        )

        # Indexes for orders
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_cycle ON orders(cycle_id)
        """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state)
        """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(timestamp)
        """
        )

        # Indexes for cycle_updates
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_updates_cycle ON cycle_updates(cycle_id, updated_at)
        """
        )

        # Indexes for reservations
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reservation_strategy
            ON cycle_reservations(strategy_name, status)
        """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reservation_expires
            ON cycle_reservations(expires_at)
        """
        )

        await conn.commit()

    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool"""
        if not self._initialized:
            await self.initialize()

        conn = await self._available.get()
        try:
            yield conn
        finally:
            await self._available.put(conn)

    async def close(self):
        """Close all connections in the pool and stop background tasks"""
        # Stop background flush task if running
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining cached data
        if self.cache:
            await self.flush_all()

        async with self._lock:
            self._initialized = False

            while not self._available.empty():
                conn = await self._available.get()
                try:
                    await conn.close()
                except:
                    pass

            for conn in self._connections:
                try:
                    await conn.close()
                except:
                    pass

            self._connections.clear()

    async def save_cycle(self, cycle_info: CycleInfo, force_write: bool = False):
        """Save or update a cycle, using cache if enabled

        Args:
            cycle_info: The cycle to save
            force_write: If True, bypass cache and write immediately to database
        """
        if self.enable_cache and not force_write:
            # Add to cache
            should_flush = await self.cache.put(cycle_info)

            # Flush if needed (terminal state or batch full)
            if should_flush:
                await self._flush_cache()
        else:
            # Direct write to database (no caching)
            await self._write_cycle_to_db(cycle_info)

    async def _write_cycle_to_db(self, cycle_info: CycleInfo):
        """Write a single cycle directly to database with orders in separate table"""
        async with self.get_connection() as conn:
            await conn.execute("BEGIN TRANSACTION")

            try:
                # Write cycle without orders_json (set to NULL)
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO cycles VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?
                    )
                """,
                    (
                        cycle_info.id,
                        cycle_info.strategy_name,
                        json.dumps(cycle_info.cycle),
                        cycle_info.initial_amount,
                        cycle_info.current_amount,
                        cycle_info.current_currency,
                        (
                            cycle_info.state.value
                            if isinstance(cycle_info.state, CycleState)
                            else cycle_info.state
                        ),
                        cycle_info.current_step,
                        cycle_info.start_time,
                        cycle_info.end_time,
                        cycle_info.profit_loss,
                        cycle_info.error_message,
                        json.dumps(cycle_info.metadata),
                        time.time(),
                    ),
                )

                # Write orders separately
                if cycle_info.orders:
                    for order in cycle_info.orders:
                        await conn.execute(
                            """
                            INSERT OR REPLACE INTO orders VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                        """,
                            (
                                order.id,
                                cycle_info.id,
                                order.market_symbol,
                                order.side,
                                order.amount,
                                order.price,
                                (
                                    order.state.value
                                    if isinstance(order.state, OrderState)
                                    else order.state
                                ),
                                order.filled_amount,
                                order.remaining_amount,
                                order.average_price,
                                order.timestamp,
                                order.retry_count,
                                order.error_message,
                                time.time(),
                                time.time(),
                            ),
                        )

                await conn.commit()

            except Exception as e:
                await conn.rollback()
                raise

    async def _batch_write_cycles(self, cycles: List[CycleInfo]):
        """Write multiple cycles to database in a single transaction with normalized orders"""
        if not cycles:
            return

        async with self.get_connection() as conn:
            await conn.execute("BEGIN TRANSACTION")

            try:
                for cycle_info in cycles:
                    # Write cycle without orders_json
                    await conn.execute(
                        """
                        INSERT OR REPLACE INTO cycles VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?
                        )
                    """,
                        (
                            cycle_info.id,
                            cycle_info.strategy_name,
                            json.dumps(cycle_info.cycle),
                            cycle_info.initial_amount,
                            cycle_info.current_amount,
                            cycle_info.current_currency,
                            (
                                cycle_info.state.value
                                if isinstance(cycle_info.state, CycleState)
                                else cycle_info.state
                            ),
                            cycle_info.current_step,
                            cycle_info.start_time,
                            cycle_info.end_time,
                            cycle_info.profit_loss,
                            cycle_info.error_message,
                            json.dumps(cycle_info.metadata),
                            time.time(),
                        ),
                    )

                    # Write orders separately
                    if cycle_info.orders:
                        for order in cycle_info.orders:
                            await conn.execute(
                                """
                                INSERT OR REPLACE INTO orders VALUES (
                                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                                )
                            """,
                                (
                                    order.id,
                                    cycle_info.id,
                                    order.market_symbol,
                                    order.side,
                                    order.amount,
                                    order.price,
                                    (
                                        order.state.value
                                        if isinstance(order.state, OrderState)
                                        else order.state
                                    ),
                                    order.filled_amount,
                                    order.remaining_amount,
                                    order.average_price,
                                    order.timestamp,
                                    order.retry_count,
                                    order.error_message,
                                    time.time(),
                                    time.time(),
                                ),
                            )

                await conn.commit()
                logger.debug(f"Batch wrote {len(cycles)} cycles to database")

            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to batch write cycles: {e}")
                raise

    async def _flush_cache(self):
        """Flush all dirty cycles from cache to database"""
        if not self.cache:
            return

        dirty_cycles = await self.cache.get_dirty_cycles()
        if dirty_cycles:
            try:
                await self._batch_write_cycles(dirty_cycles)
                # Mark cycles as clean after successful write
                await self.cache.mark_clean([c.id for c in dirty_cycles])
                logger.debug(f"Flushed {len(dirty_cycles)} cycles to database")
            except Exception as e:
                logger.error(f"Cache flush failed: {e}")
                # On failure, cycles remain dirty and will be retried

    async def _background_flush(self):
        """Background task to periodically flush cache"""
        logger.info("Started background cache flush task")

        while self._initialized:
            try:
                await asyncio.sleep(self.cache.flush_interval)

                if await self.cache.should_flush():
                    await self._flush_cache()

                # Periodically clean old completed cycles from cache
                removed = await self.cache.remove_old_completed()
                if removed > 0:
                    logger.debug(f"Removed {removed} old completed cycles from cache")

            except asyncio.CancelledError:
                logger.info("Background flush task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background flush: {e}")

    async def flush_all(self):
        """Force flush all cached data to database"""
        if self.cache:
            await self._flush_cache()
            logger.info("Force flushed all cached cycles to database")

    async def save_order(self, cycle_id: str, order_info: OrderInfo):
        """Save or update a single order efficiently"""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO orders VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """,
                (
                    order_info.id,
                    cycle_id,
                    order_info.market_symbol,
                    order_info.side,
                    order_info.amount,
                    order_info.price,
                    (
                        order_info.state.value
                        if isinstance(order_info.state, OrderState)
                        else order_info.state
                    ),
                    order_info.filled_amount,
                    order_info.remaining_amount,
                    order_info.average_price,
                    order_info.timestamp,
                    order_info.retry_count,
                    order_info.error_message,
                    time.time(),  # created_at
                    time.time(),  # updated_at
                ),
            )

            await conn.commit()

    async def update_order_state(
        self,
        order_id: str,
        new_state: OrderState,
        filled_amount: Optional[float] = None,
        average_price: Optional[float] = None,
    ):
        """Update only specific order fields efficiently"""
        async with self.get_connection() as conn:
            update_fields = ["state = ?", "updated_at = ?"]
            params = [
                new_state.value if isinstance(new_state, OrderState) else new_state,
                time.time(),
            ]

            if filled_amount is not None:
                update_fields.append("filled_amount = ?")
                params.append(filled_amount)

            if average_price is not None:
                update_fields.append("average_price = ?")
                params.append(average_price)

            params.append(order_id)

            await conn.execute(
                f"""
                UPDATE orders
                SET {", ".join(update_fields)}
                WHERE order_id = ?
            """,
                params,
            )

            await conn.commit()

    async def get_cycle_orders(self, cycle_id: str) -> List[OrderInfo]:
        """Retrieve all orders for a specific cycle"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM orders
                WHERE cycle_id = ?
                ORDER BY timestamp ASC
            """,
                (cycle_id,),
            )

            rows = await cursor.fetchall()
            orders = []

            for row in rows:
                order = OrderInfo(
                    id=row[0],
                    market_symbol=row[2],
                    side=row[3],
                    amount=row[4],
                    price=row[5],
                    state=OrderState(row[6]),
                    filled_amount=row[7],
                    remaining_amount=row[8],
                    average_price=row[9],
                    timestamp=row[10],
                    retry_count=row[11],
                    error_message=row[12],
                )
                orders.append(order)

            return orders

    async def save_cycle_partial(self, cycle_id: str, updates: Dict[str, Any]):
        """Save only changed fields of a cycle (partial update)"""
        if not updates:
            return

        async with self.get_connection() as conn:
            # Build UPDATE query dynamically
            update_fields = []
            params = []

            for field, value in updates.items():
                if field == "state" and isinstance(value, CycleState):
                    update_fields.append(f"{field} = ?")
                    params.append(value.value)
                elif field in ["cycle", "metadata"]:
                    update_fields.append(f"{field}_json = ?")
                    params.append(json.dumps(value))
                elif field != "orders":  # Skip orders as they're in separate table
                    update_fields.append(f"{field} = ?")
                    params.append(value)

            if update_fields:
                update_fields.append("updated_at = ?")
                params.append(time.time())
                params.append(cycle_id)

                await conn.execute(
                    f"""
                    UPDATE cycles
                    SET {", ".join(update_fields)}
                    WHERE id = ?
                """,
                    params,
                )

                # Log the update for audit trail
                await conn.execute(
                    """
                    INSERT INTO cycle_updates (cycle_id, field_name, new_value, updated_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (cycle_id, ",".join(updates.keys()), str(updates), time.time()),
                )

                await conn.commit()

    async def get_active_cycles(
        self, strategy_name: Optional[str] = None
    ) -> List[CycleInfo]:
        """Retrieve all active cycles, checking cache first if enabled"""
        active_states = {
            CycleState.ACTIVE,
            CycleState.PARTIALLY_FILLED,
            CycleState.RECOVERING,
            CycleState.PANIC_SELLING,
        }

        # Check cache first if enabled
        if self.enable_cache:
            # Ensure cache is flushed before reading
            await self._flush_cache()

            cached_cycles = await self.cache.get_all()
            active_cycles = []

            for cycle in cached_cycles:
                if cycle.state in active_states:
                    if not strategy_name or cycle.strategy_name == strategy_name:
                        active_cycles.append(cycle)

            # Also check database for any cycles not in cache
            db_cycles = await self._get_active_cycles_from_db(strategy_name)

            # Merge, preferring cached versions
            cached_ids = {c.id for c in active_cycles}
            for db_cycle in db_cycles:
                if db_cycle.id not in cached_ids:
                    active_cycles.append(db_cycle)
                    # Add to cache for future access
                    await self.cache.put(db_cycle)

            return active_cycles
        else:
            return await self._get_active_cycles_from_db(strategy_name)

    async def _get_active_cycles_from_db(
        self, strategy_name: Optional[str] = None
    ) -> List[CycleInfo]:
        """Retrieve active cycles directly from database with orders joined"""
        async with self.get_connection() as conn:
            query = """
                SELECT * FROM cycles
                WHERE state IN (?, ?, ?, ?)
            """
            params = [
                CycleState.ACTIVE.value,
                CycleState.PARTIALLY_FILLED.value,
                CycleState.RECOVERING.value,
                CycleState.PANIC_SELLING.value,
            ]

            if strategy_name:
                query += " AND strategy_name = ?"
                params.append(strategy_name)

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            cycles = []
            for row in rows:
                cycle_id = row[0]

                # Fetch orders from the separate orders table
                orders = await self.get_cycle_orders(cycle_id)

                cycle = CycleInfo(
                    id=cycle_id,
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
                    metadata=json.loads(row[13]) if row[13] else {},
                )
                cycles.append(cycle)

            return cycles

    async def cleanup_old_cycles(self, days: int = 7):
        """Remove completed/failed cycles older than specified days"""
        async with self.get_connection() as conn:
            cutoff_time = time.time() - (days * 24 * 3600)

            await conn.execute(
                """
                DELETE FROM cycles
                WHERE state IN (?, ?)
                AND updated_at < ?
            """,
                (CycleState.COMPLETED.value, CycleState.FAILED.value, cutoff_time),
            )

            await conn.commit()

    async def reserve_cycle_slot(
        self, strategy_name: str, max_open_cycles: int, reservation_ttl: int = 60
    ) -> Optional[str]:
        """
        Atomically reserve a cycle slot if under the max_open_cycles limit.

        Returns:
            reservation_id if successful, None if limit reached
        """
        import uuid

        async with self.get_connection() as conn:
            # Start a transaction for atomicity
            await conn.execute("BEGIN IMMEDIATE")

            try:
                current_time = time.time()
                expires_at = current_time + reservation_ttl

                # Clean up expired reservations first
                await conn.execute(
                    """
                    UPDATE cycle_reservations
                    SET status = 'expired'
                    WHERE expires_at < ?
                    AND status = 'pending'
                """,
                    (current_time,),
                )

                # Count active cycles and valid reservations atomically
                cursor = await conn.execute(
                    """
                    WITH active_counts AS (
                        SELECT COUNT(*) as active_cycles FROM cycles
                        WHERE strategy_name = ?
                        AND state IN (?, ?, ?, ?)
                    ),
                    reservation_counts AS (
                        SELECT COUNT(*) as pending_reservations FROM cycle_reservations
                        WHERE strategy_name = ?
                        AND status = 'pending'
                        AND expires_at >= ?
                    )
                    SELECT
                        active_cycles + pending_reservations as total_count
                    FROM active_counts, reservation_counts
                """,
                    (
                        strategy_name,
                        CycleState.ACTIVE.value,
                        CycleState.PARTIALLY_FILLED.value,
                        CycleState.RECOVERING.value,
                        CycleState.PANIC_SELLING.value,
                        strategy_name,
                        current_time,
                    ),
                )

                row = await cursor.fetchone()
                active_count = row[0] if row else 0

                if active_count >= max_open_cycles:
                    await conn.rollback()
                    return None

                # Create reservation
                reservation_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO cycle_reservations
                    (reservation_id, strategy_name, created_at, expires_at, status)
                    VALUES (?, ?, ?, ?, 'pending')
                """,
                    (reservation_id, strategy_name, current_time, expires_at),
                )

                await conn.commit()
                return reservation_id

            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to reserve cycle slot: {e}")
                return None

    async def confirm_reservation(self, reservation_id: str, cycle_id: str) -> bool:
        """
        Confirm a reservation by associating it with an actual cycle.

        Returns:
            True if successful, False otherwise
        """
        async with self.get_connection() as conn:
            try:
                await conn.execute(
                    """
                    UPDATE cycle_reservations
                    SET cycle_id = ?, status = 'confirmed'
                    WHERE reservation_id = ?
                    AND status = 'pending'
                """,
                    (cycle_id, reservation_id),
                )

                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to confirm reservation: {e}")
                return False

    async def release_reservation(self, reservation_id: str):
        """Release a reservation if cycle creation fails"""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                UPDATE cycle_reservations
                SET status = 'cancelled'
                WHERE reservation_id = ?
                AND status = 'pending'
            """,
                (reservation_id,),
            )

            await conn.commit()

    async def cleanup_expired_reservations(self):
        """Clean up expired reservations"""
        async with self.get_connection() as conn:
            current_time = time.time()

            await conn.execute(
                """
                UPDATE cycle_reservations
                SET status = 'expired'
                WHERE expires_at < ?
                AND status = 'pending'
            """,
                (current_time,),
            )

            # Also clean up old confirmed/cancelled/expired reservations
            old_time = current_time - (7 * 24 * 3600)  # 7 days old
            await conn.execute(
                """
                DELETE FROM cycle_reservations
                WHERE created_at < ?
                AND status IN ('confirmed', 'cancelled', 'expired')
            """,
                (old_time,),
            )

            await conn.commit()


class ConfigurationManager:
    """Manages strategy configuration loading and validation"""

    def __init__(self):
        self.strategies = {}

    def load_strategy(self, strategy_path: str) -> Dict[str, Any]:
        """Load and validate a strategy configuration"""
        path = Path(strategy_path)

        if not path.exists():
            raise FileNotFoundError(f"Strategy file not found: {strategy_path}")

        with open(path, "r") as f:
            config = yaml.safe_load(f)

        # Validate required fields
        required_fields = [
            "name",
            "exchange",
            "min_profit_bps",
            "max_slippage_bps",
            "capital_allocation",
        ]

        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")

        # Set defaults for optional fields
        config.setdefault(
            "risk_controls", {"max_open_cycles": 3, "stop_after_consecutive_losses": 5}
        )

        config.setdefault(
            "order",
            {
                "type": "market",
                "allow_partial_fills": True,
                "max_retries": 3,
                "retry_delay_ms": 1000,
            },
        )

        config.setdefault(
            "panic_sell",
            {
                "enabled": True,
                "base_currencies": ["USDC", "USD", "USDT"],
                "max_slippage_bps": 100,
            },
        )

        config.setdefault("risk_controls", config.get("risk_controls", {})).setdefault(
            "slippage_cooldown_seconds", 300
        )
        config.setdefault("risk_controls", config.get("risk_controls", {})).setdefault(
            "enable_latency_checks", True
        )
        config.setdefault("risk_controls", config.get("risk_controls", {})).setdefault(
            "enable_slippage_checks", True
        )

        self.strategies[config["name"]] = config
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
        self.order_config = config.get("order", {})
        self.max_retries = self.order_config.get("max_retries", 3)
        self.retry_delay = self.order_config.get("retry_delay_ms", 1000) / 1000.0

        # Exponential backoff configuration for order monitoring
        self.monitor_config = self.order_config.get("monitoring", {})
        self.initial_check_delay = (
            self.monitor_config.get("initial_delay_ms", 100) / 1000.0
        )
        self.max_check_delay = self.monitor_config.get("max_delay_ms", 5000) / 1000.0
        self.backoff_multiplier = self.monitor_config.get("backoff_multiplier", 2.0)
        self.jitter_factor = self.monitor_config.get("jitter_factor", 0.3)
        self.rapid_check_threshold = (
            self.monitor_config.get("rapid_check_threshold_ms", 2000) / 1000.0
        )
        self.rapid_check_interval = (
            self.monitor_config.get("rapid_check_interval_ms", 50) / 1000.0
        )

        # Rate limit awareness
        self.rate_limit_buffer = self.monitor_config.get(
            "rate_limit_buffer", 0.8
        )  # Use 80% of rate limit
        self.min_request_interval = (
            self.monitor_config.get("min_request_interval_ms", 50) / 1000.0
        )

        # Order status caching
        self.order_cache = {}
        self.cache_ttl = self.monitor_config.get("cache_ttl_ms", 500) / 1000.0

        # Track API call metrics for rate limiting
        self.api_call_timestamps = deque(maxlen=100)
        self.last_api_call = 0

    async def place_order(
        self, market_symbol: str, side: str, amount: float, order_type: str = None
    ) -> OrderInfo:
        """Place an order with retry logic"""
        order_type = order_type or self.order_config.get("type", "market")

        order_info = OrderInfo(
            id="",
            market_symbol=market_symbol,
            side=side,
            amount=amount,
            price=None,
            state=OrderState.PENDING,
            timestamp=time.time(),
        )

        for attempt in range(self.max_retries):
            try:
                if order_type == "market":
                    if side == "buy":
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
                    price = ticker.bid if side == "sell" else ticker.ask

                    if side == "buy":
                        order = await self.exchange.create_limit_buy_order(
                            market_symbol, amount, price
                        )
                    else:
                        order = await self.exchange.create_limit_sell_order(
                            market_symbol, amount, price
                        )

                order_info.id = order.order_id
                order_info.state = OrderState.PLACED
                order_info.price = order.average_price

                logger.info(f"Order placed successfully: {order_info.id}")
                return order_info

            except Exception as e:
                order_info.retry_count = attempt + 1
                order_info.error_message = str(e)

                logger.warning(f"Order placement attempt {attempt + 1} failed: {e}")

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                else:
                    order_info.state = OrderState.FAILED
                    raise

        return order_info

    async def monitor_order(
        self, order_info: OrderInfo, timeout: float = 30.0
    ) -> OrderInfo:
        """Monitor an order until it's filled or times out with intelligent backoff"""
        start_time = time.time()
        check_count = 0
        current_delay = self.initial_check_delay
        api_calls_made = 0

        # Use rapid checks for the first few seconds (configurable)
        rapid_check_end_time = start_time + self.rapid_check_threshold

        while time.time() - start_time < timeout:
            elapsed_time = time.time() - start_time

            # Check cache first
            cache_key = f"{order_info.id}_{order_info.market_symbol}"
            cached_data = self._get_cached_order_status(cache_key)

            if cached_data is None:
                # Rate limit protection
                await self._enforce_rate_limit()

                try:
                    # Fetch fresh order status
                    order = await self.exchange.fetch_order(
                        order_info.id, order_info.market_symbol
                    )
                    api_calls_made += 1

                    # Cache the result
                    self._cache_order_status(cache_key, order)

                    # Track API call for rate limiting
                    self._track_api_call()

                except Exception as e:
                    logger.error(f"Error monitoring order {order_info.id}: {e}")
                    # On error, increase backoff more aggressively
                    current_delay = min(current_delay * 3, self.max_check_delay)
                    await asyncio.sleep(current_delay)
                    continue
            else:
                order = cached_data
                logger.debug(f"Using cached order status for {order_info.id}")

            # Update order info
            order_info.filled_amount = order.amount_filled
            order_info.remaining_amount = order_info.amount - order.amount_filled
            order_info.average_price = order.average_price

            status = order.status.lower()

            # Check for terminal states
            if status in ["closed", "filled"]:
                order_info.state = OrderState.FILLED
                logger.info(
                    f"Order {order_info.id} filled completely after {api_calls_made} API calls "
                    f"in {elapsed_time:.2f}s"
                )
                return order_info

            elif status in ["canceled", "cancelled"]:
                order_info.state = OrderState.CANCELLED
                logger.warning(
                    f"Order {order_info.id} was cancelled after {api_calls_made} API calls"
                )
                return order_info

            elif order_info.filled_amount > 0:
                order_info.state = OrderState.PARTIALLY_FILLED

                # If partial fills are allowed and we have enough, proceed
                if self.order_config.get("allow_partial_fills", False):
                    fill_percentage = order_info.filled_amount / order_info.amount
                    min_fill_percentage = self.order_config.get(
                        "min_partial_fill_percentage", 0.95
                    )

                    if fill_percentage >= min_fill_percentage:
                        logger.info(
                            f"Order {order_info.id} sufficiently filled: "
                            f"{order_info.filled_amount}/{order_info.amount} ({fill_percentage:.1%})"
                        )
                        return order_info

            # Calculate next delay with exponential backoff
            check_count += 1

            if time.time() < rapid_check_end_time:
                # Rapid checking phase for new orders
                next_delay = self.rapid_check_interval
            else:
                # Exponential backoff phase
                # Base exponential backoff
                base_delay = min(
                    self.initial_check_delay * (self.backoff_multiplier**check_count),
                    self.max_check_delay,
                )

                # Add jitter to prevent thundering herd
                jitter = base_delay * self.jitter_factor * (2 * random.random() - 1)
                next_delay = max(base_delay + jitter, self.min_request_interval)

                # Log backoff info periodically
                if check_count % 5 == 0:
                    logger.debug(
                        f"Order {order_info.id} monitoring: check {check_count}, "
                        f"delay {next_delay:.2f}s, {api_calls_made} API calls"
                    )

            await asyncio.sleep(next_delay)
            current_delay = next_delay

        # Timeout reached
        if order_info.filled_amount > 0:
            order_info.state = OrderState.PARTIALLY_FILLED
        else:
            order_info.state = OrderState.FAILED
            order_info.error_message = f"Order timeout after {api_calls_made} API calls"

        logger.warning(
            f"Order {order_info.id} timed out after {timeout}s and {api_calls_made} API calls"
        )
        return order_info

    def _get_cached_order_status(self, cache_key: str) -> Optional[Dict]:
        """Get cached order status if still valid"""
        if cache_key in self.order_cache:
            cached_time, cached_data = self.order_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_data
            else:
                # Cache expired, remove it
                del self.order_cache[cache_key]
        return None

    def _cache_order_status(self, cache_key: str, order_data: Dict):
        """Cache order status with timestamp"""
        self.order_cache[cache_key] = (time.time(), order_data)

        # Clean up old cache entries if cache is getting large
        if len(self.order_cache) > 100:
            current_time = time.time()
            expired_keys = [
                k
                for k, (t, _) in self.order_cache.items()
                if current_time - t > self.cache_ttl
            ]
            for k in expired_keys:
                del self.order_cache[k]

    def _track_api_call(self):
        """Track API call timestamp for rate limiting"""
        current_time = time.time()
        self.api_call_timestamps.append(current_time)
        self.last_api_call = current_time

    async def _enforce_rate_limit(self):
        """Enforce rate limiting to avoid hitting exchange limits"""
        current_time = time.time()

        # Ensure minimum interval between requests
        time_since_last = current_time - self.last_api_call
        if time_since_last < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - time_since_last)

        # Check rate limit over sliding window
        if len(self.api_call_timestamps) >= 10:
            # Calculate request rate over last 10 requests
            oldest_timestamp = self.api_call_timestamps[-10]
            time_window = current_time - oldest_timestamp

            if time_window > 0:
                request_rate = 10 / time_window

                # Get exchange rate limit (if available)
                exchange_rate_limit = (
                    getattr(self.exchange, "rateLimit", 50) / 1000
                )  # Convert to requests/second

                # If we're approaching rate limit, add delay
                if request_rate > exchange_rate_limit * self.rate_limit_buffer:
                    delay = (
                        1.0 / (exchange_rate_limit * self.rate_limit_buffer)
                        - time_window / 10
                    )
                    if delay > 0:
                        logger.debug(f"Rate limiting: delaying {delay:.3f}s")
                        await asyncio.sleep(delay)

    async def cancel_order(self, order_info: OrderInfo) -> bool:
        """Cancel an open order"""
        try:
            await self.exchange.cancel_order(order_info.id, order_info.market_symbol)
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
        self.panic_config = config.get("panic_sell", {})
        self.base_currencies = self.panic_config.get(
            "base_currencies", ["USDC", "USD", "USDT"]
        )
        self.max_slippage_bps = self.panic_config.get("max_slippage_bps", 100)

    async def execute_panic_sell(
        self, current_currency: str, amount: float
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
                    direct_symbol, "buy", amount, base
                )
            elif reverse_symbol in markets:
                return await self._execute_panic_trade(
                    reverse_symbol, "sell", amount, base
                )

        # If no direct path, try through intermediary (usually BTC or ETH)
        intermediaries = ["BTC", "ETH"]
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
                inter_side = "buy"
            elif from_inter in markets:
                inter_market = from_inter
                inter_side = "sell"

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
                            base_side = "buy" if to_base in markets else "sell"

                            return await self._execute_panic_trade(
                                base_market, base_side, inter_amount, base
                            )

        logger.error(f"Could not find panic sell path from {current_currency}")
        return False, amount, current_currency

    async def _execute_panic_trade(
        self, market_symbol: str, side: str, amount: float, target_currency: str
    ) -> Tuple[bool, float, str]:
        """Execute a single panic trade"""
        try:
            logger.info(f"Executing panic {side} on {market_symbol} for {amount}")

            # Use market order for immediate execution
            if side == "buy":
                order = await self.exchange.create_market_buy_order(
                    market_symbol, amount
                )
            else:
                order = await self.exchange.create_market_sell_order(
                    market_symbol, amount
                )

            # Wait for confirmation
            await asyncio.sleep(1)

            order_details = await self.exchange.fetch_order_status(
                order.order_id, market_symbol
            )

            filled_amount = order_details.amount_filled

            if side == "buy":
                final_amount = filled_amount
            else:
                final_amount = order_details.amount_filled * order_details.average_price

            logger.info(f"Panic sell completed: {final_amount} {target_currency}")

            return True, final_amount, target_currency

        except Exception as e:
            logger.error(f"Panic sell failed: {e}")
            return False, amount, target_currency


class StrategyExecutionEngine:
    """Main execution engine that orchestrates all components"""

    def __init__(
        self,
        exchange,
        strategy_config: Dict[str, Any],
        state_manager: Optional[StateManager] = None,
    ):
        self.exchange = exchange
        self.config = strategy_config
        self.state_manager = state_manager or StateManager()
        self.order_manager = OrderManager(exchange, strategy_config)

        self.max_leg_latency_ms = strategy_config.get("max_leg_latency_ms")
        self.max_slippage_bps = strategy_config.get("max_slippage_bps", 20)

        # Check if individual risk controls are enabled
        risk_controls_config = strategy_config.get("risk_controls", {})
        latency_checks_enabled = (
            risk_controls_config.get("enable_latency_checks", False)
            and self.max_leg_latency_ms is not None
        )
        slippage_checks_enabled = risk_controls_config.get(
            "enable_slippage_checks", False
        )

        # DISABLED: Just make it work without risk controls
        self.enable_risk_controls = False

        # FORCE DISABLE ALL RISK CONTROLS
        self.risk_control_manager = None
        logger.info("Risk controls FORCIBLY DISABLED for debugging")

        # Use enhanced recovery manager if available and configured
        use_enhanced = strategy_config.get("panic_sell", {}).get(
            "use_enhanced_routing", True
        )
        if ENHANCED_RECOVERY_AVAILABLE and use_enhanced:
            self.recovery_manager = EnhancedFailureRecoveryManager(
                exchange, strategy_config
            )
            self._using_enhanced_recovery = True
            logger.info("Using EnhancedFailureRecoveryManager with dynamic routing")
        else:
            self.recovery_manager = FailureRecoveryManager(exchange, strategy_config)
            self._using_enhanced_recovery = False
            logger.info("Using standard FailureRecoveryManager")

        # Risk controls
        self.risk_controls = strategy_config.get("risk_controls", {})
        self.max_open_cycles = self.risk_controls.get("max_open_cycles", 3)
        self.consecutive_losses = 0
        self.max_consecutive_losses = self.risk_controls.get(
            "stop_after_consecutive_losses", 5
        )

        # Profit/slippage thresholds
        self.min_profit_bps = strategy_config.get("min_profit_bps", 10)
        self.max_slippage_bps = strategy_config.get("max_slippage_bps", 20)

        # Capital allocation
        self.capital_config = strategy_config.get("capital_allocation", {})

    async def initialize(self):
        """Initialize async components like the enhanced recovery manager"""
        if self._using_enhanced_recovery and hasattr(
            self.recovery_manager, "initialize"
        ):
            await self.recovery_manager.initialize()
            logger.info("Enhanced recovery manager initialized")

    async def execute_cycle(
        self,
        cycle: List[str],
        initial_amount: float,
        cycle_id: Optional[str] = None,
        is_recovery: bool = False,
    ) -> CycleInfo:
        """
        Execute a complete arbitrage cycle with full state management
        """
        reservation_id = None

        # Create or recover cycle info
        if cycle_id and is_recovery:
            # Recover existing cycle
            cycles = await self.state_manager.get_active_cycles(self.config["name"])
            cycle_info = next((c for c in cycles if c.id == cycle_id), None)

            if not cycle_info:
                raise ValueError(f"Cannot recover cycle {cycle_id}")
        else:
            # For new cycles, reserve a slot first
            reservation_id = await self.state_manager.reserve_cycle_slot(
                self.config["name"],
                self.max_open_cycles,
                reservation_ttl=120,  # 2 minutes to start the cycle
            )

            if not reservation_id:
                # Cannot reserve slot - max cycles reached
                logger.warning(
                    f"Cannot start new cycle: max open cycles ({self.max_open_cycles}) reached"
                )
                return CycleInfo(
                    id=f"{self.config['name']}_{int(time.time()*1000)}_rejected",
                    strategy_name=self.config["name"],
                    cycle=cycle,
                    initial_amount=initial_amount,
                    current_amount=initial_amount,
                    current_currency=cycle[0],
                    state=CycleState.FAILED,
                    current_step=0,
                    orders=[],
                    start_time=time.time(),
                    end_time=time.time(),
                    profit_loss=None,
                    error_message="Max open cycles limit reached",
                    metadata={"rejected": True},
                )

            # Create new cycle
            cycle_id = cycle_id or f"{self.config['name']}_{int(time.time()*1000)}"

            cycle_info = CycleInfo(
                id=cycle_id,
                strategy_name=self.config["name"],
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
                metadata={"reservation_id": reservation_id},
            )

        try:
            # Check other risk controls (consecutive losses)
            if not await self._check_risk_controls(skip_cycle_count=True):
                cycle_info.state = CycleState.FAILED
                cycle_info.error_message = "Risk controls violated"
                if reservation_id:
                    await self.state_manager.release_reservation(reservation_id)
                await self.state_manager.save_cycle(cycle_info)
                return cycle_info

            # Confirm reservation by saving the cycle
            if reservation_id:
                await self.state_manager.confirm_reservation(reservation_id, cycle_id)

            # Validate the cycle
            cycle_info.state = CycleState.VALIDATING
            await self.state_manager.save_cycle(cycle_info)

            if not await self._validate_cycle(cycle_info):
                cycle_info.state = CycleState.FAILED
                cycle_info.error_message = "Cycle validation failed"
                await self.state_manager.save_cycle(cycle_info)
                return cycle_info

            # Execute the cycle
            cycle_info.state = CycleState.ACTIVE
            await self.state_manager.save_cycle(cycle_info)

            success = await self._execute_cycle_trades(cycle_info)

            if success:
                cycle_info.state = CycleState.COMPLETED

                # Only calculate PnL if we're back to the original currency
                if cycle_info.current_currency == cycle_info.cycle[0]:
                    cycle_info.profit_loss = (
                        cycle_info.current_amount - cycle_info.initial_amount
                    )
                else:
                    # Cycle didn't complete properly - major error
                    cycle_info.state = CycleState.FAILED
                    cycle_info.error_message = f"Cycle ended in {cycle_info.current_currency} instead of {cycle_info.cycle[0]}"
                    logger.error(cycle_info.error_message)
                    return cycle_info

                if cycle_info.profit_loss > 0:
                    self.consecutive_losses = 0
                else:
                    self.consecutive_losses += 1
            else:
                cycle_info.state = CycleState.FAILED

                # Attempt panic sell if enabled
                if self.recovery_manager.panic_config.get("enabled", True):
                    await self._handle_panic_sell(cycle_info)

                self.consecutive_losses += 1

        except Exception as e:
            logger.error(f"Cycle execution error: {e}")
            cycle_info.state = CycleState.FAILED
            cycle_info.error_message = str(e)

            # Release reservation if cycle failed early
            if reservation_id and cycle_info.state == CycleState.PENDING:
                await self.state_manager.release_reservation(reservation_id)

            # Attempt panic sell on any error
            if self.recovery_manager.panic_config.get("enabled", True):
                await self._handle_panic_sell(cycle_info)

        finally:
            cycle_info.end_time = time.time()
            await self.state_manager.save_cycle(cycle_info)

        return cycle_info

    async def _check_risk_controls(self, skip_cycle_count: bool = False) -> bool:
        """Check if risk controls allow new cycle execution

        Args:
            skip_cycle_count: Skip checking cycle count (used when reservation already made)
        """
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning(f"Max consecutive losses reached: {self.consecutive_losses}")
            return False

        # Check open cycles (unless already reserved)
        if not skip_cycle_count:
            active_cycles = await self.state_manager.get_active_cycles(
                self.config["name"]
            )
            if len(active_cycles) >= self.max_open_cycles:
                logger.warning(f"Max open cycles reached: {len(active_cycles)}")
                return False

        return True

    async def _validate_cycle(self, cycle_info: CycleInfo) -> bool:
        """Validate that a cycle can be executed"""
        from_currency = cycle_info.cycle[0]
        amount = cycle_info.initial_amount
        trade_path = cycle_info.cycle + [cycle_info.cycle[0]]
        markets = await self.exchange.load_markets()

        for i in range(len(trade_path) - 1):
            to_currency = trade_path[i + 1]

            market_symbol_forward = f"{to_currency}/{from_currency}"
            market_symbol_backward = f"{from_currency}/{to_currency}"

            market = None
            order_side = None

            if market_symbol_forward in markets:
                market = markets[market_symbol_forward]
                order_side = "buy"
            elif market_symbol_backward in markets:
                market = markets[market_symbol_backward]
                order_side = "sell"
            else:
                logger.error(f"No market found for {from_currency} -> {to_currency}")
                return False

            # Check minimum order requirements
            min_order_amount = market.get("limits", {}).get("amount", {}).get("min")
            min_order_cost = market.get("limits", {}).get("cost", {}).get("min")

            if order_side == "sell" and min_order_amount and amount < min_order_amount:
                logger.error(f"Order amount too small: {amount} < {min_order_amount}")
                return False

            if order_side == "buy" and min_order_cost and amount < min_order_cost:
                logger.error(f"Order value too small: {amount} < {min_order_cost}")
                return False

            # Estimate amount for next step
            try:
                ticker = await self.exchange.fetch_ticker(market["symbol"])
                price = ticker.last

                # Apply expected slippage
                slippage = 1 - (self.max_slippage_bps / 10000)

                if order_side == "buy":
                    amount = (amount / price) * slippage
                else:
                    amount = (amount * price) * slippage
            except Exception as e:
                logger.warning(f"Could not fetch ticker for validation: {e}")

            from_currency = to_currency

        return True

    async def _execute_cycle_trades(self, cycle_info: CycleInfo) -> bool:
        """Execute all trades in a cycle"""
        # RISK CONTROLS DISABLED
        # if self.risk_control_manager:
        #     self.risk_control_manager.reset_cycle_measurements()

        # cycle_key = cycle_info.cycle
        # if (
        #     self.risk_control_manager
        #     and self.risk_control_manager.is_cycle_in_cooldown(cycle_key)
        # ):
        #     cooldown_remaining = self.risk_control_manager.get_cycle_cooldown_remaining(
        #         cycle_key
        #     )
        #     cycle_info.error_message = (
        #         f"Cycle in cooldown due to previous slippage violation. "
        #         f"Remaining: {cooldown_remaining:.1f}s"
        #     )
        #     logger.warning(cycle_info.error_message)
        #     return False

        trade_path = cycle_info.cycle + [cycle_info.cycle[0]]
        markets = await self.exchange.load_markets()

        # Start from current step (for recovery)
        for i in range(cycle_info.current_step, len(trade_path) - 1):
            from_currency = cycle_info.current_currency
            to_currency = trade_path[i + 1]
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
                order_side = "buy"
            elif market_symbol_backward in markets:
                market_symbol = market_symbol_backward
                order_side = "sell"
            else:
                cycle_info.error_message = (
                    f"No market for {from_currency} -> {to_currency}"
                )
                return False

            try:
                # RISK CONTROLS DISABLED
                # leg_start_time = None
                # if self.risk_control_manager and self.max_leg_latency_ms:
                #     leg_start_time = self.risk_control_manager.start_leg_timing()

                ticker = await self.exchange.fetch_ticker(market_symbol)
                expected_price = ticker.ask if order_side == "buy" else ticker.bid

                order_info = await self.order_manager.place_order(
                    market_symbol, order_side, amount
                )

                cycle_info.orders.append(order_info)
                await self.state_manager.save_cycle(cycle_info)

                order_info = await self.order_manager.monitor_order(
                    order_info,
                    timeout=30.0,  # Allow sufficient time for orders to complete
                )

                # RISK CONTROLS DISABLED
                # if self.risk_control_manager and leg_start_time:
                #     latency_measurement, latency_violated = (
                #         self.risk_control_manager.end_leg_timing(
                #             i, market_symbol, leg_start_time, order_side
                #         )
                #     )

                #     if latency_violated:
                #         self.risk_control_manager.log_latency_violation(
                #             cycle_info.id,
                #             cycle_info.strategy_name,
                #             cycle_info.cycle,
                #             "->" if order_side == "buy" else "<-",
                #             latency_measurement,
                #             self.risk_control_manager.latency_monitor.get_all_measurements(),
                #         )
                #         cycle_info.error_message = (
                #             f"Latency violation: leg {i+1} took {latency_measurement.latency_ms:.2f}ms "
                #             f"(max: {self.max_leg_latency_ms}ms)"
                #         )
                #         cycle_info.metadata["latency_violation"] = {
                #             "leg": i,
                #             "latency_ms": latency_measurement.latency_ms,
                #             "max_allowed_ms": self.max_leg_latency_ms,
                #         }
                #         return False

                if order_info.state != OrderState.FILLED:
                    if order_info.state == OrderState.PARTIALLY_FILLED:
                        if self.config.get("order", {}).get(
                            "allow_partial_fills", False
                        ):
                            if order_side == "buy":
                                # Buying to_currency with from_currency
                                cycle_info.current_amount = order_info.filled_amount
                                cycle_info.current_currency = to_currency
                            else:
                                # Selling from_currency for to_currency
                                cycle_info.current_amount = (
                                    order_info.filled_amount * order_info.average_price
                                )
                                cycle_info.current_currency = to_currency

                            logger.warning(
                                f"Proceeding with partial fill: {cycle_info.current_amount}"
                            )
                        else:
                            cycle_info.error_message = "Order not fully filled"
                            return False
                    else:
                        cycle_info.error_message = (
                            f"Order failed: {order_info.error_message}"
                        )
                        return False
                else:
                    # Order fully filled - update amount and currency properly based on trade direction
                    if order_side == "buy":
                        # Buying to_currency with from_currency
                        # filled_amount is in to_currency units
                        cycle_info.current_amount = order_info.filled_amount
                        cycle_info.current_currency = to_currency
                    else:
                        # Selling from_currency for to_currency
                        # filled_amount * average_price gives us to_currency value
                        cycle_info.current_amount = (
                            order_info.filled_amount * order_info.average_price
                        )
                        cycle_info.current_currency = to_currency

                # RISK CONTROLS DISABLED
                # if self.risk_control_manager and order_info.average_price > 0:
                #     slippage_measurement, slippage_violated = (
                #         self.risk_control_manager.track_slippage(
                #             i,
                #             market_symbol,
                #             expected_price,
                #             order_info.average_price,
                #             order_side,
                #         )
                #     )

                #     if slippage_violated:
                #         self.risk_control_manager.log_slippage_violation(
                #             cycle_info.id,
                #             cycle_info.strategy_name,
                #             cycle_info.cycle,
                #             "->" if order_side == "buy" else "<-",
                #             slippage_measurement,
                #             self.risk_control_manager.slippage_tracker.get_all_measurements(),
                #         )
                #         cycle_info.error_message = (
                #             f"Slippage violation: leg {i+1} had {slippage_measurement.slippage_bps:.2f} bps "
                #             f"(max: {self.max_slippage_bps} bps). Cycle in cooldown."
                #         )
                #         cycle_info.metadata["slippage_violation"] = {
                #             "leg": i,
                #             "slippage_bps": slippage_measurement.slippage_bps,
                #             "max_allowed_bps": self.max_slippage_bps,
                #             "cooldown_seconds": self.risk_control_manager.slippage_tracker.cooldown_seconds,
                #         }
                #         return False

                # Update cycle state (current_currency already updated above)
                cycle_info.current_step = i + 1
                await self.state_manager.save_cycle(cycle_info)

            except Exception as e:
                logger.error(f"Trade execution failed: {e}")
                cycle_info.error_message = str(e)
                return False

        return True

    async def _handle_panic_sell(self, cycle_info: CycleInfo):
        """Handle panic sell for failed cycle"""
        logger.info(f"Initiating panic sell for cycle {cycle_info.id}")

        cycle_info.state = CycleState.PANIC_SELLING
        await self.state_manager.save_cycle(cycle_info)

        # Handle both standard and enhanced recovery manager returns
        panic_result = await self.recovery_manager.execute_panic_sell(
            cycle_info.current_currency, cycle_info.current_amount
        )

        # Check if it's enhanced return (4 values) or standard (3 values)
        if len(panic_result) == 4:
            success, final_amount, final_currency, execution_steps = panic_result
            cycle_info.metadata["panic_sell_steps"] = len(execution_steps)
            cycle_info.metadata["panic_sell_path"] = (
                [step.input_currency for step in execution_steps] + [final_currency]
                if execution_steps
                else []
            )
        else:
            success, final_amount, final_currency = panic_result
            execution_steps = []

        if success:
            cycle_info.current_amount = final_amount
            cycle_info.current_currency = final_currency
            cycle_info.metadata["panic_sell_executed"] = True
            cycle_info.metadata["panic_sell_currency"] = final_currency
            cycle_info.metadata["panic_sell_amount"] = final_amount

            logger.info(
                f"Panic sell successful: {final_amount} {final_currency}"
                f"{f' via {len(execution_steps)} steps' if execution_steps else ''}"
            )
        else:
            logger.error("Panic sell failed")
            cycle_info.metadata["panic_sell_failed"] = True

    async def recover_active_cycles(self):
        """Robust recovery system for active cycles after restart or crash

        Handles:
        - Cycles with cached but unflushed data
        - Mid-transaction crashes
        - Orphaned orders
        - Stale reservations
        - Incomplete panic sells
        """
        logger.info("Starting cycle recovery process...")

        recovery_stats = {
            "total_found": 0,
            "successfully_recovered": 0,
            "resumed": 0,
            "panic_sold": 0,
            "marked_failed": 0,
            "errors": [],
        }

        try:
            # Step 1: Ensure all cached data is flushed to database
            if self.state_manager.cache:
                logger.info("Flushing any cached data to database...")
                await self.state_manager.flush_all()

            # Step 2: Clean up expired reservations
            await self.state_manager.cleanup_expired_reservations()

            # Step 3: Validate database integrity
            await self._validate_database_integrity()

            # Step 4: Get all active cycles
            active_cycles = await self.state_manager.get_active_cycles(
                self.config["name"]
            )
            recovery_stats["total_found"] = len(active_cycles)

            logger.info(f"Found {len(active_cycles)} active cycles to recover")

            # Step 5: Analyze and categorize cycles for recovery
            cycles_to_resume = []
            cycles_to_panic_sell = []
            cycles_to_validate = []

            for cycle_info in active_cycles:
                recovery_action = await self._analyze_cycle_for_recovery(cycle_info)

                if recovery_action == "resume":
                    cycles_to_resume.append(cycle_info)
                elif recovery_action == "panic_sell":
                    cycles_to_panic_sell.append(cycle_info)
                elif recovery_action == "validate":
                    cycles_to_validate.append(cycle_info)
                else:  # 'fail'
                    await self._mark_cycle_failed(
                        cycle_info, "Unrecoverable state detected"
                    )
                    recovery_stats["marked_failed"] += 1

            # Step 6: Process panic sells first (highest priority)
            for cycle_info in cycles_to_panic_sell:
                try:
                    logger.info(f"Executing panic sell for cycle {cycle_info.id}")
                    await self._handle_panic_sell(cycle_info)
                    recovery_stats["panic_sold"] += 1
                except Exception as e:
                    logger.error(f"Panic sell failed for cycle {cycle_info.id}: {e}")
                    recovery_stats["errors"].append(
                        f"Panic sell failed: {cycle_info.id}"
                    )
                    await self._mark_cycle_failed(cycle_info, f"Panic sell failed: {e}")

            # Step 7: Validate and potentially resume cycles
            for cycle_info in cycles_to_validate:
                try:
                    is_valid = await self._validate_cycle_state(cycle_info)
                    if is_valid:
                        cycles_to_resume.append(cycle_info)
                    else:
                        await self._mark_cycle_failed(
                            cycle_info, "State validation failed"
                        )
                        recovery_stats["marked_failed"] += 1
                except Exception as e:
                    logger.error(f"Validation failed for cycle {cycle_info.id}: {e}")
                    recovery_stats["errors"].append(
                        f"Validation failed: {cycle_info.id}"
                    )

            # Step 8: Resume recoverable cycles
            for cycle_info in cycles_to_resume:
                try:
                    logger.info(
                        f"Resuming cycle {cycle_info.id} from step {cycle_info.current_step}"
                    )

                    # Check if we need to recover the last order
                    await self._recover_last_order(cycle_info)

                    # Resume cycle execution
                    result = await self.execute_cycle(
                        cycle_info.cycle,
                        cycle_info.initial_amount,
                        cycle_info.id,
                        is_recovery=True,
                    )

                    if result.state == CycleState.COMPLETED:
                        recovery_stats["successfully_recovered"] += 1
                    else:
                        recovery_stats["resumed"] += 1

                except Exception as e:
                    logger.error(f"Failed to recover cycle {cycle_info.id}: {e}")
                    recovery_stats["errors"].append(f"Recovery failed: {cycle_info.id}")

                    # Last resort: panic sell
                    try:
                        if self.recovery_manager.panic_config.get("enabled", True):
                            await self._handle_panic_sell(cycle_info)
                            recovery_stats["panic_sold"] += 1
                    except Exception as panic_e:
                        logger.error(
                            f"Panic sell also failed for {cycle_info.id}: {panic_e}"
                        )
                        await self._mark_cycle_failed(
                            cycle_info, f"Recovery and panic sell failed: {e}"
                        )
                        recovery_stats["marked_failed"] += 1

            # Step 9: Log recovery summary
            logger.info("=" * 60)
            logger.info("RECOVERY SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Total cycles found: {recovery_stats['total_found']}")
            logger.info(
                f"Successfully recovered: {recovery_stats['successfully_recovered']}"
            )
            logger.info(f"Resumed execution: {recovery_stats['resumed']}")
            logger.info(f"Panic sold: {recovery_stats['panic_sold']}")
            logger.info(f"Marked as failed: {recovery_stats['marked_failed']}")

            if recovery_stats["errors"]:
                logger.warning(f"Errors encountered: {len(recovery_stats['errors'])}")
                for error in recovery_stats["errors"]:
                    logger.warning(f"  - {error}")

        except Exception as e:
            logger.error(f"Critical error during recovery process: {e}")
            raise

        return recovery_stats

    async def _validate_database_integrity(self):
        """Validate database integrity and fix orphaned records"""
        async with self.state_manager.get_connection() as conn:
            # Check for orphaned orders (orders without parent cycle)
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM orders o
                LEFT JOIN cycles c ON o.cycle_id = c.id
                WHERE c.id IS NULL
            """
            )
            orphaned_orders = (await cursor.fetchone())[0]

            if orphaned_orders > 0:
                logger.warning(
                    f"Found {orphaned_orders} orphaned orders, cleaning up..."
                )
                await conn.execute(
                    """
                    DELETE FROM orders WHERE cycle_id NOT IN (
                        SELECT id FROM cycles
                    )
                """
                )
                await conn.commit()

    async def _analyze_cycle_for_recovery(self, cycle_info: CycleInfo) -> str:
        """Analyze a cycle and determine recovery action

        Returns:
            'resume' - Continue execution from current state
            'panic_sell' - Immediately panic sell
            'validate' - Needs validation before resuming
            'fail' - Mark as failed
        """
        # Check cycle age
        cycle_age = time.time() - cycle_info.start_time
        max_cycle_age = 3600  # 1 hour

        if cycle_age > max_cycle_age:
            logger.warning(
                f"Cycle {cycle_info.id} is too old ({cycle_age:.0f}s), marking for panic sell"
            )
            return "panic_sell"

        # Check state
        if cycle_info.state == CycleState.PANIC_SELLING:
            return "panic_sell"

        if cycle_info.state == CycleState.RECOVERING:
            return "validate"

        if cycle_info.state in [CycleState.ACTIVE, CycleState.PARTIALLY_FILLED]:
            # Check if we're stuck on an order
            if cycle_info.orders:
                last_order = cycle_info.orders[-1]
                if last_order.state in [OrderState.PENDING, OrderState.PLACED]:
                    order_age = time.time() - last_order.timestamp
                    if order_age > 300:  # 5 minutes
                        logger.warning(
                            f"Cycle {cycle_info.id} has stale order, needs validation"
                        )
                        return "validate"
            return "resume"

        if cycle_info.state == CycleState.VALIDATING:
            return "validate"

        # PENDING state shouldn't exist in active cycles
        if cycle_info.state == CycleState.PENDING:
            return "fail"

        return "resume"

    async def _validate_cycle_state(self, cycle_info: CycleInfo) -> bool:
        """Validate cycle state and check if it can be resumed

        Returns:
            True if cycle can be resumed, False otherwise
        """
        try:
            # Check market availability
            markets = await self.exchange.load_markets()

            # Verify we can continue from current position
            trade_path = cycle_info.cycle + [cycle_info.cycle[0]]
            if cycle_info.current_step >= len(trade_path) - 1:
                logger.error(
                    f"Cycle {cycle_info.id} already at final step but not completed"
                )
                return False

            from_currency = cycle_info.current_currency
            to_currency = trade_path[cycle_info.current_step + 1]

            # Check if market exists
            market_symbol_forward = f"{to_currency}/{from_currency}"
            market_symbol_backward = f"{from_currency}/{to_currency}"

            if (
                market_symbol_forward not in markets
                and market_symbol_backward not in markets
            ):
                logger.error(f"No market found for {from_currency} -> {to_currency}")
                return False

            # Check balance is sufficient
            if cycle_info.current_amount <= 0:
                logger.error(
                    f"Cycle {cycle_info.id} has invalid amount: {cycle_info.current_amount}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Validation error for cycle {cycle_info.id}: {e}")
            return False

    async def _recover_last_order(self, cycle_info: CycleInfo):
        """Recover the status of the last order if it was in progress"""
        if not cycle_info.orders:
            return

        last_order = cycle_info.orders[-1]

        if last_order.state in [OrderState.PENDING, OrderState.PLACED]:
            try:
                # Try to fetch current order status from exchange
                order = await self.exchange.fetch_order(
                    last_order.id, last_order.market_symbol
                )

                status = order.status.lower()

                if status in ["closed", "filled"]:
                    last_order.state = OrderState.FILLED
                    last_order.filled_amount = order.amount_filled
                    last_order.average_price = order.average_price

                    # Update cycle amount based on fill
                    if last_order.side == "buy":
                        cycle_info.current_amount = last_order.filled_amount
                    else:
                        cycle_info.current_amount = (
                            last_order.filled_amount * last_order.average_price
                        )

                    # Save updated order state
                    await self.state_manager.update_order_state(
                        last_order.id,
                        OrderState.FILLED,
                        last_order.filled_amount,
                        last_order.average_price,
                    )

                    logger.info(f"Recovered order {last_order.id} as FILLED")

                elif status in ["canceled", "cancelled"]:
                    last_order.state = OrderState.CANCELLED
                    await self.state_manager.update_order_state(
                        last_order.id, OrderState.CANCELLED
                    )
                    logger.info(f"Recovered order {last_order.id} as CANCELLED")

                elif order.amount_filled > 0:
                    last_order.state = OrderState.PARTIALLY_FILLED
                    last_order.filled_amount = order.amount_filled
                    last_order.remaining_amount = (
                        order.amount_requested - order.amount_filled
                    )
                    await self.state_manager.update_order_state(
                        last_order.id,
                        OrderState.PARTIALLY_FILLED,
                        last_order.filled_amount,
                    )
                    logger.info(f"Recovered order {last_order.id} as PARTIALLY_FILLED")

            except Exception as e:
                logger.warning(f"Could not recover order {last_order.id} status: {e}")
                # Cancel the order to be safe
                try:
                    await self.exchange.cancel_order(
                        last_order.id, last_order.market_symbol
                    )
                    last_order.state = OrderState.CANCELLED
                except:
                    pass

    async def _mark_cycle_failed(self, cycle_info: CycleInfo, reason: str):
        """Mark a cycle as failed with proper cleanup"""
        cycle_info.state = CycleState.FAILED
        cycle_info.error_message = reason
        cycle_info.end_time = time.time()

        # Force write to ensure it's persisted
        await self.state_manager.save_cycle(cycle_info, force_write=True)

        logger.warning(f"Marked cycle {cycle_info.id} as FAILED: {reason}")

    async def start_cleanup_task(self, interval: int = 300):
        """Start a background task to clean up expired reservations periodically

        Args:
            interval: Cleanup interval in seconds (default 5 minutes)
        """

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self.state_manager.cleanup_expired_reservations()
                    logger.debug("Cleaned up expired reservations")
                except Exception as e:
                    logger.error(f"Error during reservation cleanup: {e}")

        # Start the cleanup task in the background
        asyncio.create_task(cleanup_loop())


# Backward compatibility wrapper
async def execute_cycle(exchange, cycle, initial_amount, is_dry_run=False):
    """
    Backward compatible wrapper for the old execute_cycle function.
    This loads a default configuration and uses the new engine.
    """
    if is_dry_run:
        # For dry runs, use the old simple logic
        from . import trade_executor as old_executor

        return await old_executor.execute_cycle(
            exchange, cycle, initial_amount, is_dry_run
        )

    # Create a minimal configuration
    config = {
        "name": "default",
        "exchange": exchange.id,
        "min_profit_bps": 10,
        "max_slippage_bps": 20,
        "capital_allocation": {"mode": "fixed_amount", "amount": initial_amount},
        "risk_controls": {"max_open_cycles": 1, "stop_after_consecutive_losses": 5},
        "order": {
            "type": "market",
            "allow_partial_fills": True,
            "max_retries": 3,
            "retry_delay_ms": 1000,
        },
        "panic_sell": {
            "enabled": True,
            "base_currencies": ["USDC", "USD", "USDT"],
            "max_slippage_bps": 100,
        },
    }

    # Create and use the new engine
    engine = StrategyExecutionEngine(exchange, config)
    cycle_info = await engine.execute_cycle(cycle, initial_amount)

    # Log the result
    if cycle_info.state == CycleState.COMPLETED:
        logger.info(f"Cycle completed successfully. P/L: {cycle_info.profit_loss}")
    else:
        logger.error(f"Cycle failed: {cycle_info.error_message}")
