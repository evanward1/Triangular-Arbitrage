"""
Uniswap V2 style adapter for constant-product AMM pools.

Implements reserve fetching and swap simulation using the x*y=k formula
with fees embedded in the swap calculation.
"""

import asyncio
from decimal import Decimal
from typing import Tuple

from web3 import Web3
from web3.exceptions import Web3Exception

from ..abi import UNISWAP_V2_PAIR_ABI


def fetch_pool(web3: Web3, pair_addr: str) -> Tuple[str, str, Decimal, Decimal]:
    """
    Fetch token addresses and reserves from a Uniswap V2 style pair.

    Args:
        web3: Web3 instance connected to the chain
        pair_addr: Checksummed address of the pair contract

    Returns:
        Tuple of (token0_addr, token1_addr, reserve0, reserve1)

    Raises:
        Web3Exception: If RPC calls fail
        ValueError: If pair address is invalid
    """
    if not Web3.is_checksum_address(pair_addr):
        raise ValueError(f"Invalid pair address: {pair_addr}")

    pair = web3.eth.contract(address=pair_addr, abi=UNISWAP_V2_PAIR_ABI)

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
        raise Web3Exception(f"Failed to fetch pool {pair_addr}: {e}") from e


async def fetch_pool_async(
    web3: Web3, pair_addr: str
) -> Tuple[str, str, Decimal, Decimal]:
    """
    Async version: Fetch token addresses and reserves from a Uniswap V2 style pair.

    Runs the synchronous RPC calls in a thread pool to avoid blocking the event loop.

    Args:
        web3: Web3 instance connected to the chain
        pair_addr: Checksummed address of the pair contract

    Returns:
        Tuple of (token0_addr, token1_addr, reserve0, reserve1)

    Raises:
        Web3Exception: If RPC calls fail
        ValueError: If pair address is invalid
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_pool, web3, pair_addr)


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
