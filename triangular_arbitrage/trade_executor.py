"""
Trade Execution Engine for Triangular Arbitrage.

This module provides high-level trade execution functions for calculating and executing
triangular arbitrage opportunities. It handles profit calculations, risk assessments,
and coordinates with the core execution engine.

Key Components:
    - Arbitrage profit calculation with real market data
    - Trade execution orchestration
    - Risk-aware execution with position limits
    - Integration with multiple execution modes (live/paper/backtest)
"""

import asyncio
import logging
from typing import Callable, List

from .execution_engine import StrategyExecutionEngine, ConfigurationManager, CycleState
from .utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Trade-completion callback registry
# ---------------------------------------------------------------------------
# Zero-argument callables registered here are invoked once per completed trade,
# regardless of whether execution went through execute_cycle() or directly
# through RealTriangularArbitrage.run_trading_session().  Exceptions raised by
# callbacks are swallowed so they cannot abort the trade loop.

_trade_callbacks: List[Callable[[], None]] = []


def register_trade_callback(fn: Callable[[], None]) -> None:
    """Register a callable to be invoked on each successfully completed trade."""
    _trade_callbacks.append(fn)


def _fire_trade_callbacks() -> None:
    """Invoke all registered trade-completion callbacks."""
    for fn in _trade_callbacks:
        try:
            fn()
        except Exception as exc:
            logger.warning("Trade callback %r raised: %s", fn, exc)


async def calculate_arbitrage_profit(exchange, cycle, initial_amount, min_profit_bps=0):
    """
    Calculate the potential profit from a triangular arbitrage cycle.

    Simulates execution of all three legs of the arbitrage cycle using current
    market prices to determine profitability before actual trade execution.

    Args:
        exchange: Exchange adapter instance for market data and trading
        cycle: List of three currencies forming the arbitrage cycle (e.g., ['BTC', 'ETH', 'USDT'])
        initial_amount: Starting amount in the first currency of the cycle
        min_profit_bps: Minimum profit threshold in basis points (default: 0)

    Returns:
        tuple: (final_amount, profit_bps, is_profitable)
            - final_amount (float): Final amount after completing the cycle
            - profit_bps (float): Profit in basis points (10000 bps = 100%)
            - is_profitable (bool): Whether the cycle meets minimum profit threshold

    Raises:
        Exception: If market data is unavailable or calculation fails
    """
    try:
        from_currency = cycle[0]
        amount = initial_amount
        trade_path = cycle + [cycle[0]]
        markets = await exchange.load_markets()

        # Execute each leg of the arbitrage cycle
        for i in range(len(trade_path) - 1):
            to_currency = trade_path[i + 1]

            # Determine the correct trading pair and order direction
            # We need to convert from_currency to to_currency, so:
            # - If TO/FROM pair exists, we BUY (spend FROM to get TO)
            # - If FROM/TO pair exists, we SELL (sell FROM to get TO)
            market_symbol_forward = f"{to_currency}/{from_currency}"  # e.g., BTC/USDT
            market_symbol_backward = f"{from_currency}/{to_currency}"  # e.g., USDT/BTC

            market = None
            order_side = None

            if market_symbol_forward in markets:
                # Buy TO currency with FROM currency (e.g., buy BTC with USDT)
                market = markets[market_symbol_forward]
                order_side = "buy"
                market_symbol = market_symbol_forward
            elif market_symbol_backward in markets:
                # Sell FROM currency to get TO currency (e.g., sell USDT for BTC)
                market = markets[market_symbol_backward]
                order_side = "sell"
                market_symbol = market_symbol_backward
            else:
                logger.warning(f"No market found for {from_currency} -> {to_currency}")
                return initial_amount, -10000, False  # Return large negative profit

            # Get current market price
            try:
                ticker = await exchange.fetch_ticker(market_symbol)
                price = ticker["last"]

                if order_side == "buy":
                    # Buying to_currency with from_currency
                    # Account for fees (assume 0.1% fee)
                    amount = (amount / price) * 0.999
                else:
                    # Selling from_currency for to_currency
                    # Account for fees (assume 0.1% fee)
                    amount = (amount * price) * 0.999

            except Exception as e:
                logger.warning(f"Failed to fetch ticker for {market_symbol}: {e}")
                return initial_amount, -10000, False

            from_currency = to_currency

        # Calculate profit
        final_amount = amount
        profit = final_amount - initial_amount
        profit_bps = (profit / initial_amount) * 10000  # basis points

        is_profitable = profit_bps >= min_profit_bps

        logger.info(
            f"Arbitrage calculation: {initial_amount:.6f} -> {final_amount:.6f} ({profit_bps:.1f} bps)"
        )

        return final_amount, profit_bps, is_profitable

    except Exception as e:
        logger.error(f"Error calculating arbitrage profit: {e}")
        return initial_amount, -10000, False


async def pre_trade_check(exchange, cycle, initial_amount):
    """
    Simulates the trade cycle to check if each step meets the minimum
    order size and cost requirements before executing any real trades.
    """
    print("\n--- RUNNING PRE-TRADE VALIDATION ---")

    from_currency = cycle[0]
    amount = initial_amount
    trade_path = cycle + [cycle[0]]
    markets = await exchange.load_markets()

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
            print(
                f"  -> Validation Error: Could not find a valid market for {from_currency} -> {to_currency}"
            )
            return False

        min_order_amount = market.get("limits", {}).get("amount", {}).get("min")
        min_order_cost = market.get("limits", {}).get("cost", {}).get("min")

        # Check if the current amount is sufficient for this step
        if order_side == "sell" and min_order_amount and amount < min_order_amount:
            print(
                f"  -> Validation Error: Order amount for {from_currency} -> {to_currency} is too small."
            )
            print(
                f"     Minimum is {min_order_amount} {market['base']}, but you are trying to trade {amount:.8f}."
            )
            return False

        if order_side == "buy" and min_order_cost:
            # For a BUY, the 'amount' is in the QUOTE currency. We need to check it against min_order_cost.
            if amount < min_order_cost:
                print(
                    f"  -> Validation Error: Order value for {from_currency} -> {to_currency} is too small."
                )
                print(
                    f"     Minimum is {min_order_cost} {market['quote']}, but your order is only worth {amount:.8f} {market['quote']}."
                )
                return False

        # Estimate the amount for the *next* step in the cycle
        try:
            ticker = await exchange.fetch_ticker(market["symbol"])
            price = ticker["last"]
            if order_side == "buy":
                amount = (amount / price) * 0.999  # a little slippage
            else:  # sell
                amount = (amount * price) * 0.999  # a little slippage
        except Exception as e:
            print(
                f"  -> Validation Warning: Could not fetch ticker for simulation. Skipping checks for this step. Details: {e}"
            )

        from_currency = to_currency

    print("  -> Validation successful. All trade steps meet minimum requirements.")
    return True


async def execute_cycle_legacy(
    exchange, cycle, initial_amount, is_dry_run=False, min_profit_bps=7
):
    """
    Legacy execution function for backward compatibility.
    Used only for dry runs now. Live trades use the new engine.
    """
    # First check if the arbitrage opportunity is profitable
    final_amount, profit_bps, is_profitable = await calculate_arbitrage_profit(
        exchange, cycle, initial_amount, min_profit_bps
    )

    print(f"\n--- ARBITRAGE OPPORTUNITY ANALYSIS ---")
    print(f"Cycle: {' -> '.join(cycle + [cycle[0]])}")
    print(f"Expected result: {initial_amount:.6f} -> {final_amount:.6f}")
    print(f"Profit: {profit_bps:.1f} basis points")
    print(f"Minimum required: {min_profit_bps} basis points")

    if not is_profitable:
        print(f"\n--- OPPORTUNITY REJECTED: Not profitable enough ---")
        print(f"This cycle would lose money or not meet minimum profit threshold.")
        return

    print(f"\n--- PROFITABLE OPPORTUNITY FOUND ---")

    # Run pre-trade validation for order sizes
    is_valid = await pre_trade_check(exchange, cycle, initial_amount)
    if not is_valid:
        print("\n--- TRADE CYCLE HALTED DUE TO VALIDATION FAILURE ---")
        return

    if is_dry_run:
        print("\n--- INITIATING DRY RUN ---")
    print("\n--- ATTEMPTING TO EXECUTE TRADE CYCLE ---")
    print("WARNING: Using market orders. Slippage may occur.")

    from_currency = cycle[0]
    amount = initial_amount

    trade_path = cycle + [cycle[0]]
    markets = await exchange.load_markets()

    for i in range(len(trade_path) - 1):
        to_currency = trade_path[i + 1]

        print("-" * 20)
        print(f"Step {i+1}: Trading {from_currency} -> {to_currency}")

        try:
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
                # This check is now redundant due to pre-trade validation, but good for safety
                print(
                    f"Error: Could not find a valid market for {from_currency} -> {to_currency}"
                )
                return

            order = None
            if is_dry_run:
                print(
                    f"DRY RUN: Would execute {order_side.upper()} order on {market['symbol']} for {amount:.8f} {from_currency}"
                )
                ticker = await exchange.fetch_ticker(market["symbol"])
                price = ticker["last"]
                if order_side == "buy":
                    amount = (amount / price) * 0.999
                else:  # sell
                    amount = (amount * price) * 0.999
            else:
                # --- LIVE TRADING ---
                if order_side == "buy":
                    print(
                        f"Placing MARKET BUY order for {to_currency} using {amount:.8f} {from_currency}"
                    )
                    order = await exchange.create_market_buy_order(
                        market["symbol"], amount
                    )
                elif order_side == "sell":
                    print(
                        f"Placing MARKET SELL order for {amount:.8f} {from_currency} to get {to_currency}"
                    )
                    order = await exchange.create_market_sell_order(
                        market["symbol"], amount
                    )

                print("Order placed. Fetching trade details to confirm...")

                final_order_details = None
                for _ in range(5):
                    trades = await exchange.fetch_my_trades(market["symbol"], limit=1)
                    if trades and trades[0]["order"] == order["id"]:
                        final_order_details = trades[0]
                        break
                    await asyncio.sleep(1)

                if not final_order_details:
                    print(
                        "Error: Could not fetch final trade details after placing order. Halting cycle."
                    )
                    return

                if order_side == "buy":
                    amount = float(final_order_details["amount"])
                else:  # sell
                    amount = float(final_order_details["cost"])

                print("Trade confirmed successfully.")

            from_currency = to_currency

        except Exception as e:
            print(f"An error occurred during trade execution: {e}")
            return

    print("\n--- TRADE CYCLE EXECUTION ATTEMPT COMPLETE ---")
    print(f"Finished with approximately {amount:.8f} {from_currency}")


async def execute_cycle(
    exchange, cycle, initial_amount, is_dry_run=False, strategy_config=None
):
    """
    Enhanced execution function using the new robust engine.
    Falls back to legacy for dry runs or if no config is provided.
    """
    if is_dry_run:
        # Use legacy function for dry runs
        return await execute_cycle_legacy(exchange, cycle, initial_amount, is_dry_run)

    # If no config provided, create a default one
    if not strategy_config:
        strategy_config = {
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
            "logging": {"level": "INFO"},
        }

    # Configure logging
    log_level = strategy_config.get("logging", {}).get("level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Use the new engine
    engine = StrategyExecutionEngine(exchange, strategy_config)

    # Check for and recover any active cycles first
    await engine.recover_active_cycles()

    # Execute the new cycle
    cycle_info = await engine.execute_cycle(cycle, initial_amount)

    # Log results
    if cycle_info.state == CycleState.COMPLETED:
        _fire_trade_callbacks()
        print(f"\n--- CYCLE COMPLETED SUCCESSFULLY ---")
        print(f"Initial Amount: {cycle_info.initial_amount:.8f} {cycle_info.cycle[0]}")
        print(
            f"Final Amount: {cycle_info.current_amount:.8f} {cycle_info.current_currency}"
        )
        print(f"Profit/Loss: {cycle_info.profit_loss:.8f}")
        print(
            f"Execution Time: {cycle_info.end_time - cycle_info.start_time:.2f} seconds"
        )
    else:
        print(f"\n--- CYCLE FAILED ---")
        print(f"Error: {cycle_info.error_message}")
        print(f"Final State: {cycle_info.state.value}")
        print(
            f"Current Holdings: {cycle_info.current_amount:.8f} {cycle_info.current_currency}"
        )

        if cycle_info.metadata.get("panic_sell_executed"):
            print(
                f"Panic Sell Executed: {cycle_info.metadata['panic_sell_amount']:.8f} {cycle_info.metadata['panic_sell_currency']}"
            )

    return cycle_info


async def execute_strategy(
    exchange, strategy_path: str, cycles: List[List[str]], amounts: List[float]
):
    """
    Execute multiple cycles using a specific strategy configuration.

    Args:
        exchange: The exchange connection
        strategy_path: Path to the strategy YAML file
        cycles: List of cycles to execute
        amounts: List of amounts for each cycle
    """
    # Load strategy configuration
    config_manager = ConfigurationManager()
    strategy_config = config_manager.load_strategy(strategy_path)

    print(f"\nExecuting strategy: {strategy_config['name']}")
    print(f"Exchange: {strategy_config['exchange']}")
    print(f"Min Profit: {strategy_config['min_profit_bps']} bps")
    print(f"Max Slippage: {strategy_config['max_slippage_bps']} bps")

    # Create engine
    engine = StrategyExecutionEngine(exchange, strategy_config)

    # Recover any active cycles
    await engine.recover_active_cycles()

    # Execute each cycle
    results = []
    for cycle, amount in zip(cycles, amounts):
        print(f"\nExecuting cycle: {' -> '.join(cycle)} -> {cycle[0]}")
        cycle_info = await engine.execute_cycle(cycle, amount)
        if cycle_info.state == CycleState.COMPLETED:
            _fire_trade_callbacks()
        results.append(cycle_info)

        # Check if we should stop due to consecutive losses
        if engine.consecutive_losses >= engine.max_consecutive_losses:
            print(
                f"\nStopping execution: {engine.consecutive_losses} consecutive losses"
            )
            break

    # Summary
    completed = [r for r in results if r.state == CycleState.COMPLETED]
    failed = [r for r in results if r.state == CycleState.FAILED]
    total_profit = sum(r.profit_loss or 0 for r in completed)

    print(f"\n--- STRATEGY EXECUTION SUMMARY ---")
    print(f"Total Cycles: {len(results)}")
    print(f"Completed: {len(completed)}")
    print(f"Failed: {len(failed)}")
    print(f"Total Profit/Loss: {total_profit:.8f}")

    return results
