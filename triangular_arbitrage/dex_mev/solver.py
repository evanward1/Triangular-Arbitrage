"""
Arbitrage solver for discovering and evaluating base -> mid -> alt -> base cycles.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .config_schema import DEXMEVConfig, RouteConfig
from .dex_client import DEXClient

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents a discovered arbitrage opportunity."""

    route: RouteConfig
    path: List[str]  # [base, mid, alt, base]
    amounts: List[Decimal]  # Amount at each step
    gross_bps: float  # Gross profit in basis points
    net_bps: float  # Net profit after gas/slippage in basis points
    gas_cost_wei: int  # Estimated gas cost
    notional_amount: Decimal  # Base amount used for calculation


class ArbitrageSolver:
    """Solver for discovering and evaluating arbitrage opportunities."""

    def __init__(self, config: DEXMEVConfig, dex_client: DEXClient):
        """Initialize arbitrage solver."""
        self.config = config
        self.dex_client = dex_client
        self.gas_cost_constant_wei = 200000 * 20 * 10**9  # ~200k gas at 20 gwei

    def find_arbitrage_opportunities(
        self, notional_amount: Decimal = None
    ) -> List[ArbitrageOpportunity]:
        """Find all profitable arbitrage opportunities."""
        if notional_amount is None:
            notional_amount = Decimal("1000.0")  # Default $1000 equivalent

        opportunities = []

        for route in self.config.routes:
            if route.base == self.config.base_asset:
                opportunity = self._evaluate_route(route, notional_amount)
                if opportunity:
                    logger.debug(
                        f"Found opportunity with net_bps={opportunity.net_bps}, "
                        f"min_profit_bps={self.config.min_profit_bps}"
                    )
                    if opportunity.net_bps >= self.config.min_profit_bps:
                        opportunities.append(opportunity)

        # Sort by net profit descending
        opportunities.sort(key=lambda x: x.net_bps, reverse=True)
        return opportunities

    def _evaluate_route(
        self, route: RouteConfig, notional_amount: Decimal
    ) -> ArbitrageOpportunity:
        """Evaluate a specific arbitrage route."""
        logger.debug(
            f"Evaluating route: {route.base} -> {route.mid} -> {route.alt} -> {route.base}"
        )

        try:
            # Step 1: base -> mid
            amount_mid = self.dex_client.estimate_swap_output(
                route.base,
                route.mid,
                notional_amount,
                route.pool_addresses[0] if route.pool_addresses else "",
            )

            # Step 2: mid -> alt
            amount_alt = self.dex_client.estimate_swap_output(
                route.mid,
                route.alt,
                amount_mid,
                route.pool_addresses[1] if len(route.pool_addresses) > 1 else "",
            )

            # Step 3: alt -> base
            amount_base_final = self.dex_client.estimate_swap_output(
                route.alt,
                route.base,
                amount_alt,
                route.pool_addresses[2] if len(route.pool_addresses) > 2 else "",
            )

            # Calculate profit
            gross_profit = amount_base_final - notional_amount
            gross_bps = float((gross_profit / notional_amount) * 10000)

            # Apply slippage haircut
            slippage_factor = Decimal(1.0) - (
                Decimal(self.config.max_slippage_bps) / 10000
            )
            amount_base_after_slippage = amount_base_final * slippage_factor

            # Calculate gas cost in base asset terms (simplified)
            # Lower gas cost for demo purposes
            gas_cost_wei = self.gas_cost_constant_wei
            gas_cost_base = Decimal("5.0")  # Fixed $5 gas cost for paper trading

            # Net profit after gas and slippage
            net_profit = amount_base_after_slippage - notional_amount - gas_cost_base
            net_bps = float((net_profit / notional_amount) * 10000)

            return ArbitrageOpportunity(
                route=route,
                path=[route.base, route.mid, route.alt, route.base],
                amounts=[notional_amount, amount_mid, amount_alt, amount_base_final],
                gross_bps=gross_bps,
                net_bps=net_bps,
                gas_cost_wei=gas_cost_wei,
                notional_amount=notional_amount,
            )

        except Exception as e:
            logger.error(
                f"Error evaluating route {route.base}->{route.mid}->{route.alt}: {e}"
            )
            return None

    def get_optimal_amount(self, route: RouteConfig) -> Decimal:
        """Calculate optimal amount for maximum profit (simplified)."""
        # Stub implementation - would implement more sophisticated optimization
        return Decimal("1000.0")
