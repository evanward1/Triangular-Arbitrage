"""
Core data types for DEX arbitrage scanning.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

DexKind = Literal["v2", "v3"]


@dataclass
class DexPool:
    """
    Represents a DEX liquidity pool with normalized reserves.

    Attributes:
        dex: Name of the DEX (e.g., "uniswap", "sushi")
        kind: Type of AMM ("v2" for constant-product, "v3" for concentrated liquidity)
        pair_name: Human-readable pair name (e.g., "WETH/USDC")
        pair_addr: On-chain address of the pair contract
        token0: Checksum address of token0
        token1: Checksum address of token1
        r0: Reserve amount for token0 (in native units)
        r1: Reserve amount for token1 (in native units)
        fee: Fee as decimal (e.g., 0.003 for 30 bps)
        base_symbol: Base token symbol from config
        quote_symbol: Quote token symbol from config
    """

    dex: str
    kind: DexKind
    pair_name: str
    pair_addr: str
    token0: str
    token1: str
    r0: Decimal
    r1: Decimal
    fee: Decimal
    base_symbol: str
    quote_symbol: str


@dataclass
class ArbRow:
    """
    Represents a single arbitrage opportunity result.

    Attributes:
        cycle: Human-readable cycle description (e.g., "USDC -> WETH -> USDC")
        dexA: Name of first DEX in the cycle
        dexB: Name of second DEX in the cycle
        pair: Pair being arbitraged (e.g., "WETH/USDC")
        gross_pct: Gross profit percentage (before slippage & gas)
        net_pct: Net profit percentage (after slippage & gas)
        pnl_usd: Absolute P&L in USD
    """

    cycle: str
    dexA: str
    dexB: str
    pair: str
    gross_pct: float
    net_pct: float
    pnl_usd: float
