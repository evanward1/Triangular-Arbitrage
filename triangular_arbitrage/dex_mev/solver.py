"""
Arbitrage solver for discovering and evaluating base -> mid -> alt -> base cycles.
"""

import logging
import time
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
    gas_cost_usd: Decimal  # Gas cost in USD
    notional_amount: Decimal  # Base amount used for calculation
    per_leg_slippage_bps: List[float]  # Slippage per leg in bps
    total_slippage_bps: float  # Total slippage across all legs
    slippage_cost_usd: Decimal  # Slippage cost in USD
    breakeven_before_gas: Decimal  # Profit before gas costs
    breakeven_after_gas: Decimal  # Profit after all costs
    per_leg_fee_bps: List[float]  # DEX fee per leg in bps (e.g., 30 for 0.3%)
    total_fee_bps: float  # Total DEX fees across all legs in bps
    snapshot_timestamp: float = 0.0  # Unix timestamp when opportunity was calculated


class ArbitrageSolver:
    """Solver for discovering and evaluating arbitrage opportunities."""

    def __init__(self, config: DEXMEVConfig, dex_client: DEXClient):
        """Initialize arbitrage solver."""
        self.config = config
        self.dex_client = dex_client
        self.gas_cost_constant_wei = 200000 * 20 * 10**9  # ~200k gas at 20 gwei

        # ETH price for gas cost estimation (would come from oracle in production)
        self.eth_price_usd = Decimal("2000.0")

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

    def _calculate_per_leg_slippage(
        self, amount_in: Decimal, amount_out: Decimal, price_impact_bps: float = 0
    ) -> float:
        """
        Calculate slippage for a single leg.

        Args:
            amount_in: Input amount
            amount_out: Output amount
            price_impact_bps: Additional price impact in bps

        Returns:
            Slippage in basis points
        """
        # Slippage is the deviation from perfect execution
        # For simplicity, use a conservative estimate based on trade size
        # In production, would calculate based on reserves and liquidity depth
        base_slippage_bps = 5.0  # Base 5 bps slippage
        slippage_bps = base_slippage_bps + price_impact_bps
        return slippage_bps

    def _estimate_gas_cost_usd(self, gas_limit: int, gas_price_gwei: int) -> Decimal:
        """
        Estimate gas cost in USD.

        Args:
            gas_limit: Gas limit for transaction
            gas_price_gwei: Gas price in gwei

        Returns:
            Gas cost in USD
        """
        gas_cost_wei = gas_limit * gas_price_gwei * 10**9
        gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)
        gas_cost_usd = gas_cost_eth * self.eth_price_usd
        return gas_cost_usd

    def _evaluate_route(
        self, route: RouteConfig, notional_amount: Decimal
    ) -> ArbitrageOpportunity:
        """Evaluate a specific arbitrage route with detailed slippage and breakeven analysis."""
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
            leg1_slippage = self._calculate_per_leg_slippage(
                notional_amount, amount_mid
            )

            # Check per-leg slippage cap
            if leg1_slippage > self.config.per_leg_slippage_bps:
                logger.debug(
                    f"Leg 1 slippage {leg1_slippage:.2f} bps exceeds cap {self.config.per_leg_slippage_bps} bps"
                )
                return None

            # Step 2: mid -> alt
            amount_alt = self.dex_client.estimate_swap_output(
                route.mid,
                route.alt,
                amount_mid,
                route.pool_addresses[1] if len(route.pool_addresses) > 1 else "",
            )
            leg2_slippage = self._calculate_per_leg_slippage(amount_mid, amount_alt)

            if leg2_slippage > self.config.per_leg_slippage_bps:
                logger.debug(
                    f"Leg 2 slippage {leg2_slippage:.2f} bps exceeds cap "
                    f"{self.config.per_leg_slippage_bps} bps"
                )
                return None

            # Step 3: alt -> base
            amount_base_final = self.dex_client.estimate_swap_output(
                route.alt,
                route.base,
                amount_alt,
                route.pool_addresses[2] if len(route.pool_addresses) > 2 else "",
            )
            leg3_slippage = self._calculate_per_leg_slippage(
                amount_alt, amount_base_final
            )

            if leg3_slippage > self.config.per_leg_slippage_bps:
                logger.debug(
                    f"Leg 3 slippage {leg3_slippage:.2f} bps exceeds cap {self.config.per_leg_slippage_bps} bps"
                )
                return None

            # Calculate total slippage
            per_leg_slippage_bps = [leg1_slippage, leg2_slippage, leg3_slippage]
            total_slippage_bps = sum(per_leg_slippage_bps)

            # Check cycle-wide slippage cap
            if total_slippage_bps > self.config.cycle_slippage_bps:
                logger.debug(
                    f"Total slippage {total_slippage_bps:.2f} bps exceeds cycle cap "
                    f"{self.config.cycle_slippage_bps} bps"
                )
                return None

            # Calculate DEX fees (0.3% = 30 bps per leg for most DEXes)
            # In paper mode, the swap math already applies 0.3% per leg
            # We need to track this explicitly so DecisionEngine can display it
            fee_bps_per_leg = 30.0  # 0.3% standard Uniswap V2 fee
            per_leg_fee_bps = [fee_bps_per_leg, fee_bps_per_leg, fee_bps_per_leg]
            total_fee_bps = sum(per_leg_fee_bps)

            # Calculate gross profit
            gross_profit = amount_base_final - notional_amount
            gross_bps = float((gross_profit / notional_amount) * 10000)

            # Calculate slippage cost in USD (conservative estimate)
            slippage_cost_usd = notional_amount * (Decimal(total_slippage_bps) / 10000)

            # Calculate gas cost in USD
            gas_price_gwei = self.dex_client.get_gas_price()
            # For paper mode, use realistic but lower gas assumptions
            if self.dex_client.paper_mode:
                gas_limit = 250000  # More realistic for 3-leg arb
            else:
                gas_limit = self.config.gas_limit_cap
            gas_cost_wei = gas_limit * gas_price_gwei * 10**9
            gas_cost_usd = self._estimate_gas_cost_usd(gas_limit, gas_price_gwei)

            # Calculate breakeven
            breakeven_before_gas = gross_profit - slippage_cost_usd
            breakeven_after_gas = breakeven_before_gas - gas_cost_usd

            # Log detailed breakeven calculation
            logger.debug(
                f"Route {route.base}->{route.mid}->{route.alt}: "
                f"gross_profit=${gross_profit:.2f}, "
                f"slippage_cost=${slippage_cost_usd:.2f}, "
                f"gas_cost=${gas_cost_usd:.2f}, "
                f"breakeven_before_gas=${breakeven_before_gas:.2f}, "
                f"breakeven_after_gas=${breakeven_after_gas:.2f}"
            )

            # Check if breakeven after gas meets threshold
            min_profit_threshold = notional_amount * (
                Decimal(self.config.min_profit_bps) / 10000
            )
            if breakeven_after_gas < min_profit_threshold:
                logger.debug(
                    f"Breakeven after gas ${breakeven_after_gas:.2f} below threshold ${min_profit_threshold:.2f}"
                )
                return None

            # Calculate net profit in bps
            # IMPORTANT: This is the authoritative net calculation for DEX opportunities.
            # Do NOT recalculate net by subtracting costs from gross elsewhere - that leads
            # to double-counting. The breakeven_after_gas already accounts for all costs.
            net_profit = breakeven_after_gas
            net_bps = float((net_profit / notional_amount) * 10000)

            return ArbitrageOpportunity(
                route=route,
                path=[route.base, route.mid, route.alt, route.base],
                amounts=[notional_amount, amount_mid, amount_alt, amount_base_final],
                gross_bps=gross_bps,
                net_bps=net_bps,
                gas_cost_wei=gas_cost_wei,
                gas_cost_usd=gas_cost_usd,
                notional_amount=notional_amount,
                per_leg_slippage_bps=per_leg_slippage_bps,
                total_slippage_bps=total_slippage_bps,
                slippage_cost_usd=slippage_cost_usd,
                breakeven_before_gas=breakeven_before_gas,
                breakeven_after_gas=breakeven_after_gas,
                per_leg_fee_bps=per_leg_fee_bps,
                total_fee_bps=total_fee_bps,
                snapshot_timestamp=time.time(),
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

    def refresh_and_revalidate(
        self, opportunity: ArbitrageOpportunity
    ) -> ArbitrageOpportunity:
        """
        Refresh reserves and recalculate opportunity metrics.

        This should be called right before execution to ensure the opportunity
        is still valid with current on-chain reserves.

        Args:
            opportunity: The original opportunity to refresh

        Returns:
            Updated ArbitrageOpportunity with fresh reserves and metrics,
            or None if the opportunity is no longer valid

        Raises:
            ValueError: If refreshed opportunity falls below profitability threshold
        """
        logger.info(
            f"Refreshing opportunity: {opportunity.route.base}->{opportunity.route.mid}->{opportunity.route.alt} "
            f"(original net={opportunity.net_bps:.2f} bps, age={time.time() - opportunity.snapshot_timestamp:.1f}s)"
        )

        # Re-evaluate the route with current reserves
        refreshed = self._evaluate_route(opportunity.route, opportunity.notional_amount)

        if refreshed is None:
            raise ValueError(
                f"Opportunity no longer valid after refresh: "
                f"original_net={opportunity.net_bps:.2f} bps, "
                f"route={opportunity.route.base}->{opportunity.route.mid}->{opportunity.route.alt}"
            )

        # Check if net profit dropped significantly (more than 20% decline)
        net_decline_pct = (
            (opportunity.net_bps - refreshed.net_bps) / opportunity.net_bps * 100
            if opportunity.net_bps != 0
            else 0
        )

        if net_decline_pct > 20:
            logger.warning(
                f"Opportunity profit declined {net_decline_pct:.1f}% after refresh: "
                f"original_net={opportunity.net_bps:.2f} bps -> refreshed_net={refreshed.net_bps:.2f} bps"
            )

        logger.info(
            f"Opportunity refreshed successfully: "
            f"net={refreshed.net_bps:.2f} bps (was {opportunity.net_bps:.2f} bps, "
            f"change={refreshed.net_bps - opportunity.net_bps:+.2f} bps)"
        )

        return refreshed
