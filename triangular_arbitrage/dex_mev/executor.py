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
        """Print a single arbitrage opportunity with structured logging."""
        # Structured log entry
        log_data = {
            "rank": rank,
            "dex": opp.route.dex_name,
            "path": " -> ".join(opp.path),
            "pool_addresses": opp.route.pool_addresses,
            "notional_amount": float(opp.notional_amount),
            "amounts": [float(amt) for amt in opp.amounts],
            "gross_bps": opp.gross_bps,
            "net_bps": opp.net_bps,
            "gas_est_wei": opp.gas_cost_wei,
            "gas_cost_usd": float(opp.gas_cost_usd),
            "per_leg_fee_bps": opp.per_leg_fee_bps,
            "total_fee_bps": opp.total_fee_bps,
            "per_leg_slippage_bps": opp.per_leg_slippage_bps,
            "total_slippage_bps": opp.total_slippage_bps,
            "slippage_cost_usd": float(opp.slippage_cost_usd),
            "breakeven_before_gas": float(opp.breakeven_before_gas),
            "breakeven_after_gas": float(opp.breakeven_after_gas),
            "mode": "paper_trading",
            "simulation_ok": True,
            "failure_reason": None,
        }
        logger.info(f"OPPORTUNITY_FOUND: {log_data}")

        # Human-readable console output
        print(f"#{rank} Arbitrage Opportunity - {opp.route.dex_name}")
        print(f"Path: {opp.path[0]} → {opp.path[1]} → {opp.path[2]} → {opp.path[3]}")
        print(f"Notional Amount: {opp.notional_amount} {opp.route.base}")
        print("")

        # Show amounts at each step with slippage
        for i in range(len(opp.amounts) - 1):
            token = opp.path[i]
            amount = opp.amounts[i]
            next_token = opp.path[i + 1]
            next_amount = opp.amounts[i + 1]
            slippage = (
                opp.per_leg_slippage_bps[i] if i < len(opp.per_leg_slippage_bps) else 0
            )
            print(
                f"  Step {i + 1}: {amount:.6f} {token} → "
                f"{next_amount:.6f} {next_token} (slippage: {slippage:.1f} bps)"
            )

        print("")
        print(f"💰 Gross Profit:     {opp.gross_bps:.2f} bps")
        print(
            f"💵 DEX Fees:         {opp.total_fee_bps:.1f} bps "
            f"({len(opp.per_leg_fee_bps)} legs × {opp.per_leg_fee_bps[0]:.1f} bps)"
        )
        print(
            f"📉 Slippage Cost:    ${opp.slippage_cost_usd:.2f} ({opp.total_slippage_bps:.1f} bps)"
        )
        print(f"⛽ Gas Cost:         ${opp.gas_cost_usd:.2f} ({opp.gas_cost_wei:,} wei)")
        print(f"💵 Breakeven (pre):  ${opp.breakeven_before_gas:.2f}")
        print(f"💸 Breakeven (post): ${opp.breakeven_after_gas:.2f}")
        print(f"📊 Net Profit:       {opp.net_bps:.2f} bps")

        if opp.net_bps > 50:
            print("🚀 HIGH PROFIT OPPORTUNITY!")
        elif opp.net_bps > 20:
            print("✅ Good opportunity")
        else:
            print("⚠️  Marginal opportunity")

        print("")

    def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> Dict:
        """Execute an arbitrage opportunity - PAPER TRADING ONLY."""
        # CRITICAL: Refresh opportunity right before execution to ensure profitability
        try:
            opportunity = self.solver.refresh_and_revalidate(opportunity)
        except ValueError as e:
            logger.warning(f"Opportunity invalidated during pre-execution refresh: {e}")
            return {
                "transaction_hash": None,
                "gas_used": 0,
                "status": "aborted",
                "note": f"REFRESH_FAILED: {e}",
            }

        # Structured execution log
        execution_log = {
            "action": "EXECUTE_OPPORTUNITY",
            "mode": "paper_trading",
            "path": " -> ".join(opportunity.path),
            "pool_addresses": opportunity.route.pool_addresses,
            "dex": opportunity.route.dex_name,
            "notional_amount": float(opportunity.notional_amount),
            "amounts": [float(amt) for amt in opportunity.amounts],
            "gross_bps": opportunity.gross_bps,
            "net_bps": opportunity.net_bps,
            "total_fee_bps": opportunity.total_fee_bps,
            "gas_est": opportunity.gas_cost_wei,
            "gas_cost_usd": float(opportunity.gas_cost_usd),
            "breakeven_before_gas": float(opportunity.breakeven_before_gas),
            "breakeven_after_gas": float(opportunity.breakeven_after_gas),
            "total_slippage_bps": opportunity.total_slippage_bps,
            "slippage_cost_usd": float(opportunity.slippage_cost_usd),
            "simulation_ok": True,
            "refreshed": True,
        }
        logger.info(f"EXECUTION_START: {execution_log}")

        # Use DEX client to execute (stub for paper trading)
        result = self.dex_client.execute_arbitrage_swap(
            path=opportunity.path,
            amounts=opportunity.amounts,
            pool_addresses=opportunity.route.pool_addresses,
        )

        # Log execution result
        result_log = {
            "action": "EXECUTION_COMPLETE",
            "status": result["status"],
            "tx_hash": result.get("transaction_hash"),
            "gas_used": result.get("gas_used"),
            "mode": "paper_trading",
        }
        logger.info(f"EXECUTION_RESULT: {result_log}")

        return result
