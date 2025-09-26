#!/usr/bin/env python3
"""
Deterministic Backtest Runner

Runs triangular arbitrage strategies against historical data with full determinism
and comprehensive reporting. Designed for strategy validation and optimization.
"""

import asyncio
import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from triangular_arbitrage.execution_engine import (
    StrategyExecutionEngine,
    ConfigurationManager,
    StateManager,
    CycleState
)
from triangular_arbitrage.exchanges import BacktestExchange

# Set up logger
logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    Deterministic backtest runner with comprehensive reporting
    """

    def __init__(self, strategy_config: Dict[str, Any], backtest_config: Dict[str, Any]):
        self.strategy_config = strategy_config
        self.backtest_config = backtest_config

        # Override execution mode
        self.strategy_config['execution'] = {'mode': 'backtest'}
        self.strategy_config['execution'].update(backtest_config)

        # Results tracking
        self.results = {
            'backtest_id': f"backtest_{int(time.time())}",
            'strategy_name': strategy_config['name'],
            'start_time': None,
            'end_time': None,
            'wall_clock_duration_seconds': 0.0,
            'simulation_duration_seconds': 0.0,
            'cycles_started': 0,
            'cycles_filled': 0,
            'cycles_partial': 0,
            'cycles_rejected': 0,
            'cycles_canceled_slippage': 0,
            'cycles_canceled_latency': 0,
            'partials_resolved': 0,
            'net_pnl': 0.0,
            'gross_pnl': 0.0,
            'total_fees': 0.0,
            'basis_points_captured': 0.0,
            'average_cycle_duration_ms': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'cycles': [],
            'final_balances': {},
            'execution_metrics': {},
            'configuration': {
                'strategy': strategy_config,
                'backtest': backtest_config
            }
        }

    async def run(self) -> Dict[str, Any]:
        """Run the backtest and return comprehensive results"""

        wall_clock_start = time.time()
        self.results['start_time'] = datetime.now(timezone.utc).isoformat()

        logger.info(f"🚀 Starting backtest: {self.results['backtest_id']}")
        logger.info(f"Strategy: {self.results['strategy_name']}")
        logger.info(f"Data file: {self.backtest_config.get('data_file')}")

        try:
            # Create backtest exchange
            exchange = BacktestExchange(self.strategy_config['execution'])
            await exchange.initialize()

            # Create execution engine with backtest exchange
            engine = StrategyExecutionEngine(exchange, self.strategy_config)
            await engine.initialize()

            # Load cycles to test
            cycles = self._load_test_cycles()
            logger.info(f"Loaded {len(cycles)} cycles for backtesting")

            # Run backtest cycles
            await self._run_backtest_cycles(engine, exchange, cycles)

            # Get final metrics
            self.results['execution_metrics'] = await exchange.get_execution_metrics()
            self.results['final_balances'] = await exchange.fetch_balance()

            # Calculate derived metrics
            self._calculate_performance_metrics()

            # Clean up
            await exchange.close()

        except Exception as e:
            logger.error(f"Backtest failed: {e}", exc_info=True)
            self.results['error'] = str(e)

        finally:
            wall_clock_end = time.time()
            self.results['wall_clock_duration_seconds'] = wall_clock_end - wall_clock_start
            self.results['end_time'] = datetime.now(timezone.utc).isoformat()

            # Save results
            await self._save_results()

        return self.results

    def _load_test_cycles(self) -> List[List[str]]:
        """Load cycles from strategy configuration"""
        cycles_file = self.strategy_config.get('trading_pairs_file')
        if not cycles_file:
            raise ValueError("No trading_pairs_file specified in strategy")

        cycles_path = Path(cycles_file)
        if not cycles_path.exists():
            raise FileNotFoundError(f"Cycles file not found: {cycles_file}")

        cycles = []
        with open(cycles_path, 'r') as f:
            import csv
            reader = csv.reader(f)
            # Skip header if present
            header = next(reader, None)

            for row in reader:
                if row and len(row) >= 3:
                    cycle = row[:3]  # Take first 3 currencies
                    cycles.append(cycle)

        return cycles

    async def _run_backtest_cycles(
        self,
        engine: StrategyExecutionEngine,
        exchange: BacktestExchange,
        cycles: List[List[str]]
    ):
        """Execute backtest cycles with proper time simulation"""

        # Get initial simulation time
        sim_start_time = exchange.get_current_simulation_time()

        for i, cycle in enumerate(cycles):
            if i >= self.backtest_config.get('max_cycles', 100):
                logger.info(f"Reached maximum cycle limit: {i}")
                break

            try:
                # Advance simulation time slightly
                target_time = sim_start_time + (i * 5.0)  # 5 seconds between cycles
                exchange.advance_time_to(target_time)

                # Determine initial amount based on balances
                start_currency = cycle[0]
                available_balance = (await exchange.fetch_balance()).get(start_currency, 0.0)

                if available_balance <= 0:
                    logger.debug(f"No balance for {start_currency}, skipping cycle {i}")
                    continue

                # Calculate amount for this cycle
                capital_config = self.strategy_config['capital_allocation']
                if capital_config['mode'] == 'fixed_fraction':
                    amount = available_balance * capital_config['fraction']
                elif capital_config['mode'] == 'fixed_amount':
                    amount = min(capital_config.get('amount', available_balance), available_balance)
                else:
                    amount = available_balance * 0.1  # Conservative default

                # Skip if amount too small
                if amount < 0.001:
                    continue

                logger.info(f"[{i+1}/{len(cycles)}] Testing cycle: {' -> '.join(cycle + [cycle[0]])}")
                logger.info(f"Amount: {amount:.6f} {start_currency}")

                # Execute cycle
                cycle_info = await engine.execute_cycle(cycle, amount)

                # Track results
                self._track_cycle_result(cycle_info)

                # Log result
                if cycle_info.state == CycleState.COMPLETED:
                    pnl = cycle_info.profit_loss or 0.0
                    pnl_bps = (pnl / cycle_info.initial_amount) * 10000 if cycle_info.initial_amount > 0 else 0.0
                    logger.info(f"✅ Cycle completed: PnL {pnl:+.6f} ({pnl_bps:+.1f} bps)")
                elif cycle_info.state == CycleState.PARTIALLY_FILLED:
                    logger.info(f"⚠️  Cycle partial: {cycle_info.error_message}")
                else:
                    logger.info(f"❌ Cycle failed: {cycle_info.error_message}")

                # Brief pause for realism
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Cycle {i} failed: {e}")
                self.results['cycles_rejected'] += 1

        # Calculate simulation duration
        sim_end_time = exchange.get_current_simulation_time()
        self.results['simulation_duration_seconds'] = sim_end_time - sim_start_time

    def _track_cycle_result(self, cycle_info):
        """Track individual cycle results"""
        self.results['cycles_started'] += 1

        cycle_data = {
            'cycle_id': cycle_info.id,
            'cycle_path': cycle_info.cycle,
            'state': cycle_info.state.value if hasattr(cycle_info.state, 'value') else str(cycle_info.state),
            'initial_amount': cycle_info.initial_amount,
            'final_amount': cycle_info.current_amount,
            'pnl': cycle_info.profit_loss,
            'duration_ms': (cycle_info.end_time - cycle_info.start_time) * 1000 if cycle_info.end_time else 0.0,
            'orders_count': len(cycle_info.orders) if cycle_info.orders else 0,
            'error_message': cycle_info.error_message
        }

        self.results['cycles'].append(cycle_data)

        # Update counters
        if cycle_info.state == CycleState.COMPLETED:
            self.results['cycles_filled'] += 1
            if cycle_info.profit_loss:
                self.results['net_pnl'] += cycle_info.profit_loss
        elif cycle_info.state == CycleState.PARTIALLY_FILLED:
            self.results['cycles_partial'] += 1
            self.results['partials_resolved'] += 1
        elif 'slippage' in (cycle_info.error_message or '').lower():
            self.results['cycles_canceled_slippage'] += 1
        elif 'latency' in (cycle_info.error_message or '').lower():
            self.results['cycles_canceled_latency'] += 1
        else:
            self.results['cycles_rejected'] += 1

    def _calculate_performance_metrics(self):
        """Calculate comprehensive performance metrics"""
        completed_cycles = [c for c in self.results['cycles'] if c['state'] == 'completed']

        if not completed_cycles:
            logger.warning("No completed cycles for performance calculation")
            return

        # Basic metrics
        pnls = [c['pnl'] for c in completed_cycles if c['pnl'] is not None]
        durations = [c['duration_ms'] for c in completed_cycles if c['duration_ms'] > 0]

        if pnls:
            self.results['gross_pnl'] = sum(abs(pnl) for pnl in pnls)
            self.results['win_rate'] = len([pnl for pnl in pnls if pnl > 0]) / len(pnls)

            # Basis points calculation
            total_basis_points = 0.0
            for cycle in completed_cycles:
                if cycle['pnl'] and cycle['initial_amount']:
                    bp = (cycle['pnl'] / cycle['initial_amount']) * 10000
                    total_basis_points += bp
            self.results['basis_points_captured'] = total_basis_points

        if durations:
            self.results['average_cycle_duration_ms'] = sum(durations) / len(durations)

        # Calculate drawdown
        running_pnl = 0.0
        peak_pnl = 0.0
        max_drawdown = 0.0

        for cycle in completed_cycles:
            if cycle['pnl']:
                running_pnl += cycle['pnl']
                peak_pnl = max(peak_pnl, running_pnl)
                drawdown = peak_pnl - running_pnl
                max_drawdown = max(max_drawdown, drawdown)

        self.results['max_drawdown'] = max_drawdown

        # Profit factor
        winning_trades = [pnl for pnl in pnls if pnl > 0]
        losing_trades = [abs(pnl) for pnl in pnls if pnl < 0]

        if winning_trades and losing_trades:
            self.results['profit_factor'] = sum(winning_trades) / sum(losing_trades)

        # Simple Sharpe approximation (assuming daily returns)
        if len(pnls) > 1:
            import statistics
            mean_return = statistics.mean(pnls)
            std_return = statistics.stdev(pnls)
            if std_return > 0:
                self.results['sharpe_ratio'] = mean_return / std_return

    async def _save_results(self):
        """Save backtest results to JSON file"""
        results_dir = Path("logs/backtests")
        results_dir.mkdir(parents=True, exist_ok=True)

        results_file = results_dir / f"{self.results['backtest_id']}.json"

        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"📊 Backtest results saved: {results_file}")

        # Also save a summary
        summary_file = results_dir / f"{self.results['backtest_id']}_summary.txt"
        with open(summary_file, 'w') as f:
            f.write(self._generate_summary_report())

        logger.info(f"📋 Summary report saved: {summary_file}")

    def _generate_summary_report(self) -> str:
        """Generate human-readable summary report"""
        report = []
        report.append("=" * 60)
        report.append(f"BACKTEST SUMMARY: {self.results['backtest_id']}")
        report.append("=" * 60)
        report.append(f"Strategy: {self.results['strategy_name']}")
        report.append(f"Start Time: {self.results['start_time']}")
        report.append(f"End Time: {self.results['end_time']}")
        report.append(f"Wall Clock Duration: {self.results['wall_clock_duration_seconds']:.2f}s")
        report.append(f"Simulation Duration: {self.results['simulation_duration_seconds']:.2f}s")
        report.append("")

        # Cycle Statistics
        report.append("CYCLE STATISTICS")
        report.append("-" * 20)
        report.append(f"Cycles Started: {self.results['cycles_started']}")
        report.append(f"Cycles Filled: {self.results['cycles_filled']}")
        report.append(f"Cycles Partial: {self.results['cycles_partial']}")
        report.append(f"Cycles Rejected: {self.results['cycles_rejected']}")
        report.append(f"Canceled by Slippage: {self.results['cycles_canceled_slippage']}")
        report.append(f"Canceled by Latency: {self.results['cycles_canceled_latency']}")
        report.append(f"Partials Resolved: {self.results['partials_resolved']}")
        report.append("")

        # Performance Metrics
        report.append("PERFORMANCE METRICS")
        report.append("-" * 20)
        report.append(f"Net P&L: {self.results['net_pnl']:+.6f}")
        report.append(f"Gross P&L: {self.results['gross_pnl']:.6f}")
        report.append(f"Basis Points Captured: {self.results['basis_points_captured']:+.1f}")
        report.append(f"Win Rate: {self.results['win_rate']:.1%}")
        report.append(f"Profit Factor: {self.results['profit_factor']:.2f}")
        report.append(f"Max Drawdown: {self.results['max_drawdown']:.6f}")
        report.append(f"Sharpe Ratio: {self.results['sharpe_ratio']:.2f}")
        report.append(f"Avg Cycle Duration: {self.results['average_cycle_duration_ms']:.0f}ms")
        report.append("")

        # Final Balances
        if self.results['final_balances']:
            report.append("FINAL BALANCES")
            report.append("-" * 15)
            for currency, balance in self.results['final_balances'].items():
                if balance > 0.001:  # Only show meaningful balances
                    report.append(f"{currency}: {balance:.6f}")
            report.append("")

        # Configuration Summary
        report.append("CONFIGURATION")
        report.append("-" * 15)
        config = self.results['configuration']['backtest']
        report.append(f"Data File: {config.get('data_file')}")
        report.append(f"Random Seed: {config.get('random_seed')}")
        report.append(f"Fill Probability: {config.get('fill_model', {}).get('fill_probability', 'N/A')}")

        return "\n".join(report)


async def main():
    """Main backtest runner"""
    parser = argparse.ArgumentParser(description='Run deterministic backtest')
    parser.add_argument('--strategy', required=True, help='Strategy YAML configuration file')
    parser.add_argument('--data-file', help='Override backtest data file')
    parser.add_argument('--start-time', type=float, help='Start timestamp (Unix)')
    parser.add_argument('--end-time', type=float, help='End timestamp (Unix)')
    parser.add_argument('--random-seed', type=int, default=42, help='Random seed for determinism')
    parser.add_argument('--max-cycles', type=int, default=100, help='Maximum cycles to test')
    parser.add_argument('--time-acceleration', type=float, default=0.0, help='Time acceleration factor')
    parser.add_argument('--output-dir', default='logs/backtests', help='Output directory')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Load strategy configuration
    config_manager = ConfigurationManager()
    try:
        strategy_config = config_manager.load_strategy(args.strategy)
    except Exception as e:
        logger.error(f"Failed to load strategy: {e}")
        return 1

    # Build backtest configuration
    backtest_config = {
        'data_file': args.data_file or 'data/backtests/sample_feed.csv',
        'start_time': args.start_time,
        'end_time': args.end_time,
        'random_seed': args.random_seed,
        'max_cycles': args.max_cycles,
        'time_acceleration': args.time_acceleration,
        'initial_balances': {
            'BTC': 1.0,
            'ETH': 5.0,
            'USDT': 50000.0,
            'USDC': 50000.0
        },
        'slippage_model': {
            'base_slippage_bps': 3,
            'size_impact_coefficient': 0.05,
            'max_slippage_bps': 100,
            'random_component_bps': 2
        },
        'fill_model': {
            'fill_probability': 0.98,
            'partial_fill_threshold': 1000,
            'min_fill_ratio': 0.3,
            'max_fill_time_ms': 1000
        },
        'fees': {
            'taker_bps': 30,
            'maker_bps': 10
        }
    }

    # Run backtest
    runner = BacktestRunner(strategy_config, backtest_config)
    results = await runner.run()

    # Print summary
    print("\n" + runner._generate_summary_report())

    return 0 if results.get('cycles_started', 0) > 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)