"""
DEX arbitrage execution engine with MEV protection.

Handles:
- Transaction building and signing
- MEV-protected bundle submission (Flashbots for Ethereum, bloXroute for BSC)
- Dry-run simulation
- Execution monitoring and safety checks
"""

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.types import TxParams, Wei

from triangular_arbitrage.utils import get_logger

from .types import ArbRow, DexPool

logger = get_logger(__name__)


@dataclass
class ExecutionConfig:
    """
    Configuration for arbitrage execution.

    Attributes:
        private_key: Private key for signing transactions (WARNING: keep secure!)
        max_gas_price_gwei: Maximum gas price willing to pay
        max_priority_fee_gwei: Maximum priority fee (EIP-1559)
        use_flashbots: Enable Flashbots/MEV-protected bundles
        dry_run_mode: If True, simulate but don't submit transactions
        min_profit_threshold_usd: Minimum profit to execute (safety check)
        max_slippage_pct: Maximum slippage tolerance
    """

    private_key: Optional[str] = None
    max_gas_price_gwei: float = 10.0
    max_priority_fee_gwei: float = 2.0
    use_flashbots: bool = True
    dry_run_mode: bool = True
    min_profit_threshold_usd: float = 5.0
    max_slippage_pct: float = 1.0


@dataclass
class ExecutionResult:
    """
    Result of an execution attempt.

    Attributes:
        success: Whether execution succeeded
        tx_hash: Transaction hash (if submitted)
        net_profit_usd: Actual net profit in USD
        gas_used: Gas consumed
        gas_cost_usd: Gas cost in USD
        execution_time_ms: Time from submission to confirmation
        error: Error message (if failed)
    """

    success: bool
    tx_hash: Optional[str] = None
    net_profit_usd: Optional[float] = None
    gas_used: Optional[int] = None
    gas_cost_usd: Optional[float] = None
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None


class DexExecutor:
    """
    Executes DEX arbitrage opportunities with MEV protection.

    Supports:
    - Ethereum: Flashbots bundles
    - BSC: bloXroute bundles or direct submission
    """

    def __init__(
        self,
        web3: Web3,
        config: ExecutionConfig,
        router_address: Optional[str] = None,
    ):
        """
        Initialize executor.

        Args:
            web3: Web3 instance
            config: Execution configuration
            router_address: DEX router contract address (if using router pattern)
        """
        self.web3 = web3
        self.config = config
        self.router_address = router_address

        # Initialize account if private key provided
        self.account: Optional[LocalAccount] = None
        if config.private_key:
            try:
                self.account = Account.from_key(config.private_key)
                logger.info(f"Loaded account: {self.account.address}")
            except Exception as e:
                logger.error(f"Failed to load private key: {e}")
                raise

        # Execution statistics
        self.executions_attempted = 0
        self.executions_successful = 0
        self.total_profit_usd = 0.0
        self.total_gas_cost_usd = 0.0

    def can_execute(self, opportunity: ArbRow) -> tuple[bool, str]:
        """
        Check if opportunity meets execution criteria.

        Args:
            opportunity: Arbitrage opportunity

        Returns:
            Tuple of (can_execute: bool, reason: str)
        """
        # Check profit threshold
        if opportunity.pnl_usd < self.config.min_profit_threshold_usd:
            return (
                False,
                f"Profit ${opportunity.pnl_usd:.2f} < threshold ${self.config.min_profit_threshold_usd:.2f}",
            )

        # Check net percentage is positive
        if opportunity.net_pct <= 0:
            return False, f"Net profit {opportunity.net_pct:.2f}% <= 0%"

        # Check account is loaded
        if not self.account:
            return False, "No account loaded (missing private key)"

        return True, "OK"

    async def execute_opportunity(
        self,
        opportunity: ArbRow,
        pool1: DexPool,
        pool2: DexPool,
        trade_amount: Decimal,
    ) -> ExecutionResult:
        """
        Execute a 2-leg arbitrage opportunity.

        Args:
            opportunity: Arbitrage opportunity details
            pool1: First pool (buy leg)
            pool2: Second pool (sell leg)
            trade_amount: Amount to trade (in quote token units)

        Returns:
            ExecutionResult with outcome
        """
        start_time = time.time()
        self.executions_attempted += 1

        # Safety check
        can_execute, reason = self.can_execute(opportunity)
        if not can_execute:
            logger.warning(f"Execution blocked: {reason}")
            return ExecutionResult(success=False, error=reason)

        # Dry run mode - simulate only
        if self.config.dry_run_mode:
            logger.info(
                f"[DRY RUN] Would execute: {opportunity.cycle} "
                f"(net: {opportunity.net_pct:+.2f}%, profit: ${opportunity.pnl_usd:.2f})"
            )
            return ExecutionResult(
                success=True,
                tx_hash="0xDRYRUN",
                net_profit_usd=opportunity.pnl_usd,
                gas_used=200000,
                gas_cost_usd=0.15,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            # Build transaction
            logger.info(f"Building transaction for {opportunity.cycle}...")
            tx_params = await self._build_arbitrage_transaction(
                pool1, pool2, trade_amount
            )

            # Submit via MEV protection if enabled
            if self.config.use_flashbots:
                logger.info("Submitting via MEV-protected bundle...")
                tx_hash = await self._submit_flashbots_bundle(tx_params)
            else:
                logger.info("Submitting directly to mempool...")
                tx_hash = await self._submit_direct(tx_params)

            # Wait for confirmation
            logger.info(f"Waiting for tx {tx_hash}...")
            receipt = await self._wait_for_transaction(tx_hash)

            # Calculate actual profit
            execution_time_ms = (time.time() - start_time) * 1000
            gas_used = receipt["gasUsed"]
            gas_cost_usd = self._calculate_gas_cost(gas_used)
            net_profit_usd = opportunity.pnl_usd - gas_cost_usd

            # Update stats
            self.executions_successful += 1
            self.total_profit_usd += net_profit_usd
            self.total_gas_cost_usd += gas_cost_usd

            logger.info(
                f"✓ Execution succeeded! Profit: ${net_profit_usd:.2f}, "
                f"Gas: ${gas_cost_usd:.2f}, Time: {execution_time_ms:.0f}ms"
            )

            return ExecutionResult(
                success=True,
                tx_hash=tx_hash,
                net_profit_usd=net_profit_usd,
                gas_used=gas_used,
                gas_cost_usd=gas_cost_usd,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Execution failed after {execution_time_ms:.0f}ms: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms,
            )

    async def _build_arbitrage_transaction(
        self,
        pool1: DexPool,
        pool2: DexPool,
        trade_amount: Decimal,
    ) -> TxParams:
        """
        Build transaction for 2-leg arbitrage.

        For production use, this should call your arbitrage contract
        that executes both swaps atomically.

        Args:
            pool1: First pool
            pool2: Second pool
            trade_amount: Trade amount

        Returns:
            Transaction parameters
        """
        # Get current gas prices
        gas_price = await self._get_gas_price()

        # Build transaction
        # NOTE: This is a placeholder - you need to implement your contract call
        tx: TxParams = {
            "from": self.account.address,
            "to": self.router_address or pool1.pair_addr,
            "value": Wei(0),
            "gas": 250000,  # Estimated gas limit for 2-leg arb
            "gasPrice": gas_price,
            "nonce": self.web3.eth.get_transaction_count(self.account.address),
            "chainId": self.web3.eth.chain_id,
            "data": b"",  # TODO: Encode swap calls
        }

        return tx

    async def _get_gas_price(self) -> Wei:
        """Get current gas price with ceiling."""
        current_gas_price = self.web3.eth.gas_price
        max_gas_price = Web3.to_wei(self.config.max_gas_price_gwei, "gwei")

        # Use lower of current or max
        gas_price = min(current_gas_price, max_gas_price)

        logger.debug(
            f"Gas price: {Web3.from_wei(gas_price, 'gwei'):.2f} gwei "
            f"(current: {Web3.from_wei(current_gas_price, 'gwei'):.2f})"
        )

        return gas_price

    async def _submit_flashbots_bundle(self, tx_params: TxParams) -> str:
        """
        Submit transaction via Flashbots (or bloXroute for BSC).

        For production, integrate with:
        - Ethereum: flashbots.net
        - BSC: bloXroute BDN

        Args:
            tx_params: Transaction parameters

        Returns:
            Transaction hash
        """
        # TODO: Sign transaction and submit to Flashbots relay
        # signed_tx = self.account.sign_transaction(tx_params)

        # For now, simulate
        logger.warning("Flashbots not implemented - simulating bundle submission")

        # In production:
        # 1. Build bundle with signed transaction
        # 2. Submit to Flashbots relay
        # 3. Wait for inclusion confirmation
        # 4. Return transaction hash

        return f"0x{'0' * 64}"  # Placeholder

    async def _submit_direct(self, tx_params: TxParams) -> str:
        """
        Submit transaction directly to mempool (NOT MEV-protected).

        WARNING: This exposes you to frontrunning. Only use for testing.

        Args:
            tx_params: Transaction parameters

        Returns:
            Transaction hash
        """
        # Sign transaction
        signed_tx = self.account.sign_transaction(tx_params)

        # Submit to network
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        return self.web3.to_hex(tx_hash)

    async def _wait_for_transaction(self, tx_hash: str, timeout: int = 60) -> Dict:
        """
        Wait for transaction confirmation.

        Args:
            tx_hash: Transaction hash
            timeout: Timeout in seconds

        Returns:
            Transaction receipt

        Raises:
            TimeoutError: If transaction not confirmed within timeout
        """
        start = time.time()

        while time.time() - start < timeout:
            try:
                receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except Exception:
                pass

            await asyncio.sleep(1)

        raise TimeoutError(f"Transaction {tx_hash} not confirmed after {timeout}s")

    def _calculate_gas_cost(self, gas_used: int) -> float:
        """
        Calculate gas cost in USD.

        Args:
            gas_used: Gas units consumed

        Returns:
            Cost in USD
        """
        # Get gas price in wei
        gas_price_wei = self.web3.eth.gas_price

        # Calculate cost in native token (ETH/BNB)
        cost_native = float(Web3.from_wei(gas_price_wei * gas_used, "ether"))

        # Convert to USD (rough estimate)
        # TODO: Get real-time price from oracle
        if self.web3.eth.chain_id == 56:  # BSC
            native_price_usd = 500.0  # BNB price
        else:  # Ethereum
            native_price_usd = 2500.0  # ETH price

        cost_usd = cost_native * native_price_usd

        return cost_usd

    def get_stats(self) -> Dict:
        """Get execution statistics."""
        success_rate = (
            self.executions_successful / self.executions_attempted * 100
            if self.executions_attempted > 0
            else 0.0
        )

        return {
            "executions_attempted": self.executions_attempted,
            "executions_successful": self.executions_successful,
            "success_rate_pct": success_rate,
            "total_profit_usd": self.total_profit_usd,
            "total_gas_cost_usd": self.total_gas_cost_usd,
            "net_profit_usd": self.total_profit_usd - self.total_gas_cost_usd,
        }

    def print_stats(self) -> None:
        """Print execution statistics."""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("  EXECUTION STATISTICS")
        print("=" * 80)
        print(f"  Attempts:        {stats['executions_attempted']}")
        print(f"  Successful:      {stats['executions_successful']}")
        print(f"  Success Rate:    {stats['success_rate_pct']:.1f}%")
        print(f"  Total Profit:    ${stats['total_profit_usd']:.2f}")
        print(f"  Total Gas Cost:  ${stats['total_gas_cost_usd']:.2f}")
        print(f"  Net Profit:      ${stats['net_profit_usd']:.2f}")
        print("=" * 80 + "\n")
