"""
Configuration schema for DEX MEV arbitrage module.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class TokenConfig:
    """Token configuration for DEX trading."""

    symbol: str
    address: str
    decimals: int


@dataclass
class RouteConfig:
    """Route configuration for arbitrage paths."""

    base: str
    mid: str
    alt: str
    dex_name: str
    pool_addresses: List[str]


@dataclass
class DEXMEVConfig:
    """Main configuration for DEX MEV arbitrage."""

    # Network configuration
    network: str
    chain_id: int
    rpc_url_env: str
    rpc_primary: str
    rpc_backups: List[str]
    private_key_env: str

    # Trading parameters
    base_asset: str
    min_profit_bps: int
    max_slippage_bps: int  # Legacy field, kept for backward compatibility

    # Slippage caps
    per_leg_slippage_bps: int  # Maximum slippage per individual leg
    cycle_slippage_bps: int  # Maximum total slippage for entire cycle

    # Gas configuration
    max_base_fee_gwei: int
    max_priority_fee_gwei: int
    gas_limit_cap: int

    # Private transaction configuration
    private_tx_enabled: bool
    mev_relay: str
    simulation_rpc: str

    # Trade execution options
    exact_in: bool  # If True, use exactAmountIn, else exactAmountOut
    use_bundle: bool  # If True, submit as bundle instead of single tx

    # Routes and tokens
    routes: List[RouteConfig]
    tokens: Dict[str, TokenConfig]

    # Legacy Flashbots fields (kept for backward compatibility)
    use_flashbots: bool
    coinbase_tip_gwei: int

    @classmethod
    def from_dict(cls, config_dict: dict) -> "DEXMEVConfig":
        """Create config from dictionary."""
        # Parse routes
        routes = []
        for route_data in config_dict.get("routes", []):
            routes.append(
                RouteConfig(
                    base=route_data["base"],
                    mid=route_data["mid"],
                    alt=route_data["alt"],
                    dex_name=route_data["dex_name"],
                    pool_addresses=route_data.get("pool_addresses", []),
                )
            )

        # Parse tokens
        tokens = {}
        for symbol, token_data in config_dict.get("tokens", {}).items():
            tokens[symbol] = TokenConfig(
                symbol=symbol,
                address=token_data["address"],
                decimals=token_data["decimals"],
            )

        # Get values with defaults for backward compatibility
        return cls(
            # Network configuration
            network=config_dict.get("network", "ethereum"),
            chain_id=config_dict["chain_id"],
            rpc_url_env=config_dict.get("rpc_url_env", "RPC_URL"),
            rpc_primary=config_dict.get("rpc_primary", ""),
            rpc_backups=config_dict.get("rpc_backups", []),
            private_key_env=config_dict.get("private_key_env", "PRIVATE_KEY"),
            # Trading parameters
            base_asset=config_dict["base_asset"],
            min_profit_bps=config_dict.get("min_profit_bps", 10),
            max_slippage_bps=config_dict.get("max_slippage_bps", 50),
            # Slippage caps
            per_leg_slippage_bps=config_dict.get("per_leg_slippage_bps", 50),
            cycle_slippage_bps=config_dict.get("cycle_slippage_bps", 100),
            # Gas configuration
            max_base_fee_gwei=config_dict.get("max_base_fee_gwei", 50),
            max_priority_fee_gwei=config_dict.get("max_priority_fee_gwei", 2),
            gas_limit_cap=config_dict.get("gas_limit_cap", 500000),
            # Private transaction configuration
            private_tx_enabled=config_dict.get("private_tx_enabled", False),
            mev_relay=config_dict.get("mev_relay", ""),
            simulation_rpc=config_dict.get("simulation_rpc", ""),
            # Trade execution options
            exact_in=config_dict.get("exact_in", True),
            use_bundle=config_dict.get("use_bundle", False),
            # Routes and tokens
            routes=routes,
            tokens=tokens,
            # Legacy Flashbots fields
            use_flashbots=config_dict.get("use_flashbots", False),
            coinbase_tip_gwei=config_dict.get("coinbase_tip_gwei", 0),
        )
