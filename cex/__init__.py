"""
CEX (Centralized Exchange) Arbitrage Module

This module provides triangular arbitrage trading capabilities for centralized exchanges.

Refactored from the monolithic trading_arbitrage.py (2,920 lines) into focused modules
for better maintainability, testability, and reusability.

Module Structure:
-----------------
- constants.py: Exchange fees, limits, and configuration constants
- balance_tracker.py: Balance and equity tracking (future)
- order_executor.py: Order execution and depth checking (future)
- arbitrage_engine.py: Main arbitrage detection and execution logic

Usage:
------
    from cex import RealTriangularArbitrage

    engine = RealTriangularArbitrage(exchange_name="binanceus", trading_mode="paper")
    await engine.run_trading_session(max_trades=100)

Migration Status:
-----------------
Phase 1 (COMPLETE): Module structure created
Phase 2 (IN PROGRESS): Constants extracted
Phase 3 (PENDING): Balance tracker extraction
Phase 4 (PENDING): Order executor extraction
Phase 5 (PENDING): Main engine refactoring

Note: trading_arbitrage.py remains the primary entry point until full migration is complete.
"""

# Re-export the main class for backward compatibility
# TODO: Import from cex.arbitrage_engine once refactoring is complete
try:
    from trading_arbitrage import RealTriangularArbitrage
except ImportError:
    # During transition, this is expected
    RealTriangularArbitrage = None

__all__ = ["RealTriangularArbitrage"]
__version__ = "0.1.0-refactoring"
