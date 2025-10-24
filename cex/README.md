# CEX (Centralized Exchange) Arbitrage Module

**Status:** 🚧 **Refactoring In Progress** (Phase 1 Complete)

This module is part of an ongoing refactoring effort to break down the monolithic `trading_arbitrage.py` (2,920 lines) into smaller, more maintainable components.

## 📂 Module Structure

```
cex/
├── __init__.py           # Module exports and version info
├── constants.py          # ✅ Exchange fees, limits, configuration (COMPLETE)
├── balance_tracker.py    # 📅 Balance and equity tracking (PLANNED)
├── order_executor.py     # 📅 Order execution and depth checking (PLANNED)
├── arbitrage_engine.py   # 📅 Main arbitrage logic (PLANNED)
└── README.md            # This file
```

## 🎯 Refactoring Goals

1. **Improve Maintainability**: Break 2,920 lines into focused modules (~500-700 lines each)
2. **Enable Testing**: Isolated components are easier to unit test
3. **Reusability**: Shared utilities can be used across different strategies
4. **Clarity**: Clear separation of concerns (config, execution, tracking)

## ✅ Phase 1: Foundation (COMPLETE)

- [x] Create `cex/` module directory
- [x] Extract constants to `constants.py`
- [x] Create `TradingConfig` class for centralized configuration
- [x] Add module documentation

## 📅 Phase 2: Balance Tracking (PLANNED)

Extract balance and equity tracking logic:
- `fetch_balances()` → `BalanceTracker.fetch()`
- `get_cash()` → `BalanceTracker.get_cash()`
- `get_asset_value()` → `BalanceTracker.get_asset_value()`
- `_equity_usd()` → `BalanceTracker.calculate_equity()`
- Paper trading balance management

**Estimated Effort:** 4-6 hours

## 📅 Phase 3: Order Execution (PLANNED)

Extract order execution and depth checking:
- `execute_trade()` → `OrderExecutor.execute()`
- `check_order_book_depth()` → `OrderExecutor.check_depth()`
- `should_use_maker()` → `OrderExecutor.should_use_maker()`
- `panic_sell()` → `OrderExecutor.panic_sell()`

**Estimated Effort:** 6-8 hours

## 📅 Phase 4: Main Engine (PLANNED)

Refactor main arbitrage logic:
- `find_arbitrage_opportunities()` → `ArbitrageEngine.find_opportunities()`
- `execute_arbitrage_cycle()` → `ArbitrageEngine.execute_cycle()`
- `estimate_cycle_slippage()` → `ArbitrageEngine.estimate_slippage()`
- Graph building and caching logic

**Estimated Effort:** 8-10 hours

## 📅 Phase 5: Testing & Migration (PLANNED)

- Write comprehensive unit tests for each module
- Integrate modules back into main engine
- Deprecate `trading_arbitrage.py`
- Update all imports across codebase

**Estimated Effort:** 6-8 hours

---

## 🔧 Current Usage

During the refactoring period, the original `trading_arbitrage.py` remains the primary entry point:

```python
# Current (backward compatible)
from trading_arbitrage import RealTriangularArbitrage

engine = RealTriangularArbitrage(
    exchange_name="binanceus",
    trading_mode="paper"
)
await engine.run_trading_session()
```

## 🎯 Future Usage (After Refactoring)

```python
# Future (modular approach)
from cex import RealTriangularArbitrage
from cex.constants import TradingConfig

config = TradingConfig()
config.min_profit_threshold = 0.30  # Override defaults

engine = RealTriangularArbitrage(
    exchange_name="binanceus",
    trading_mode="paper",
    config=config
)
await engine.run_trading_session()
```

## 📊 Migration Timeline

| Phase | Description | Status | ETA |
|-------|-------------|--------|-----|
| Phase 1 | Foundation & Constants | ✅ Complete | Done |
| Phase 2 | Balance Tracking | 📅 Planned | TBD |
| Phase 3 | Order Execution | 📅 Planned | TBD |
| Phase 4 | Main Engine | 📅 Planned | TBD |
| Phase 5 | Testing & Migration | 📅 Planned | TBD |

**Total Estimated Effort:** 24-32 hours
**Priority:** Medium (improves maintainability, not critical for functionality)

## 🤝 Contributing

When adding new features to the CEX arbitrage system:

1. **For new features:** Add to appropriate module (balance_tracker, order_executor, etc.)
2. **For bug fixes:** Fix in `trading_arbitrage.py` first, then backport during refactoring
3. **For configuration:** Add to `constants.py` with environment variable support

## 📖 Related Documentation

- [Main README](../README.md) - Project overview
- [Trading Setup Guide](../TRADING_SETUP.md) - Getting started with trading
- [Execution Engine Docs](../docs/EXECUTION_ENGINE_DOCS.md) - Advanced execution details

---

**Note:** This is a living document and will be updated as the refactoring progresses.

*Last Updated: 2025-01-16*
