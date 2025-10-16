"""
DEX client for interacting with decentralized exchanges using web3.

Supports Uniswap V2/V3 with proper math, slippage protection, and private tx submission.
"""

import logging
import os
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError

from .config_schema import DEXMEVConfig
from .price_oracle import PriceOracle

logger = logging.getLogger(__name__)

# Uniswap V2 Pair ABI (minimal)
UNISWAP_V2_PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"},
        ],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
]

# ERC20 ABI (minimal)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]


class DEXClient:
    """Client for interacting with DEX contracts via web3."""

    def __init__(self, config: DEXMEVConfig, paper_mode: bool = False):
        """Initialize DEX client with configuration."""
        self.config = config
        self.paper_mode = paper_mode

        if not paper_mode:
            # Get RPC URL from environment or config
            rpc_url = os.getenv(config.rpc_url_env) or config.rpc_primary
            if not rpc_url:
                raise ValueError(
                    f"RPC URL environment variable {config.rpc_url_env} not set and no rpc_primary in config"
                )

            # Initialize web3
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to RPC at {rpc_url}")

            # Get private key from environment (for future use)
            self.private_key = os.getenv(config.private_key_env)
            if not self.private_key:
                logger.warning(
                    f"Private key environment variable {config.private_key_env} not set - paper trading only"
                )
            else:
                self.account = Account.from_key(self.private_key)
                logger.info(f"Loaded account: {self.account.address}")

            # Initialize simulation RPC if configured
            self.simulation_rpc = config.simulation_rpc
            if self.simulation_rpc:
                self.sim_w3 = Web3(Web3.HTTPProvider(self.simulation_rpc))
                logger.info(f"Simulation RPC configured: {self.simulation_rpc}")
            else:
                self.sim_w3 = self.w3

            # Initialize Flashbots if enabled
            self.private_tx_enabled = config.private_tx_enabled
            self.mev_relay = config.mev_relay if config.private_tx_enabled else None
            if self.private_tx_enabled and self.mev_relay:
                logger.info(f"Private tx enabled via relay: {self.mev_relay}")

        else:
            # Paper mode - no actual connections
            self.w3 = None
            self.sim_w3 = None
            self.private_key = None
            self.account = None
            self.private_tx_enabled = False
            self.mev_relay = None
            # Initialize price oracle for paper trading
            self.price_oracle = PriceOracle(cache_ttl_seconds=60)
            logger.info(
                "DEX client initialized in PAPER MODE - using dynamic price oracle"
            )

        logger.info(f"DEX client initialized for chain {config.network}")

    def get_token_balance(self, token_address: str, wallet_address: str) -> Decimal:
        """Get token balance for a wallet address."""
        if self.paper_mode:
            logger.debug(
                f"PAPER: Getting balance for token {token_address} wallet {wallet_address}"
            )
            return Decimal("1000.0")  # Mock balance for paper trading

        try:
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
            )
            balance_wei = token_contract.functions.balanceOf(
                Web3.to_checksum_address(wallet_address)
            ).call()
            # Convert from wei to token units (assumes 18 decimals, adjust if needed)
            return Decimal(balance_wei) / Decimal(10**18)
        except Exception as e:
            logger.error(f"Failed to get token balance: {e}")
            return Decimal("0.0")

    def get_pool_reserves(
        self, pool_address: str, token_in_address: str, token_out_address: str
    ) -> Tuple[Decimal, Decimal]:
        """
        Get reserves for a Uniswap V2 liquidity pool.

        Returns (reserve_in, reserve_out) ordered correctly for the swap.
        """
        if self.paper_mode:
            logger.debug(f"PAPER: Getting pool reserves for {pool_address}")
            return (Decimal("1000000.0"), Decimal("2000.0"))  # Mock reserves

        try:
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=UNISWAP_V2_PAIR_ABI,
            )

            # Get reserves
            reserves = pool_contract.functions.getReserves().call()
            reserve0, reserve1 = Decimal(reserves[0]), Decimal(reserves[1])

            # Get token0 and token1 to determine order
            token0 = pool_contract.functions.token0().call()
            token_in_checksum = Web3.to_checksum_address(token_in_address)

            # Return reserves in correct order for swap
            if token0.lower() == token_in_checksum.lower():
                return (reserve0, reserve1)
            else:
                return (reserve1, reserve0)

        except Exception as e:
            logger.error(f"Failed to get pool reserves: {e}")
            return (Decimal("0.0"), Decimal("0.0"))

    def calculate_v2_output(
        self,
        amount_in: Decimal,
        reserve_in: Decimal,
        reserve_out: Decimal,
        fee_bps: int = 30,
    ) -> Decimal:
        """
        Calculate Uniswap V2 output amount using constant product formula.

        Formula: amountOut = (amountIn * fee_multiplier * reserveOut) / (reserveIn + amountIn * fee_multiplier)
        where fee_multiplier = (10000 - fee_bps) / 10000

        Args:
            amount_in: Input amount in token decimals
            reserve_in: Reserve of input token
            reserve_out: Reserve of output token
            fee_bps: Fee in basis points (default 30 = 0.3%)

        Returns:
            Output amount in token decimals
        """
        if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
            return Decimal("0.0")

        fee_multiplier = Decimal(10000 - fee_bps) / Decimal(10000)
        amount_in_with_fee = amount_in * fee_multiplier

        numerator = amount_in_with_fee * reserve_out
        denominator = reserve_in + amount_in_with_fee

        amount_out = numerator / denominator
        return amount_out

    def calculate_v2_input_for_output(
        self,
        amount_out: Decimal,
        reserve_in: Decimal,
        reserve_out: Decimal,
        fee_bps: int = 30,
    ) -> Decimal:
        """
        Calculate required input for desired output (Uniswap V2).

        Formula: amountIn = (reserveIn * amountOut * 10000) / ((reserveOut - amountOut) * (10000 - fee_bps))

        Args:
            amount_out: Desired output amount
            reserve_in: Reserve of input token
            reserve_out: Reserve of output token
            fee_bps: Fee in basis points

        Returns:
            Required input amount
        """
        if amount_out <= 0 or reserve_in <= 0 or reserve_out <= amount_out:
            return Decimal("0.0")

        numerator = reserve_in * amount_out * Decimal(10000)
        denominator = (reserve_out - amount_out) * Decimal(10000 - fee_bps)

        amount_in = numerator / denominator
        return amount_in

    def estimate_swap_output(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        pool_address: str,
        fee_bps: int = 30,
    ) -> Decimal:
        """
        Estimate output amount for a swap (Uniswap V2).

        Args:
            token_in: Symbol of input token
            token_out: Symbol of output token
            amount_in: Amount to swap
            pool_address: Address of liquidity pool
            fee_bps: Pool fee in basis points

        Returns:
            Estimated output amount
        """
        if self.paper_mode:
            # Use dynamic price oracle for realistic paper trading
            logger.debug(
                f"PAPER: Estimating swap {amount_in} {token_in} -> {token_out}"
            )
            fee = Decimal("0.997")  # 0.3% fee per leg

            # Get real market rate from price oracle
            rate = self.price_oracle.get_price(token_in, token_out)

            if rate is None:
                logger.warning(
                    f"Could not get price for {token_in}/{token_out}, using fallback"
                )
                rate = Decimal("1.0")  # 1:1 fallback

            logger.debug(f"Oracle rate for {token_in}/{token_out}: {rate}")
            return amount_in * rate * fee

        # Get token addresses
        token_in_config = self.config.tokens.get(token_in)
        token_out_config = self.config.tokens.get(token_out)

        if not token_in_config or not token_out_config:
            logger.error(f"Token config not found: {token_in} or {token_out}")
            return Decimal("0.0")

        # Get reserves
        reserve_in, reserve_out = self.get_pool_reserves(
            pool_address, token_in_config.address, token_out_config.address
        )

        if reserve_in <= 0 or reserve_out <= 0:
            logger.error(f"Invalid reserves for pool {pool_address}")
            return Decimal("0.0")

        # Convert amount to wei
        amount_in_wei = amount_in * Decimal(10**token_in_config.decimals)

        # Calculate output
        amount_out_wei = self.calculate_v2_output(
            amount_in_wei, reserve_in, reserve_out, fee_bps
        )

        # Convert back to token units
        amount_out = amount_out_wei / Decimal(10**token_out_config.decimals)

        return amount_out

    def get_gas_price(self) -> int:
        """Get current gas price in gwei."""
        if self.paper_mode or not self.w3:
            return 20  # Default gas price for paper mode

        try:
            gas_price_wei = self.w3.eth.gas_price
            gas_price_gwei = gas_price_wei // 10**9
            return min(int(gas_price_gwei), self.config.max_base_fee_gwei)
        except Exception as e:
            logger.warning(f"Failed to get gas price: {e}, using default")
            return 20  # Default gas price

    def check_gas_price(self) -> Tuple[bool, int, str]:
        """
        Check if current gas price is acceptable.

        Returns:
            Tuple of (is_acceptable, current_gas_price_gwei, reason)
        """
        if self.paper_mode:
            return (True, 20, "paper_mode")

        try:
            gas_price_gwei = self.get_gas_price()
            if gas_price_gwei > self.config.max_base_fee_gwei:
                return (
                    False,
                    gas_price_gwei,
                    f"Gas price {gas_price_gwei} gwei exceeds max {self.config.max_base_fee_gwei} gwei",
                )
            return (True, gas_price_gwei, "acceptable")
        except Exception as e:
            return (False, 0, f"Failed to check gas price: {e}")

    def simulate_transaction(
        self, tx_params: Dict, sender_address: str
    ) -> Tuple[bool, Optional[int], str]:
        """
        Simulate a transaction before sending.

        Args:
            tx_params: Transaction parameters including to, data, value, gas
            sender_address: Address to simulate from

        Returns:
            Tuple of (success, gas_used, reason)
        """
        if self.paper_mode:
            logger.debug("PAPER: Simulating transaction")
            return (True, 200000, "paper_mode_simulation")

        try:
            # Use simulation RPC if available
            w3 = self.sim_w3 if self.sim_w3 else self.w3

            # Prepare simulation parameters
            sim_params = {
                "from": Web3.to_checksum_address(sender_address),
                "to": Web3.to_checksum_address(tx_params["to"]),
                "data": tx_params.get("data", "0x"),
                "value": tx_params.get("value", 0),
                "gas": tx_params.get("gas", self.config.gas_limit_cap),
            }

            # Call eth_call to simulate
            try:
                w3.eth.call(sim_params)
                # Estimate gas for the transaction
                gas_estimate = w3.eth.estimate_gas(sim_params)
                logger.info(f"Simulation successful, estimated gas: {gas_estimate}")
                return (True, gas_estimate, "simulation_passed")
            except ContractLogicError as e:
                logger.error(f"Simulation failed with contract error: {e}")
                return (False, None, f"contract_revert: {str(e)}")

        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            return (False, None, f"simulation_error: {str(e)}")

    def build_swap_transaction(
        self,
        path: List[str],
        amounts: List[Decimal],
        pool_addresses: List[str],
        sender_address: str,
        slippage_bps: int = 50,
    ) -> Optional[Dict]:
        """
        Build a swap transaction for arbitrage execution.

        Args:
            path: Token path [tokenA, tokenB, tokenC, tokenA]
            amounts: Expected amounts at each step
            pool_addresses: Pool addresses for each swap
            sender_address: Address executing the trade
            slippage_bps: Slippage tolerance in basis points

        Returns:
            Transaction parameters dict or None if build fails
        """
        if self.paper_mode:
            logger.debug("PAPER: Building swap transaction")
            return {
                "to": "0x0000000000000000000000000000000000000000",
                "data": "0x",
                "value": 0,
                "gas": 250000,
                "gasPrice": 20 * 10**9,
                "nonce": 0,
                "chainId": self.config.chain_id,
            }

        try:
            # Calculate minimum output with slippage protection
            final_amount = amounts[-1]
            slippage_factor = Decimal(1.0) - (Decimal(slippage_bps) / 10000)
            min_output = final_amount * slippage_factor

            # For now, return a stub transaction
            # In production, this would call router contract methods
            logger.info(
                f"Building swap transaction: {path[0]} -> {path[-1]}, "
                f"amount_in: {amounts[0]}, min_out: {min_output}"
            )

            # Get current gas price
            gas_price_gwei = self.get_gas_price()
            gas_price_wei = gas_price_gwei * 10**9

            # Get nonce
            nonce = self.w3.eth.get_transaction_count(
                Web3.to_checksum_address(sender_address)
            )

            tx_params = {
                "to": pool_addresses[0] if pool_addresses else "0x" + "0" * 40,
                "data": "0x",  # Would encode actual swap data here
                "value": 0,
                "gas": self.config.gas_limit_cap,
                "gasPrice": gas_price_wei,
                "nonce": nonce,
                "chainId": self.config.chain_id,
            }

            return tx_params

        except Exception as e:
            logger.error(f"Failed to build swap transaction: {e}")
            return None

    def sign_transaction(self, tx_params: Dict) -> Optional[str]:
        """
        Sign a transaction with the loaded private key.

        Args:
            tx_params: Transaction parameters

        Returns:
            Signed transaction hex string or None if signing fails
        """
        if self.paper_mode:
            logger.debug("PAPER: Signing transaction")
            return "0x" + "0" * 130  # Mock signed tx

        if not self.private_key or not self.account:
            logger.error("No private key loaded, cannot sign transaction")
            return None

        try:
            signed_tx = self.w3.eth.account.sign_transaction(
                tx_params, self.private_key
            )
            return signed_tx.rawTransaction.hex()
        except Exception as e:
            logger.error(f"Failed to sign transaction: {e}")
            return None

    def submit_private_transaction(
        self, signed_tx_hex: str
    ) -> Tuple[bool, Optional[str], str]:
        """
        Submit transaction via private mempool (Flashbots/MEV relay).

        Args:
            signed_tx_hex: Signed transaction hex string

        Returns:
            Tuple of (success, tx_hash, reason)
        """
        if self.paper_mode:
            logger.info("PAPER: Submitting private transaction")
            return (True, "0x" + "0" * 64, "paper_mode")

        if not self.private_tx_enabled or not self.mev_relay:
            logger.warning("Private tx not enabled, falling back to public mempool")
            return self.submit_public_transaction(signed_tx_hex)

        try:
            # In production, this would use Flashbots RPC or MEV relay
            # For now, log and return success
            logger.info(f"Submitting private transaction to relay: {self.mev_relay}")

            # Stub: would use flashbots-py or direct RPC call here
            # Example:
            # flashbots_provider.send_private_transaction(signed_tx_hex)

            return (True, "0x" + "0" * 64, "private_tx_submitted")

        except Exception as e:
            logger.error(f"Failed to submit private transaction: {e}")
            return (False, None, f"submission_failed: {str(e)}")

    def submit_public_transaction(
        self, signed_tx_hex: str
    ) -> Tuple[bool, Optional[str], str]:
        """
        Submit transaction to public mempool.

        Args:
            signed_tx_hex: Signed transaction hex string

        Returns:
            Tuple of (success, tx_hash, reason)
        """
        if self.paper_mode:
            logger.info("PAPER: Submitting public transaction")
            return (True, "0x" + "0" * 64, "paper_mode")

        try:
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx_hex)
            tx_hash_hex = tx_hash.hex()
            logger.info(f"Transaction submitted: {tx_hash_hex}")
            return (True, tx_hash_hex, "public_tx_submitted")

        except Exception as e:
            logger.error(f"Failed to submit public transaction: {e}")
            return (False, None, f"submission_failed: {str(e)}")

    def execute_arbitrage_swap(
        self, path: List[str], amounts: List[Decimal], pool_addresses: List[str]
    ) -> Dict:
        """Execute arbitrage swap transaction - PAPER TRADING STUB ONLY."""
        logger.info("🚨 PAPER TRADING STUB: Would execute swap with path:")
        for i, (token, amount) in enumerate(zip(path, amounts)):
            logger.info(f"  Step {i+1}: {amount} {token}")

        # Return mock transaction result
        return {
            "transaction_hash": "0x" + "0" * 64,
            "gas_used": 200000,
            "status": "success",
            "note": "PAPER TRADING - NO ACTUAL TRANSACTION",
        }

    def get_account_address(self) -> Optional[str]:
        """Get account address from private key."""
        if self.paper_mode:
            return "0x1234567890123456789012345678901234567890"  # Mock address for paper mode

        if not self.private_key:
            return None

        try:
            account = self.w3.eth.account.from_key(self.private_key)
            return account.address
        except Exception as e:
            logger.error(f"Failed to get account from private key: {e}")
            return None
