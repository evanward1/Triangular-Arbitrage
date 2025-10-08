"""
Arbitrage executor for running paper trading scans and printing opportunities.
"""

import logging
from typing import Dict

import yaml

from .config_schema import DEXMEVConfig
from .dex_client import DEXClient
from .solver import ArbitrageOpportunity, ArbitrageSolver

logger = logging.getLogger(__name__)


class ArbitrageExecutor:
    """Executor for running arbitrage scans and paper trading."""

    def __init__(self, config_path: str, paper_mode: bool = True):
        """Initialize executor with config file path."""
        self.config = self._load_config(config_path)
        self.dex_client = DEXClient(self.config, paper_mode=paper_mode)
        self.solver = ArbitrageSolver(self.config, self.dex_client)

    def _load_config(self, config_path: str) -> DEXMEVConfig:
        """Load configuration from YAML file."""
        try:
            with open(config_path, "r") as f:
                config_dict = yaml.safe_load(f)
            return DEXMEVConfig.from_dict(config_dict)
        except Exception as e:
            raise ValueError(f"Failed to load config from {config_path}: {e}")

    def run_paper(self, max_opportunities: int = 10) -> None:
        """Run paper trading scan and print top opportunities."""
        logger.info("🔍 Starting DEX MEV arbitrage paper scan...")
        logger.info(f"Chain ID: {self.config.chain_id}")
        logger.info(f"Base Asset: {self.config.base_asset}")
        logger.info(f"Min Profit: {self.config.min_profit_bps} bps")
        logger.info(f"Max Slippage: {self.config.max_slippage_bps} bps")
        logger.info("")

        # Find opportunities
        opportunities = self.solver.find_arbitrage_opportunities()

        if not opportunities:
            print("❌ No profitable arbitrage opportunities found")
            return

        print(f"📊 Found {len(opportunities)} profitable opportunities:")
        print("")
        print("=" * 80)

        # Print top opportunities
        for i, opp in enumerate(opportunities[:max_opportunities]):
            self._print_opportunity(i + 1, opp)
            print("-" * 80)

        if len(opportunities) > max_opportunities:
            print(
                f"... and {len(opportunities) - max_opportunities} more opportunities"
            )

    def _print_opportunity(self, rank: int, opp: ArbitrageOpportunity) -> None:
        """Print a single arbitrage opportunity."""
        print(f"#{rank} Arbitrage Opportunity - {opp.route.dex_name}")
        print(f"Path: {opp.path[0]} → {opp.path[1]} → {opp.path[2]} → {opp.path[3]}")
        print(f"Notional Amount: {opp.notional_amount} {opp.route.base}")
        print("")

        # Show amounts at each step
        for i in range(len(opp.amounts) - 1):
            token = opp.path[i]
            amount = opp.amounts[i]
            next_token = opp.path[i + 1]
            next_amount = opp.amounts[i + 1]
            print(
                f"  Step {i + 1}: {amount:.6f} {token} → {next_amount:.6f} {next_token}"
            )

        print("")
        print(f"💰 Gross Profit: {opp.gross_bps:.2f} bps")
        print(f"💸 Net Profit:   {opp.net_bps:.2f} bps (after gas & slippage)")
        print(f"⛽ Gas Cost:     {opp.gas_cost_wei:,} wei")

        if opp.net_bps > 50:
            print("🚀 HIGH PROFIT OPPORTUNITY!")
        elif opp.net_bps > 20:
            print("✅ Good opportunity")
        else:
            print("⚠️  Marginal opportunity")

        print("")

    def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> Dict:
        """Execute an arbitrage opportunity - PAPER TRADING ONLY."""
        path_str = (
            f"{opportunity.path[0]} → {opportunity.path[1]} → "
            f"{opportunity.path[2]} → {opportunity.path[3]}"
        )
        logger.info(f"🚨 PAPER EXECUTION: {path_str}")

        # Use DEX client to execute (stub for paper trading)
        result = self.dex_client.execute_arbitrage_swap(
            path=opportunity.path,
            amounts=opportunity.amounts,
            pool_addresses=opportunity.route.pool_addresses,
        )

        logger.info(f"Paper execution result: {result['status']}")
        return result
