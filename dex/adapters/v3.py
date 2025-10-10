"""
Uniswap V3 style adapter (STUB for future implementation).

V3 uses concentrated liquidity and requires calling the Quoter contract
to simulate swaps. This module provides the interface but is not yet
fully implemented.
"""

from decimal import Decimal

from web3 import Web3


def quote_exact_input(
    web3: Web3, quoter_addr: str, path_bytes: bytes, amount_in: Decimal
) -> Decimal:
    """
    Get a quote for an exact input swap on Uniswap V3.

    This is a STUB. Full implementation requires:
    1. Encoding the swap path (tokenIn -> fee -> tokenOut)
    2. Calling Quoter.quoteExactInput() with the encoded path
    3. Handling multi-hop paths if needed
    4. Managing gas estimation and simulation failures

    Args:
        web3: Web3 instance
        quoter_addr: Address of the Quoter contract (e.g., QuoterV2)
        path_bytes: Encoded path (token addresses + fees)
        amount_in: Input amount in native units

    Returns:
        Expected output amount in native units

    Raises:
        NotImplementedError: This is a stub for future development

    TODO:
        - Implement path encoding (abi.encodePacked equivalent)
        - Handle quoter gas limits and error cases
        - Add support for QuoterV2 with additional parameters
        - Add price impact and slippage calculations
    """
    raise NotImplementedError(
        "Uniswap V3 support is not yet implemented. "
        "To add V3:\n"
        "1. Encode swap path using abi.encodePacked(tokenIn, fee, tokenOut)\n"
        "2. Call Quoter.quoteExactInput(path, amountIn)\n"
        "3. Handle revert cases and gas estimation\n"
        "4. Add multi-hop path support if needed"
    )


def encode_v3_path(tokens: list[str], fees: list[int]) -> bytes:
    """
    Encode a Uniswap V3 swap path.

    V3 paths are encoded as: token0 (20 bytes) | fee0 (3 bytes) | token1 (20 bytes) | ...

    Args:
        tokens: List of token addresses (checksummed)
        fees: List of fee tiers in bps (e.g., [3000] for 0.3%)

    Returns:
        Encoded path as bytes

    Raises:
        NotImplementedError: This is a stub for future development

    TODO:
        - Implement packed encoding matching Solidity's abi.encodePacked
        - Validate token addresses and fee tiers
        - Add support for multi-hop paths
    """
    raise NotImplementedError(
        "V3 path encoding is not yet implemented. "
        "Use eth_abi.packed or manual byte concatenation."
    )


# Common V3 fee tiers (in basis points)
V3_FEE_TIERS = {
    "LOW": 500,  # 0.05%
    "MEDIUM": 3000,  # 0.30%
    "HIGH": 10000,  # 1.00%
}
