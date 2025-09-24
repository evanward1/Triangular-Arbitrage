#!/usr/bin/env python3
"""
Strategy Runner - Execute trading strategies using configuration files

Usage:
    python run_strategy.py --strategy configs/strategies/strategy_1.yaml [--recover]
"""

import asyncio
import argparse
import os
import sys
import csv
from pathlib import Path
from dotenv import load_dotenv
import ccxt.async_support as ccxt
import logging

from triangular_arbitrage.execution_engine import (
    StrategyExecutionEngine,
    ConfigurationManager,
    StateManager,
    CycleState
)


def load_cycles_from_csv(csv_path: str):
    """Load trading cycles from CSV file"""
    cycles = []

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"Cycles file not found: {csv_path}")

    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        # Skip header if present
        header = next(reader, None)

        for row in reader:
            if row and len(row) >= 3:
                # Assume format: currency1,currency2,currency3[,profit]
                cycle = row[:3]
                cycles.append(cycle)

    return cycles


async def main():
    parser = argparse.ArgumentParser(description='Execute trading strategy')
    parser.add_argument(
        '--strategy',
        required=True,
        help='Path to strategy YAML configuration file'
    )
    parser.add_argument(
        '--recover',
        action='store_true',
        help='Recover and complete any active cycles before starting new ones'
    )
    parser.add_argument(
        '--cycles',
        type=int,
        default=1,
        help='Number of cycles to execute (default: 1)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in simulation mode without real trades'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Load environment variables
    load_dotenv()

    # Load strategy configuration
    config_manager = ConfigurationManager()

    try:
        strategy_config = config_manager.load_strategy(args.strategy)
    except Exception as e:
        logger.error(f"Failed to load strategy: {e}")
        return 1

    logger.info(f"Loaded strategy: {strategy_config['name']}")

    # Setup exchange connection
    exchange_name = strategy_config['exchange']
    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")

    if not api_key or not api_secret:
        logger.error("EXCHANGE_API_KEY or EXCHANGE_API_SECRET not found in .env file")
        return 1

    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'createMarketBuyOrderRequiresPrice': False
        }
    })

    try:
        # Load markets
        await exchange.load_markets()
        logger.info(f"Connected to {exchange_name}")

        # Create execution engine
        engine = StrategyExecutionEngine(exchange, strategy_config)

        # Initialize async components
        await engine.initialize()

        # Handle recovery if requested
        if args.recover:
            logger.info("Recovering active cycles...")
            await engine.recover_active_cycles()

        # Load cycles from CSV if specified
        cycles_file = strategy_config.get('trading_pairs_file')
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

        # Execute cycles
        executed = 0
        max_cycles = min(args.cycles, len(cycles))

        for i in range(max_cycles):
            cycle = cycles[i % len(cycles)]

            # Determine starting amount based on capital allocation
            capital_config = strategy_config['capital_allocation']
            start_currency = cycle[0]
            available = balances.get('free', {}).get(start_currency, 0)

            if available <= 0:
                logger.warning(f"No {start_currency} available, skipping cycle")
                continue

            if capital_config['mode'] == 'fixed_fraction':
                amount = available * capital_config['fraction']
            elif capital_config['mode'] == 'fixed_amount':
                amount = min(capital_config.get('amount', available), available)
            else:
                amount = available

            logger.info(
                f"Executing cycle {i+1}/{max_cycles}: "
                f"{' -> '.join(cycle)} -> {cycle[0]}"
            )
            logger.info(f"Amount: {amount:.8f} {start_currency}")

            if args.dry_run:
                logger.info("DRY RUN - Simulating execution")
                # Use the legacy function for dry runs
                from triangular_arbitrage.trade_executor import execute_cycle_legacy
                await execute_cycle_legacy(exchange, cycle, amount, is_dry_run=True)
            else:
                # Execute with the new engine
                cycle_info = await engine.execute_cycle(cycle, amount)

                if cycle_info.state == CycleState.COMPLETED:
                    logger.info(
                        f"Cycle completed. P/L: {cycle_info.profit_loss:.8f}"
                    )
                else:
                    logger.error(
                        f"Cycle failed: {cycle_info.error_message}"
                    )

                # Check for consecutive losses
                if engine.consecutive_losses >= engine.max_consecutive_losses:
                    logger.warning(
                        f"Stopping: {engine.consecutive_losses} consecutive losses"
                    )
                    break

            executed += 1

            # Brief pause between cycles
            if i < max_cycles - 1:
                await asyncio.sleep(2)

        logger.info(f"Executed {executed} cycles")

        # Cleanup old cycle records (older than 7 days)
        state_manager = StateManager()
        state_manager.cleanup_old_cycles(days=7)

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