"""
Uniswap V2 style adapter for constant-product AMM pools.

Implements reserve fetching and swap simulation using the x*y=k formula
with fees embedded in the swap calculation.
"""

import asyncio
import time
from decimal import Decimal
from typing import Tuple

from web3 import Web3
from web3.exceptions import Web3Exception

from ..abi import UNISWAP_V2_PAIR_ABI


def fetch_pool(
    web3: Web3, pair_addr: str, max_retries: int = 3
) -> Tuple[str, str, Decimal, Decimal]:
    """
    Fetch token addresses and reserves from a Uniswap V2 style pair.

    Args:
        web3: Web3 instance connected to the chain
        pair_addr: Checksummed address of the pair contract
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Tuple of (token0_addr, token1_addr, reserve0, reserve1)

    Raises:
        Web3Exception: If RPC calls fail after all retries
        ValueError: If pair address is invalid
    """
    if not Web3.is_checksum_address(pair_addr):
        raise ValueError(f"Invalid pair address: {pair_addr}")

    pair = web3.eth.contract(address=pair_addr, abi=UNISWAP_V2_PAIR_ABI)

    last_error = None
    for attempt in range(max_retries):
        try:
            token0 = pair.functions.token0().call()
            token1 = pair.functions.token1().call()
            reserves = pair.functions.getReserves().call()

            r0 = Decimal(reserves[0])
            r1 = Decimal(reserves[1])

            return (
                Web3.to_checksum_address(token0),
                Web3.to_checksum_address(token1),
                r0,
                r1,
            )
        except Exception as e:
            last_error = e
            # Check if it's a rate limit error
            if "429" in str(e) or "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2**attempt
                    time.sleep(wait_time)
                    continue
            # For non-rate-limit errors, fail immediately
            raise Web3Exception(f"Failed to fetch pool {pair_addr}: {e}") from e

    # If we exhausted retries
    raise Web3Exception(
        f"Failed to fetch pool {pair_addr} after {max_retries} retries: {last_error}"
    ) from last_error


async def fetch_pool_async(
    web3: Web3, pair_addr: str, max_retries: int = 3
) -> Tuple[str, str, Decimal, Decimal]:
    """
    Async version: Fetch token addresses and reserves from a Uniswap V2 style pair.

    Runs the synchronous RPC calls in a thread pool to avoid blocking the event loop.
    Includes exponential backoff for rate limit errors.

    Args:
        web3: Web3 instance connected to the chain
        pair_addr: Checksummed address of the pair contract
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Tuple of (token0_addr, token1_addr, reserve0, reserve1)

    Raises:
        Web3Exception: If RPC calls fail after all retries
        ValueError: If pair address is invalid
    """
    if not Web3.is_checksum_address(pair_addr):
        raise ValueError(f"Invalid pair address: {pair_addr}")

    pair = web3.eth.contract(address=pair_addr, abi=UNISWAP_V2_PAIR_ABI)
    last_error = None

    for attempt in range(max_retries):
        try:
            loop = asyncio.get_event_loop()

            # Fetch all data in parallel using thread pool
            token0_task = loop.run_in_executor(None, pair.functions.token0().call)
            token1_task = loop.run_in_executor(None, pair.functions.token1().call)
            reserves_task = loop.run_in_executor(
                None, pair.functions.getReserves().call
            )

            token0, token1, reserves = await asyncio.gather(
                token0_task, token1_task, reserves_task
            )

            r0 = Decimal(reserves[0])
            r1 = Decimal(reserves[1])

            return (
                Web3.to_checksum_address(token0),
                Web3.to_checksum_address(token1),
                r0,
                r1,
            )
        except Exception as e:
            last_error = e
            error_msg = str(e)

            # Check for rate limit errors (common patterns)
            is_rate_limit = (
                "429" in error_msg
                or "Too Many Requests" in error_msg
                or "-32005" in error_msg  # BSC/Ethereum rate limit code
                or "limit exceeded" in error_msg.lower()
            )

            if is_rate_limit and attempt < max_retries - 1:
                # Exponential backoff with jitter: 2s, 4s, 8s
                wait_time = (2 ** (attempt + 1)) + (attempt * 0.5)
                await asyncio.sleep(wait_time)
                continue

            # For non-rate-limit errors or last attempt, raise
            if attempt == max_retries - 1:
                raise Web3Exception(
                    f"Failed to fetch pool {pair_addr} after {max_retries} retries: {error_msg}"
                ) from e

    # Should never reach here, but for type safety
    raise Web3Exception(
        f"Failed to fetch pool {pair_addr}: {last_error}"
    ) from last_error


def swap_out(
    amount_in: Decimal, reserve_in: Decimal, reserve_out: Decimal, fee: Decimal
) -> Decimal:
    """
    Calculate output amount for a V2 swap using constant-product formula.

    Formula (with fee embedded):
        amountInWithFee = amountIn * (1 - fee)
        amountOut = (amountInWithFee * reserveOut) / (reserveIn + amountInWithFee)

    This is the standard x*y=k invariant with fees applied to the input.

    Args:
        amount_in: Input token amount (in native units)
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        fee: Fee as decimal (e.g., 0.003 for 30 bps)

    Returns:
        Output token amount (in native units)

    Raises:
        ValueError: If inputs are invalid (negative, zero reserves, etc.)
    """
    if amount_in <= 0:
        raise ValueError(f"amount_in must be positive: {amount_in}")
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError(
            f"Reserves must be positive: in={reserve_in}, out={reserve_out}"
        )
    if fee < 0 or fee >= 1:
        raise ValueError(f"Fee must be in [0, 1): {fee}")

    # Apply fee to input
    amount_in_with_fee = amount_in * (Decimal(1) - fee)

    # Constant product formula
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee

    return numerator / denominator


def price_quote_in_out(
    amount_in: Decimal, reserve_in: Decimal, reserve_out: Decimal, fee: Decimal
) -> Tuple[Decimal, Decimal]:
    """
    Calculate both output amount and effective price for a V2 swap.

    Args:
        amount_in: Input token amount
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        fee: Fee as decimal

    Returns:
        Tuple of (amount_out, effective_price)
        where effective_price = amount_out / amount_in

    Raises:
        ValueError: If inputs are invalid
    """
    amount_out = swap_out(amount_in, reserve_in, reserve_out, fee)
    price = amount_out / amount_in if amount_in > 0 else Decimal(0)
    return amount_out, price
