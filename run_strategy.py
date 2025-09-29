#!/usr/bin/env python3
"""
Enhanced Strategy Runner - Execute trading strategies with multi-mode support

Supports live trading, paper trading, and backtesting execution modes.

Usage:
    # Live trading
    python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode live

    # Paper trading
    python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode paper

    # Backtesting (use backtests/run_backtest.py for full backtesting)
    python run_strategy.py --strategy configs/strategies/strategy_1.yaml --mode backtest
"""

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path

import ccxt.async_support as ccxt
from dotenv import load_dotenv

from coinbase_adapter import CoinbaseAdvancedAdapter
from triangular_arbitrage.config_schema import validate_strategy_config
from triangular_arbitrage.exchanges import (
    BacktestExchange,
    ExchangeAdapter,
    LiveExchangeAdapter,
    PaperExchange,
)
from triangular_arbitrage.execution_engine import (
    ConfigurationManager,
    CycleState,
    StateManager,
    StrategyExecutionEngine,
)


class MockCoinbaseAdapter:
    """Mock Coinbase adapter for paper trading without credentials"""

    def __init__(self):
        self.id = "coinbase_mock"
        self.markets = {}

    async def load_markets(self):
        """Load mock markets"""
        return {
            "BTC/USD": {
                "symbol": "BTC/USD",
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 10}},
            },
            "ETH/USD": {
                "symbol": "ETH/USD",
                "limits": {"amount": {"min": 0.01}, "cost": {"min": 10}},
            },
            "XLM/USD": {
                "symbol": "XLM/USD",
                "limits": {"amount": {"min": 1}, "cost": {"min": 1}},
            },
            "DASH/USD": {
                "symbol": "DASH/USD",
                "limits": {"amount": {"min": 0.01}, "cost": {"min": 1}},
            },
            "MASK/USD": {
                "symbol": "MASK/USD",
                "limits": {"amount": {"min": 0.1}, "cost": {"min": 1}},
            },
            "COMP/USD": {
                "symbol": "COMP/USD",
                "limits": {"amount": {"min": 0.01}, "cost": {"min": 1}},
            },
            "USDT/USD": {
                "symbol": "USDT/USD",
                "limits": {"amount": {"min": 1}, "cost": {"min": 1}},
            },
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 10}},
            },
            "XLM/USDT": {
                "symbol": "XLM/USDT",
                "limits": {"amount": {"min": 1}, "cost": {"min": 1}},
            },
            "XLM/BTC": {
                "symbol": "XLM/BTC",
                "limits": {"amount": {"min": 1}, "cost": {"min": 0.001}},
            },
            "MASK/USDT": {
                "symbol": "MASK/USDT",
                "limits": {"amount": {"min": 0.1}, "cost": {"min": 1}},
            },
            "DASH/BTC": {
                "symbol": "DASH/BTC",
                "limits": {"amount": {"min": 0.01}, "cost": {"min": 0.001}},
            },
        }

    async def fetch_ticker(self, symbol):
        """Return mock ticker data"""
        import random
        import time

        # Base prices
        base_prices = {
            "BTC/USD": 50000.0,
            "ETH/USD": 3000.0,
            "XLM/USD": 0.12,
            "DASH/USD": 35.0,
            "MASK/USD": 2.8,
            "COMP/USD": 55.0,
            "USDT/USD": 1.0,
            "BTC/USDT": 50000.0,
            "XLM/USDT": 0.12,
            "XLM/BTC": 0.0000024,
            "MASK/USDT": 2.8,
            "DASH/BTC": 0.0007,
        }

        base_price = base_prices.get(symbol, 1.0)
        variation = random.uniform(-0.005, 0.005)  # ±0.5% variation
        last_price = base_price * (1 + variation)

        spread = last_price * 0.001  # 0.1% spread
        bid = last_price - spread / 2
        ask = last_price + spread / 2

        return {
            "symbol": symbol,
            "last": last_price,
            "bid": bid,
            "ask": ask,
            "high": last_price * 1.01,
            "low": last_price * 0.99,
            "volume": 1000.0,
            "quoteVolume": last_price * 1000.0,
            "timestamp": int(time.time() * 1000),
            "datetime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }


def load_cycles_from_csv(csv_path: str):
    """Load trading cycles from CSV file"""
    cycles = []

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"Cycles file not found: {csv_path}")

    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        # Skip header if present
        header = next(reader, None)

        for row in reader:
            if row and len(row) >= 3:
                # Assume format: currency1,currency2,currency3[,profit]
                cycle = row[:3]
                cycles.append(cycle)

    return cycles


def create_exchange_adapter(
    strategy_config: dict, execution_mode: str, args
) -> ExchangeAdapter:
    """Create appropriate exchange adapter based on execution mode"""

    if execution_mode == "backtest":
        # Use BacktestExchange for backtesting
        backtest_config = strategy_config.get("execution", {}).get("backtest", {})
        backtest_config.update(
            {
                "execution_mode": "backtest",
                "data_file": args.data_file
                or backtest_config.get("data_file", "data/backtests/sample_feed.csv"),
                "start_time": args.start_time,
                "end_time": args.end_time,
                "random_seed": args.random_seed
                or backtest_config.get("random_seed", 42),
                "time_acceleration": args.time_acceleration
                or backtest_config.get("time_acceleration", 1.0),
            }
        )
        return BacktestExchange(backtest_config)

    elif execution_mode == "paper":
        # Create live exchange first, then wrap with PaperExchange
        live_exchange = create_live_exchange(strategy_config, args)

        paper_config = strategy_config.get("execution", {}).get("paper", {})
        paper_config.update(
            {
                "execution_mode": "paper",
                "random_seed": args.random_seed or paper_config.get("random_seed", 42),
            }
        )

        return PaperExchange(live_exchange, paper_config)

    else:  # live mode
        live_exchange = create_live_exchange(strategy_config, args)
        return LiveExchangeAdapter(live_exchange, {"execution_mode": "live"})


def create_live_exchange(strategy_config: dict, args):
    """Create live exchange instance"""
    exchange_name = strategy_config["exchange"]
    api_key = os.getenv("EXCHANGE_API_KEY") or args.api_key
    api_secret = os.getenv("EXCHANGE_API_SECRET") or args.api_secret

    if not api_key or not api_secret:
        if args.mode == "live":
            raise ValueError("API credentials required for live trading mode")
        # For paper mode, we still need credentials to get live market data
        logging.warning("No API credentials provided - using demo mode")

    # Use Coinbase Advanced Trading API for coinbase exchange
    if exchange_name == "coinbase":
        if not api_key or not api_secret:
            if args.mode == "paper":
                # For paper mode, create a mock exchange for market data
                return MockCoinbaseAdapter()
            else:
                raise ValueError("Coinbase requires API credentials for live trading")
        return CoinbaseAdvancedAdapter(
            api_key, api_secret, sandbox=(args.mode != "live")
        )
    else:
        exchange_class = getattr(ccxt, exchange_name)

        # Configure exchange with proper credentials
        exchange_config = {
            "enableRateLimit": True,
            "options": {"createMarketBuyOrderRequiresPrice": False},
        }

        # Add credentials if available
        if api_key and api_secret:
            exchange_config["apiKey"] = api_key
            exchange_config["secret"] = api_secret
            # For Coinbase APIs, use sandbox for non-live modes
            if exchange_name == "coinbasepro" and args.mode != "live":
                exchange_config["sandbox"] = True

        return exchange_class(exchange_config)


async def main():
    parser = argparse.ArgumentParser(
        description="Execute trading strategy with multi-mode support"
    )
    parser.add_argument(
        "--strategy", required=True, help="Path to strategy YAML configuration file"
    )
    parser.add_argument(
        "--mode",
        choices=["live", "paper", "backtest"],
        help="Execution mode (overrides YAML config)",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Recover and complete any active cycles before starting new ones",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume with persisted cooldown state from previous run",
    )
    parser.add_argument(
        "--cycles", type=int, default=1, help="Number of cycles to execute (default: 1)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="DEPRECATED: Use --mode paper instead"
    )

    # Mode-specific arguments
    parser.add_argument("--api-key", help="Exchange API key (overrides env var)")
    parser.add_argument("--api-secret", help="Exchange API secret (overrides env var)")
    parser.add_argument(
        "--random-seed", type=int, help="Random seed for paper/backtest modes"
    )

    # Backtest-specific arguments
    parser.add_argument("--data-file", help="Backtest data file path")
    parser.add_argument(
        "--start-time", type=float, help="Backtest start time (Unix timestamp)"
    )
    parser.add_argument(
        "--end-time", type=float, help="Backtest end time (Unix timestamp)"
    )
    parser.add_argument(
        "--time-acceleration", type=float, help="Time acceleration factor"
    )

    # Paper trading arguments
    parser.add_argument(
        "--paper-balance",
        action="append",
        nargs=2,
        metavar=("CURRENCY", "AMOUNT"),
        help="Set paper trading balance (can be used multiple times)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Handle deprecated dry-run flag
    if args.dry_run:
        args.mode = "paper"

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Handle deprecated dry-run warning
    if args.dry_run:
        logger.warning("--dry-run is deprecated, using --mode paper instead")

    # Load environment variables
    load_dotenv()

    # Load strategy configuration
    config_manager = ConfigurationManager()

    try:
        strategy_config = config_manager.load_strategy(args.strategy)
    except Exception as e:
        logger.error(f"Failed to load strategy: {e}")
        return 1

    # Validate configuration schema
    try:
        validated_config = validate_strategy_config(strategy_config)
        logger.info(f"✓ Configuration validation passed")

        # Log any warnings identified during validation
        warnings = []
        if validated_config.min_profit_bps <= 5:
            warnings.append(
                "min_profit_bps is very low (≤5 bps) - may result in unprofitable trades"
            )
        if validated_config.max_slippage_bps > validated_config.min_profit_bps:
            warnings.append(
                f"max_slippage_bps ({validated_config.max_slippage_bps}) > min_profit_bps ({validated_config.min_profit_bps}) - may result in losses"
            )

        for warning in warnings:
            logger.warning(f"⚠️  {warning}")

    except Exception as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        logger.error(
            "Please check your configuration file and fix the validation errors"
        )
        logger.error(
            f"Use 'python tools/validate_config.py {args.strategy}' for detailed validation information"
        )
        return 1

    logger.info(f"Loaded strategy: {strategy_config['name']}")

    # Determine execution mode (CLI args override YAML config)
    execution_mode = args.mode
    if not execution_mode:
        execution_mode = strategy_config.get("execution", {}).get("mode", "live")

    logger.info(f"🚀 Running in {execution_mode.upper()} mode")

    # Override paper balance if specified
    if args.paper_balance and execution_mode == "paper":
        paper_config = strategy_config.setdefault("execution", {}).setdefault(
            "paper", {}
        )
        initial_balances = paper_config.setdefault("initial_balances", {})
        for currency, amount in args.paper_balance:
            initial_balances[currency] = float(amount)
            logger.info(f"Set paper balance: {currency} = {amount}")

    # Create appropriate exchange adapter
    try:
        exchange = create_exchange_adapter(strategy_config, execution_mode, args)
    except Exception as e:
        logger.error(f"Failed to create exchange adapter: {e}")
        return 1

    try:
        # Initialize exchange
        await exchange.initialize()
        logger.info(
            f"✅ Connected to {strategy_config['exchange']} in {execution_mode} mode"
        )

        # Create execution engine with exchange adapter
        engine = StrategyExecutionEngine(exchange, strategy_config)

        # Initialize async components
        await engine.initialize()

        # Load cooldown state if resuming (not applicable for backtest mode)
        if (
            args.resume
            and execution_mode != "backtest"
            and hasattr(engine, "risk_control_manager")
            and engine.risk_control_manager
        ):
            restored = engine.risk_control_manager.load_cooldowns()
            if restored > 0:
                logger.info(
                    f"✓ Resumed with {restored} active cooldowns from previous run"
                )
            else:
                logger.info("No active cooldowns to resume")

        # Handle recovery if requested (not applicable for backtest mode)
        if args.recover and execution_mode != "backtest":
            logger.info("Recovering active cycles...")
            await engine.recover_active_cycles()

        # Load cycles from CSV if specified
        cycles_file = strategy_config.get("trading_pairs_file")
        if not cycles_file:
            logger.error("No trading_pairs_file specified in strategy")
            return 1

        cycles = load_cycles_from_csv(cycles_file)
        logger.info(f"Loaded {len(cycles)} cycles from {cycles_file}")

        if not cycles:
            logger.error("No cycles found in CSV file")
            return 1

        # Get account balance
        balances = await exchange.fetch_balance()
        logger.info(
            f"Current balances: {[(k, v) for k, v in balances.items() if v > 0.001][:5]}"
        )

        # Execute cycles
        min_profit_bps = strategy_config.get("min_profit_bps", 7)
        max_executions = args.cycles

        logger.info(f"⚡ EXECUTION MODE: {execution_mode.upper()}")
        logger.info(f"🎯 Will execute up to {max_executions} cycles")
        logger.info(f"💰 Minimum profit threshold: {min_profit_bps} basis points")

        executed = 0
        scanned_count = 0

        for cycle in cycles:
            # Stop if we've executed enough trades
            if executed >= max_executions:
                logger.info(f"🛑 Maximum executions reached ({max_executions})")
                break

            scanned_count += 1
            start_currency = cycle[0]
            available = balances.get(start_currency, 0)

            if available <= 0:
                continue

            # Calculate amount for this cycle
            capital_config = strategy_config["capital_allocation"]
            if capital_config["mode"] == "fixed_fraction":
                amount = available * capital_config["fraction"]
            elif capital_config["mode"] == "fixed_amount":
                amount = min(capital_config.get("amount", available), available)
            else:
                amount = available * 0.1  # Conservative default

            # Skip if amount too small
            if amount < 0.001:
                continue

            cycle_name = " -> ".join(cycle + [cycle[0]])
            logger.info(
                f"[{scanned_count:3d}/{len(cycles)}] Testing cycle: {cycle_name}"
            )
            logger.info(f"Amount: {amount:.6f} {start_currency}")

            try:
                # Execute cycle directly with the new engine
                cycle_info = await engine.execute_cycle(cycle, amount)

                if cycle_info.state == CycleState.COMPLETED:
                    # Only count as executed if we're back to the original currency
                    if cycle_info.current_currency == cycle_info.cycle[0]:
                        executed += 1
                        pnl = cycle_info.profit_loss or 0.0
                        pnl_bps = (
                            (pnl / cycle_info.initial_amount) * 10000
                            if cycle_info.initial_amount > 0
                            else 0.0
                        )
                        logger.info(
                            f"✅ Cycle completed: PnL {pnl:+.6f} ({pnl_bps:+.1f} bps)"
                        )
                    else:
                        logger.error(
                            f"❌ Cycle incomplete: ended in {cycle_info.current_currency} instead of {cycle_info.cycle[0]}"
                        )

                    # Update balances for next iteration
                    balances = await exchange.fetch_balance()

                elif cycle_info.state == CycleState.PARTIALLY_FILLED:
                    logger.info(f"⚠️  Cycle partial: {cycle_info.error_message}")
                else:
                    logger.info(f"❌ Cycle failed: {cycle_info.error_message}")

                # Check for consecutive losses (not applicable in backtest mode)
                if execution_mode != "backtest" and hasattr(
                    engine, "consecutive_losses"
                ):
                    if engine.consecutive_losses >= engine.max_consecutive_losses:
                        logger.warning(
                            f"🛑 Stopping: {engine.consecutive_losses} consecutive losses"
                        )
                        break

                # Show progress every 25 cycles
                if scanned_count % 25 == 0:
                    logger.info(
                        f"📊 Progress: {scanned_count}/{len(cycles)} scanned, {executed} executed"
                    )

            except Exception as e:
                logger.warning(f"Failed to execute cycle {cycle}: {e}")

        # Final summary
        logger.info(f"\n🎯 EXECUTION COMPLETE!")
        logger.info(f"📊 Tested: {scanned_count}/{len(cycles)} cycles")
        logger.info(f"💰 Executed: {executed} cycles")

        # Show execution metrics if available
        if hasattr(exchange, "get_execution_metrics"):
            metrics = await exchange.get_execution_metrics()
            if metrics:
                logger.info(f"📈 Execution metrics:")
                if "fill_rate" in metrics:
                    logger.info(f"   Fill rate: {metrics['fill_rate']:.1%}")
                if "average_slippage_bps" in metrics:
                    logger.info(
                        f"   Avg slippage: {metrics['average_slippage_bps']:.1f} bps"
                    )
                if "total_fees_paid" in metrics:
                    logger.info(f"   Total fees: {metrics['total_fees_paid']:.6f}")

        # Final balances
        final_balances = await exchange.fetch_balance()
        logger.info(
            f"Final balances: {[(k, v) for k, v in final_balances.items() if v > 0.001]}"
        )

        # Cleanup old cycle records (older than 7 days) - skip for backtest
        if execution_mode != "backtest":
            state_manager = StateManager()
            await state_manager.cleanup_old_cycles(days=7)

            # Save cooldown state for resume
            if hasattr(engine, "risk_control_manager") and engine.risk_control_manager:
                try:
                    engine.risk_control_manager.save_cooldowns()
                except Exception as e:
                    logger.warning(f"Failed to save cooldown state: {e}")

    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        return 1
    finally:
        await exchange.close()

    return 0


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
