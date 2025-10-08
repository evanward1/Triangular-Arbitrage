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

    chain_id: int
    rpc_url_env: str
    private_key_env: str
    base_asset: str
    min_profit_bps: int
    max_slippage_bps: int
    max_gas_gwei: int
    routes: List[RouteConfig]
    tokens: Dict[str, TokenConfig]
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

        return cls(
            chain_id=config_dict["chain_id"],
            rpc_url_env=config_dict["rpc_url_env"],
            private_key_env=config_dict["private_key_env"],
            base_asset=config_dict["base_asset"],
            min_profit_bps=config_dict["min_profit_bps"],
            max_slippage_bps=config_dict["max_slippage_bps"],
            max_gas_gwei=config_dict["max_gas_gwei"],
            routes=routes,
            tokens=tokens,
            use_flashbots=config_dict["use_flashbots"],
            coinbase_tip_gwei=config_dict["coinbase_tip_gwei"],
        )
