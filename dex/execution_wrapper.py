"""
Execution wrapper that integrates DexExecutor with DexRunner.

Adds execution capability to the paper trading scanner.
"""

import asyncio
from typing import List, Optional

from triangular_arbitrage.utils import get_logger

from .executor import DexExecutor, ExecutionConfig, ExecutionResult
from .runner import DexRunner
from .types import ArbRow, DexPool

logger = get_logger(__name__)


class ExecutionEnabledRunner(DexRunner):
    """
    DexRunner with execution capabilities.

    Extends DexRunner to add:
    - Automatic execution of profitable opportunities
    - Safety checks and rate limiting
    - Execution statistics tracking
    """

    def __init__(
        self,
        config,
        execution_config: Optional[ExecutionConfig] = None,
        auto_execute: bool = False,
        quiet: bool = False,
        use_dynamic_pools: bool = None,
        starting_capital_usd: float = 1000.0,
    ):
        """
        Initialize execution-enabled runner.

        Args:
            config: DexConfig instance
            execution_config: ExecutionConfig (if None, dry-run mode)
            auto_execute: If True, automatically execute opportunities
            quiet: Quiet mode (less logging)
            use_dynamic_pools: Use dynamic pool discovery
            starting_capital_usd: Starting account balance in USD (default: $1000)
        """
        super().__init__(config, quiet, use_dynamic_pools)

        # Initialize executor
        self.execution_config = execution_config or ExecutionConfig(dry_run_mode=True)
        self.executor: Optional[DexExecutor] = None
        self.auto_execute = auto_execute

        # Account balance tracking
        self.starting_capital_usd = starting_capital_usd

        # Execution tracking
        self.opportunities_found = 0
        self.opportunities_executed = 0
        self.last_execution_time = 0.0

        # Rate limiting (prevent spam execution)
        self.min_execution_interval_sec = 5.0  # Wait at least 5s between executions

    def connect(self) -> None:
        """Connect to RPC and initialize executor."""
        super().connect()

        # Initialize executor after web3 is connected
        if self.web3:
            self.executor = DexExecutor(
                self.web3,
                self.execution_config,
                router_address=None,  # TODO: Set your router address
            )
            logger.info(
                f"Executor initialized (dry_run={self.execution_config.dry_run_mode})"
            )

    async def scan_and_execute_async(self) -> List[ArbRow]:
        """
        Scan for opportunities and optionally execute the best one.

        Returns:
            List of all opportunities found (sorted by net_pct)
        """
        # Scan for opportunities
        rows = await self.scan_async()

        if not rows:
            return []

        # Find executable opportunities
        opportunities = [r for r in rows if r.net_pct >= self.config.threshold_net_pct]

        if not opportunities:
            return rows

        self.opportunities_found += len(opportunities)

        # Auto-execute if enabled
        if self.auto_execute and self.executor:
            best = opportunities[0]

            # Rate limiting check
            import time

            time_since_last = time.time() - self.last_execution_time

            if time_since_last < self.min_execution_interval_sec:
                logger.debug(
                    f"Skipping execution (rate limit: {time_since_last:.1f}s < {self.min_execution_interval_sec}s)"
                )
                return rows

            # Execute best opportunity
            await self._execute_opportunity(best)

        return rows

    async def _execute_opportunity(
        self, opportunity: ArbRow
    ) -> Optional[ExecutionResult]:
        """
        Execute a single opportunity.

        Args:
            opportunity: Arbitrage opportunity

        Returns:
            ExecutionResult if executed, None if skipped
        """
        import time

        self.last_execution_time = time.time()

        logger.info(f"\n{'='*80}")
        logger.info(f"EXECUTING OPPORTUNITY: {opportunity.cycle}")
        logger.info(
            f"Net Profit: {opportunity.net_pct:+.2f}% (${opportunity.pnl_usd:.2f})"
        )
        logger.info(f"{'='*80}\n")

        # Find pools for this opportunity
        pool1, pool2 = self._find_pools_for_opportunity(opportunity)

        if not pool1 or not pool2:
            logger.error("Failed to find pools for opportunity")
            return None

        # Calculate trade amount
        trade_amount = self._calculate_trade_amount(pool1)

        # Execute
        result = await self.executor.execute_opportunity(
            opportunity,
            pool1,
            pool2,
            trade_amount,
        )

        if result.success:
            self.opportunities_executed += 1
            logger.info(
                f"✓ Execution successful! "
                f"Profit: ${result.net_profit_usd:.2f}, "
                f"Gas: ${result.gas_cost_usd:.2f}, "
                f"Time: {result.execution_time_ms:.0f}ms"
            )
        else:
            logger.error(f"✗ Execution failed: {result.error}")

        return result

    def _find_pools_for_opportunity(
        self, opportunity: ArbRow
    ) -> tuple[Optional[DexPool], Optional[DexPool]]:
        """
        Find the two pools involved in an opportunity.

        Args:
            opportunity: Arbitrage opportunity

        Returns:
            Tuple of (pool1, pool2) or (None, None) if not found
        """
        # Parse pair from opportunity
        # Format: "USDT/WBNB"
        pair_tokens = opportunity.pair.split("/")
        if len(pair_tokens) != 2:
            return None, None

        base_sym, quote_sym = pair_tokens

        # Find pools matching dexA and dexB
        pool1 = None
        pool2 = None

        for pool in self.pools:
            if (
                pool.dex == opportunity.dexA
                and pool.base_symbol == base_sym
                and pool.quote_symbol == quote_sym
            ):
                pool1 = pool
            elif (
                pool.dex == opportunity.dexB
                and pool.base_symbol == base_sym
                and pool.quote_symbol == quote_sym
            ):
                pool2 = pool

        return pool1, pool2

    def _calculate_trade_amount(self, pool: DexPool):
        """Calculate trade amount based on config."""
        from decimal import Decimal

        # Use max_position_usd from config
        usd_amount = Decimal(str(self.config.max_position_usd))

        # Convert to token units (assuming pool has USD quote)
        # This is simplified - production should use proper price conversion
        quote_decimals = self.decimals_of.get(pool.quote_symbol, 18)
        trade_amount = usd_amount * Decimal(10) ** quote_decimals

        return trade_amount

    def print_balance_line(self) -> None:
        """Print current balance as a compact status line."""
        from .runner import Colors as c

        current_balance = self.get_current_balance_usd()
        total_pnl = current_balance - self.starting_capital_usd
        pnl_pct = (
            (total_pnl / self.starting_capital_usd * 100)
            if self.starting_capital_usd > 0
            else 0.0
        )

        # Color based on profit/loss
        balance_color = (
            c.GREEN if total_pnl > 0 else (c.RED if total_pnl < 0 else c.WHITE)
        )
        pnl_symbol = "↑" if total_pnl > 0 else ("↓" if total_pnl < 0 else "→")

        print(f"\n  {c.CYAN}{'─' * 72}{c.RESET}")
        print(
            f"  {c.BOLD}Balance:{c.RESET} {balance_color}${current_balance:,.2f}{c.RESET} "
            f"{c.DIM}(Started: ${self.starting_capital_usd:,.2f}){c.RESET} "
            f"{c.BOLD}P&L:{c.RESET} {balance_color}{pnl_symbol} "
            f"{'+' if total_pnl >= 0 else ''}${total_pnl:.2f} ({pnl_pct:+.2f}%){c.RESET}"
        )
        print(f"  {c.CYAN}{'─' * 72}{c.RESET}\n")

    async def run_with_execution_async(self) -> None:
        """
        Main loop with execution capability (async version).

        Similar to run_async() but with automatic execution.
        """
        # Block until pools are loaded
        if not self.pools:
            raise RuntimeError(
                "No pools loaded. Call fetch_pools() before run_with_execution_async()."
            )

        # Print banner with execution mode
        self._print_execution_banner()

        scan_num = 0
        while True:
            scan_num += 1

            try:
                rows = await self.scan_and_execute_async()
                self.print_results(rows, scan_num)

                # Show current balance after each scan
                self.print_balance_line()

            except KeyboardInterrupt:
                # Print final stats before exit
                if self.executor:
                    self.executor.print_stats()
                raise
            except Exception as e:
                logger.error(f"\nScan {scan_num} failed: {e}", exc_info=True)
                if self.config.once:
                    raise

            if self.config.once:
                break

            await asyncio.sleep(self.config.poll_sec)

    def get_current_balance_usd(self) -> float:
        """
        Calculate current account balance.

        Returns:
            Current balance = starting capital + net profit
        """
        if self.executor:
            stats = self.executor.get_stats()
            net_profit = stats["net_profit_usd"]
            return self.starting_capital_usd + net_profit
        return self.starting_capital_usd

    def _print_execution_banner(self) -> None:
        """Print banner with execution mode info."""
        from .runner import Colors as c

        self.print_banner()

        # Add execution mode info
        print(f"  {c.BOLD}Execution Mode:{c.RESET}")

        if self.execution_config.dry_run_mode:
            mode_str = f"{c.YELLOW}DRY RUN{c.RESET} (simulation only)"
        else:
            mode_str = f"{c.RED}LIVE{c.RESET} (real transactions)"

        print(f"    {c.DIM}Mode:{c.RESET} {mode_str}")
        print(
            f"    {c.DIM}Auto-Execute:{c.RESET} {c.GREEN if self.auto_execute else c.RED}{self.auto_execute}{c.RESET}"
        )

        if self.executor and self.executor.account:
            print(
                f"    {c.DIM}Wallet:{c.RESET} {c.WHITE}{self.executor.account.address}{c.RESET}"
            )

        # Show starting balance prominently
        print(f"\n  {c.BOLD}Account Balance:{c.RESET}")
        print(
            f"    {c.DIM}Starting Capital:{c.RESET} {c.GREEN}${self.starting_capital_usd:,.2f}{c.RESET}"
        )

        print(f"\n{c.CYAN}{'═' * 80}{c.RESET}\n")

    def get_execution_stats(self) -> dict:
        """Get execution statistics."""
        stats = {
            "opportunities_found": self.opportunities_found,
            "opportunities_executed": self.opportunities_executed,
            "execution_rate": (
                self.opportunities_executed / self.opportunities_found * 100
                if self.opportunities_found > 0
                else 0.0
            ),
        }

        if self.executor:
            stats.update(self.executor.get_stats())

        return stats

    def print_execution_summary(self) -> None:
        """Print execution summary with clear balance display."""
        from .runner import Colors as c

        stats = self.get_execution_stats()
        current_balance = self.get_current_balance_usd()
        total_pnl = current_balance - self.starting_capital_usd
        pnl_pct = (
            (total_pnl / self.starting_capital_usd * 100)
            if self.starting_capital_usd > 0
            else 0.0
        )

        print("\n" + "=" * 80)
        print("  EXECUTION SUMMARY")
        print("=" * 80)

        # Account Balance Section (MOST PROMINENT)
        print(f"\n  {c.BOLD}ACCOUNT BALANCE:{c.RESET}")
        print(f"  {'─' * 76}")
        print(
            f"  Starting Capital:      {c.DIM}${self.starting_capital_usd:>12,.2f}{c.RESET}"
        )

        # Color-code current balance based on profit/loss
        balance_color = (
            c.GREEN if total_pnl > 0 else (c.RED if total_pnl < 0 else c.WHITE)
        )
        pnl_color = c.GREEN if total_pnl > 0 else (c.RED if total_pnl < 0 else c.WHITE)

        print(
            f"  {c.BOLD}Current Balance:       {balance_color}${current_balance:>12,.2f}{c.RESET}"
        )
        pnl_sign = "+" if total_pnl >= 0 else ""
        print(
            f"  {c.BOLD}Total P&L:             {pnl_color}{pnl_sign}${total_pnl:>12,.2f} "
            f"({pnl_pct:+.2f}%){c.RESET}"
        )

        # Trading Statistics
        print(f"\n  {c.BOLD}TRADING STATISTICS:{c.RESET}")
        print(f"  {'─' * 76}")
        print(f"  Opportunities Found:   {stats['opportunities_found']:>12,}")
        print(f"  Opportunities Executed: {stats['opportunities_executed']:>12,}")
        print(f"  Execution Rate:        {stats['execution_rate']:>11.1f}%")

        if self.executor:
            print(f"\n  Execution Attempts:    {stats['executions_attempted']:>12,}")
            print(f"  Successful:            {stats['executions_successful']:>12,}")
            print(f"  Success Rate:          {stats['success_rate_pct']:>11.1f}%")

            # Profit Breakdown
            print(f"\n  {c.BOLD}PROFIT BREAKDOWN:{c.RESET}")
            print(f"  {'─' * 76}")
            print(
                f"  Gross Profit:          {c.GREEN}${stats['total_profit_usd']:>12,.2f}{c.RESET}"
            )
            print(
                f"  Gas Costs:             {c.RED}-${stats['total_gas_cost_usd']:>12,.2f}{c.RESET}"
            )
            net_sign = "+" if stats["net_profit_usd"] >= 0 else ""
            print(
                f"  Net Profit:            {pnl_color}{net_sign}"
                f"${stats['net_profit_usd']:>12,.2f}{c.RESET}"
            )

        print("=" * 80 + "\n")
