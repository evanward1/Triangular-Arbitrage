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
from coinbase_adapter import CoinbaseAdvancedAdapter


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
        '--resume',
        action='store_true',
        help='Resume with persisted cooldown state from previous run'
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

    if not args.dry_run and (not api_key or not api_secret):
        logger.error("EXCHANGE_API_KEY or EXCHANGE_API_SECRET not found in .env file")
        return 1

    # Use Coinbase Advanced Trading API for coinbase exchange
    if exchange_name == 'coinbase':
        if not api_key or not api_secret:
            logger.error("Coinbase requires API credentials")
            return 1
        exchange = CoinbaseAdvancedAdapter(api_key, api_secret, sandbox=args.dry_run)
    else:
        exchange_class = getattr(ccxt, exchange_name)

        # Configure exchange with proper credentials
        exchange_config = {
            'enableRateLimit': True,
            'options': {
                'createMarketBuyOrderRequiresPrice': False
            }
        }

        # Add credentials if not in dry-run mode or if required for Coinbase
        if not args.dry_run or exchange_name in ['coinbasepro']:
            if api_key and api_secret:
                exchange_config['apiKey'] = api_key
                exchange_config['secret'] = api_secret
                # For Coinbase APIs, use sandbox for dry-runs
                if exchange_name == 'coinbasepro' and args.dry_run:
                    exchange_config['sandbox'] = True

        exchange = exchange_class(exchange_config)

    try:
        # Load markets
        await exchange.load_markets()
        logger.info(f"Connected to {exchange_name}")

        # Create execution engine
        engine = StrategyExecutionEngine(exchange, strategy_config)

        # Initialize async components
        await engine.initialize()

        # Load cooldown state if resuming
        if args.resume and engine.risk_control_manager:
            restored = engine.risk_control_manager.load_cooldowns()
            if restored > 0:
                logger.info(f"✓ Resumed with {restored} active cooldowns from previous run")
            else:
                logger.info("No active cooldowns to resume")

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

        # Get account balance (skip for dry-runs or use mock data for problematic exchanges)
        if args.dry_run:
            # Mock balances for dry-run testing
            balances = {'free': {'BTC': 1.0, 'ETH': 10.0, 'USDT': 10000.0, 'USDC': 10000.0, 'SOL': 100.0, 'ADA': 1000.0, 'DOT': 100.0, 'AVAX': 50.0, 'LINK': 100.0, 'LTC': 100.0, 'XRP': 1000.0, 'TRX': 10000.0, 'DOGE': 10000.0}}
            logger.info("Using mock balances for dry-run")
        else:
            balances = await exchange.fetch_balance()

        # 🚀 LIGHTNING-FAST ARBITRAGE HUNTING 🚀
        # Execute profitable trades IMMEDIATELY when found (no delays!)
        from triangular_arbitrage.trade_executor import calculate_arbitrage_profit, execute_cycle_legacy
        min_profit_bps = strategy_config.get('min_profit_bps', 7)
        max_executions = args.cycles

        logger.info(f"⚡ LIGHTNING ARBITRAGE MODE: Scanning {len(cycles)} cycles")
        logger.info(f"🎯 Will execute ALL profitable opportunities immediately (max {max_executions})")
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
            available = balances.get('free', {}).get(start_currency, 0)

            if available <= 0:
                continue

            # Calculate amount for this cycle
            capital_config = strategy_config['capital_allocation']
            if capital_config['mode'] == 'fixed_fraction':
                amount = available * capital_config['fraction']
            elif capital_config['mode'] == 'fixed_amount':
                amount = min(capital_config.get('amount', available), available)
            else:
                amount = available

            # Calculate profit for this cycle
            try:
                final_amount, profit_bps, is_profitable = await calculate_arbitrage_profit(
                    exchange, cycle, amount, min_profit_bps
                )

                cycle_name = ' -> '.join(cycle + [cycle[0]])
                profit_status = f"📊 [{scanned_count:3d}/{len(cycles)}] {cycle_name}: {profit_bps:+6.1f} bps"

                # 🔥 EXECUTE IMMEDIATELY IF PROFITABLE 🔥
                if is_profitable:
                    executed += 1
                    logger.info(f"{profit_status} 🔥 PROFITABLE! EXECUTING NOW!")
                    logger.info(f"⚡ Execution #{executed}: {amount:.8f} {start_currency}")

                    if args.dry_run:
                        logger.info("🧪 DRY RUN - Simulating execution")
                        await execute_cycle_legacy(exchange, cycle, amount, is_dry_run=True, min_profit_bps=min_profit_bps)
                    else:
                        # Execute with the new engine
                        cycle_info = await engine.execute_cycle(cycle, amount)

                        if cycle_info.state == CycleState.COMPLETED:
                            logger.info(f"✅ Trade completed. P/L: {cycle_info.profit_loss:.8f}")
                        else:
                            logger.error(f"❌ Trade failed: {cycle_info.error_message}")

                        # Check for consecutive losses
                        if engine.consecutive_losses >= engine.max_consecutive_losses:
                            logger.warning(f"🛑 Stopping: {engine.consecutive_losses} consecutive losses")
                            break

                    logger.info(f"💎 Profit locked in! Moving to next opportunity...\n")

                else:
                    logger.info(f"{profit_status}")  # Show unprofitable result

                # Show progress every 25 cycles
                if scanned_count % 25 == 0:
                    logger.info(f"📊 Progress: {scanned_count}/{len(cycles)} scanned, {executed} profitable executed")

            except Exception as e:
                logger.warning(f"Failed to analyze cycle {cycle}: {e}")

        # Final summary
        logger.info(f"\n🎯 ARBITRAGE HUNT COMPLETE!")
        logger.info(f"📊 Scanned: {scanned_count}/{len(cycles)} cycles")
        logger.info(f"💰 Executed: {executed} profitable trades")

        logger.info(f"Executed {executed} cycles")

        # Cleanup old cycle records (older than 7 days)
        state_manager = StateManager()
        state_manager.cleanup_old_cycles(days=7)

        # Save cooldown state for resume
        if engine.risk_control_manager:
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