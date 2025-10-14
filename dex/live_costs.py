"""
Live cost computation for DEX arbitrage opportunities.

Queries on-chain data for:
- Pool fee tiers (Uniswap V3)
- Liquidity reserves (Uniswap V2/Sushi)
- Gas prices and estimates
- Price impact calculations
"""

from typing import Any, Dict, List, Optional

# Minimal ABIs for on-chain reads
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
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]

UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Default fee map for V2-style DEXes (bps)
DEFAULT_V2_FEE_MAP = {
    "uniswap_v2": 30.0,  # 0.30%
    "sushiswap": 30.0,  # 0.30%
    "pancakeswap": 25.0,  # 0.25%
    "quickswap": 30.0,  # 0.30%
    "default": 30.0,  # 0.30% fallback
}


def read_v3_fee_bps(web3, pool_addr: str) -> float:
    """
    Read fee tier from Uniswap V3 pool contract.

    Args:
        web3: Web3 instance
        pool_addr: Pool contract address

    Returns:
        Fee in basis points (e.g., 500 -> 5 bps, 3000 -> 30 bps)
    """
    try:
        pool = web3.eth.contract(
            address=web3.to_checksum_address(pool_addr), abi=UNISWAP_V3_POOL_ABI
        )
        fee = pool.functions.fee().call()
        return fee / 100.0  # Convert from pool units (500, 3000, 10000) to bps
    except Exception:
        # Fallback to 30 bps if read fails
        return 30.0


def read_v2_reserves(web3, pair_addr: str) -> tuple:
    """
    Read reserves from Uniswap V2-style pair contract.

    Args:
        web3: Web3 instance
        pair_addr: Pair contract address

    Returns:
        Tuple of (reserve0, reserve1)
    """
    try:
        pair = web3.eth.contract(
            address=web3.to_checksum_address(pair_addr), abi=UNISWAP_V2_PAIR_ABI
        )
        reserves = pair.functions.getReserves().call()
        return reserves[0], reserves[1]
    except Exception:
        # Return dummy reserves if read fails
        return 1000000 * 10**18, 1000000 * 10**18


def price_impact_bps(amount_in: float, reserve_in: float) -> float:
    """
    Calculate price impact for constant product AMM.

    Uses small trade approximation: impact ≈ amount_in / reserve_in

    Args:
        amount_in: Trade amount in token units
        reserve_in: Reserve amount in token units

    Returns:
        Price impact in basis points
    """
    if reserve_in <= 0:
        return 0.0

    impact_fraction = amount_in / reserve_in
    return max(0.0, impact_fraction * 10000.0)


def estimate_gas_pct(
    web3, tx: Dict[str, Any], trade_size_usd: float, eth_usd: float
) -> float:
    """
    Estimate gas cost as percentage of trade size.

    Args:
        web3: Web3 instance
        tx: Transaction dict for estimation
        trade_size_usd: Trade size in USD
        eth_usd: Current ETH price in USD

    Returns:
        Gas cost as percentage
    """
    try:
        gas_price = web3.eth.gas_price
        # Estimate gas or use typical router gas usage
        try:
            gas_used = web3.eth.estimate_gas(tx)
        except Exception:
            gas_used = 180000  # Typical multi-hop swap gas

        gas_eth = (gas_used * gas_price) / 1e18
        gas_usd = gas_eth * eth_usd

        if trade_size_usd <= 0:
            return 0.0

        return (gas_usd / trade_size_usd) * 100.0
    except Exception:
        # Fallback: 0.18% typical gas cost
        return 0.18


def compute_costs_for_route(
    web3: Optional[Any],
    route_legs: List[Dict[str, Any]],
    size_usd: float,
    eth_usd: float = 2000.0,
    token_decimals: Optional[Dict[str, int]] = None,
    v2_fee_bps_map: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Compute all costs for a multi-hop route using live on-chain data.

    Args:
        web3: Web3 instance (if None, uses mock values)
        route_legs: List of route leg dicts with pool metadata
        size_usd: Trade size in USD
        eth_usd: Current ETH/USD price
        token_decimals: Map of token symbol to decimals
        v2_fee_bps_map: Custom V2 fee map (uses defaults if None)

    Returns:
        Dict with fee_bps, fee_pct, slip_bps, slip_pct, gas_bps, gas_pct
    """
    if token_decimals is None:
        token_decimals = {"USDC": 6, "USDT": 6, "DAI": 18, "WETH": 18, "WBTC": 8}

    if v2_fee_bps_map is None:
        v2_fee_bps_map = DEFAULT_V2_FEE_MAP

    fee_bps_total = 0.0
    slip_bps_total = 0.0

    # If no web3, use mock values
    if web3 is None:
        fee_bps_total = 30.0 * len(route_legs)  # 0.30% per leg
        slip_bps_total = 2.0  # 0.02% total
        gas_bps = 18.0  # 0.18%
    else:
        for leg in route_legs:
            leg_type = leg.get("type", "v2")
            dex_name = leg.get("dex", "").lower()

            if leg_type == "v3":
                # Read actual V3 fee tier
                pool_addr = leg.get("pool")
                if pool_addr:
                    fee_bps_total += read_v3_fee_bps(web3, pool_addr)
                else:
                    fee_bps_total += 30.0  # Fallback
            else:
                # V2-style: use fee map
                fee_bps_total += v2_fee_bps_map.get(dex_name, v2_fee_bps_map["default"])

            # Calculate slippage from reserves
            pair_addr = leg.get("pair") or leg.get("pool")
            if pair_addr and leg_type == "v2":
                reserve_in, reserve_out = read_v2_reserves(web3, pair_addr)

                # Convert USD trade size to token amount
                token_in = leg.get("token_in", "USDC")
                decimals = token_decimals.get(token_in, 18)
                token_in_usd = leg.get("token_in_usd", 1.0)

                amount_in = (size_usd / token_in_usd) * (10**decimals)
                slip_bps_total += price_impact_bps(amount_in, reserve_in)
            else:
                # Estimate slippage
                slip_bps_total += leg.get("slip_bps_est", 0.5)

        # Estimate gas cost
        dummy_tx = {"from": "0x0000000000000000000000000000000000000000", "value": 0}
        gas_pct = estimate_gas_pct(web3, dummy_tx, size_usd, eth_usd)
        gas_bps = gas_pct * 100.0

    return {
        "fee_bps": fee_bps_total,
        "fee_pct": fee_bps_total / 100.0,
        "slip_bps": slip_bps_total,
        "slip_pct": slip_bps_total / 100.0,
        "gas_bps": gas_bps,
        "gas_pct": gas_bps / 100.0,
    }
