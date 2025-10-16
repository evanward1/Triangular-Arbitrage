"""
Configuration loading and validation for DEX arbitrage scanner.
"""

import os
from decimal import Decimal
from typing import Any, Dict, List, Optional

import yaml


class ConfigError(Exception):
    """Raised when config is invalid or missing required fields."""

    pass


class DexConfig:
    """
    Parsed and validated configuration for DEX paper trading.

    Attributes:
        rpc_url: HTTP(S) RPC endpoint
        poll_sec: Seconds between scans
        once: If True, run single scan and exit
        usd_token: Symbol of quote token (e.g., "USDC")
        max_position_usd: Max position size in USD
        price_safety_margin_pct: Safety margin as percent (e.g., 0.02 for 0.02%)
        apply_safety_per_leg: If True, multiply safety by number of legs
        threshold_net_pct: Minimum net profit threshold (%)
        gas_price_gwei: Gas price for informational display
        gas_limit: Gas limit for informational display
        gas_cost_usd_override: If set, subtract this from P&L per cycle
        tokens: Dict of {symbol -> {address, decimals}}
        dexes: List of DEX configs with pairs
    """

    def __init__(self, config_dict: Dict[str, Any]):
        """
        Parse and validate config from dictionary.

        Args:
            config_dict: Loaded YAML config

        Raises:
            ConfigError: If required fields missing or invalid
        """
        # RPC and loop settings
        self.rpc_url: str = self._get_required(config_dict, "rpc_url", str)
        self.poll_sec: int = config_dict.get("poll_sec", 6)
        self.once: bool = config_dict.get("once", False)

        # Trading parameters
        self.usd_token: str = self._get_required(config_dict, "usd_token", str)
        self.max_position_usd: Decimal = Decimal(
            str(config_dict.get("max_position_usd", 1000))
        )

        # Safety margin: parse once as percent, support legacy slippage_bps
        if "price_safety_margin_pct" in config_dict:
            self.price_safety_margin_pct: float = float(
                config_dict["price_safety_margin_pct"]
            )
        elif "slippage_bps" in config_dict:
            # Legacy: convert bps to percent
            self.price_safety_margin_pct: float = config_dict["slippage_bps"] / 100.0
        else:
            # Default: 0.02% (2 bps)
            self.price_safety_margin_pct: float = 0.02

        self.apply_safety_per_leg: bool = config_dict.get("apply_safety_per_leg", False)
        self.threshold_net_pct: float = config_dict.get("threshold_net_pct", 0.0)

        # Gas settings (informational)
        self.gas_price_gwei: float = config_dict.get("gas_price_gwei", 0.5)
        self.gas_limit: int = config_dict.get("gas_limit", 220_000)
        self.gas_cost_usd_override: Optional[float] = config_dict.get(
            "gas_cost_usd_override"
        )

        # Tokens (optional if using dynamic pool discovery)
        tokens_raw = config_dict.get("tokens", {})
        self.tokens: Dict[str, Dict[str, Any]] = self._parse_tokens(tokens_raw)

        # Validate USD token exists (only if tokens are specified)
        if self.tokens and self.usd_token not in self.tokens:
            raise ConfigError(
                f"usd_token '{self.usd_token}' not found in tokens config"
            )

        # Dynamic pool discovery config
        self.dynamic_pools: Optional[Dict[str, Any]] = self._parse_dynamic_pools(
            config_dict.get("dynamic_pools", {})
        )

        # DEXes (static config - optional if using dynamic pools)
        dexes_raw = config_dict.get("dexes", [])
        self.dexes: List[Dict[str, Any]] = self._parse_dexes(dexes_raw)

        # Validate at least one DEX or dynamic pools enabled
        if not self.dexes and not (
            self.dynamic_pools and self.dynamic_pools.get("enabled")
        ):
            raise ConfigError(
                "Either static DEXes or dynamic_pools.enabled must be configured"
            )

    @staticmethod
    def _get_required(d: Dict, key: str, expected_type: type) -> Any:
        """Get required config field with type validation."""
        if key not in d:
            raise ConfigError(f"Missing required config field: {key}")
        val = d[key]
        if not isinstance(val, expected_type):
            raise ConfigError(
                f"Config field '{key}' must be {expected_type.__name__}, got {type(val).__name__}"
            )
        return val

    @staticmethod
    def _parse_tokens(tokens_raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Parse and validate tokens config."""
        tokens = {}
        for symbol, info in tokens_raw.items():
            if not isinstance(info, dict):
                raise ConfigError(f"Token '{symbol}' config must be a dict")
            if "address" not in info:
                raise ConfigError(f"Token '{symbol}' missing 'address'")
            if "decimals" not in info:
                raise ConfigError(f"Token '{symbol}' missing 'decimals'")

            tokens[symbol] = {
                "address": info["address"],
                "decimals": int(info["decimals"]),
            }
        return tokens

    @staticmethod
    def _parse_dexes(dexes_raw: List[Any]) -> List[Dict[str, Any]]:
        """Parse and validate DEXes config."""
        dexes = []
        for i, dex in enumerate(dexes_raw):
            if not isinstance(dex, dict):
                raise ConfigError(f"DEX config {i} must be a dict")

            name = dex.get("name")
            if not name:
                raise ConfigError(f"DEX config {i} missing 'name'")

            kind = dex.get("kind", "v2")
            if kind not in ["v2", "v3"]:
                raise ConfigError(
                    f"DEX '{name}' has invalid kind '{kind}' (must be v2 or v3)"
                )

            fee_bps = dex.get("fee_bps")
            if fee_bps is None:
                raise ConfigError(f"DEX '{name}' missing 'fee_bps'")

            pairs_raw = dex.get("pairs", [])
            if not isinstance(pairs_raw, list):
                raise ConfigError(f"DEX '{name}' pairs must be a list")

            pairs = []
            for j, pair in enumerate(pairs_raw):
                if not isinstance(pair, dict):
                    raise ConfigError(f"DEX '{name}' pair {j} must be a dict")

                pair_name = pair.get("name")
                pair_addr = pair.get("address")
                base = pair.get("base")
                quote = pair.get("quote")

                if not all([pair_name, pair_addr, base, quote]):
                    raise ConfigError(
                        f"DEX '{name}' pair {j} missing required fields (name, address, base, quote)"
                    )

                pairs.append(
                    {
                        "name": pair_name,
                        "address": pair_addr,
                        "base": base,
                        "quote": quote,
                    }
                )

            dexes.append(
                {
                    "name": name,
                    "kind": kind,
                    "fee_bps": int(fee_bps),
                    "pairs": pairs,
                }
            )

        return dexes

    @staticmethod
    def _parse_dynamic_pools(dynamic_raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse and validate dynamic pool discovery config.

        Args:
            dynamic_raw: Dynamic pools config dict

        Returns:
            Parsed config or None if not enabled

        Raises:
            ConfigError: If config is invalid
        """
        if not dynamic_raw or not dynamic_raw.get("enabled"):
            return None

        config = {
            "enabled": True,
            "min_liquidity_usd": float(dynamic_raw.get("min_liquidity_usd", 10000)),
            "max_pools_per_dex": dynamic_raw.get("max_pools_per_dex"),
            "max_scan_pools": dynamic_raw.get("max_scan_pools"),
            "factories": [],
        }

        # Parse factory addresses
        factories_raw = dynamic_raw.get("factories", [])
        if not isinstance(factories_raw, list):
            raise ConfigError("dynamic_pools.factories must be a list")

        for i, factory in enumerate(factories_raw):
            if not isinstance(factory, dict):
                raise ConfigError(f"Factory config {i} must be a dict")

            name = factory.get("name")
            address = factory.get("address")
            fee_bps = factory.get("fee_bps")

            if not name:
                raise ConfigError(f"Factory config {i} missing 'name'")
            if not address:
                raise ConfigError(f"Factory config {i} missing 'address'")
            if fee_bps is None:
                raise ConfigError(f"Factory config {i} missing 'fee_bps'")

            config["factories"].append(
                {
                    "name": name,
                    "address": address,
                    "fee_bps": int(fee_bps),
                }
            )

        if not config["factories"]:
            raise ConfigError("dynamic_pools enabled but no factories configured")

        return config

    @property
    def slippage_pct(self) -> float:
        """Alias for price_safety_margin_pct (backward compatibility)."""
        return self.price_safety_margin_pct

    @property
    def slippage_bps(self) -> float:
        """Safety margin in basis points (for backward compatibility)."""
        return self.price_safety_margin_pct * 100.0

    @property
    def slippage_decimal(self) -> Decimal:
        """Safety margin as Decimal (backward compatibility)."""
        return Decimal(str(self.price_safety_margin_pct)) / Decimal("100")

    @property
    def safety_bps(self) -> float:
        """Safety margin in basis points (for backward compatibility)."""
        return self.price_safety_margin_pct * 100.0

    @property
    def safety_decimal(self) -> Decimal:
        """Safety margin as Decimal for precise math."""
        return Decimal(str(self.price_safety_margin_pct)) / Decimal("100")

    @property
    def gas_pct(self) -> float:
        """Gas cost as percentage of position (if override set)."""
        if self.gas_cost_usd_override is None:
            return 0.0
        return (self.gas_cost_usd_override / float(self.max_position_usd)) * 100.0

    @property
    def breakeven_pct(self) -> float:
        """
        Breakeven profit threshold accounting for safety margin and gas.
        Gross profit must exceed this to meet net threshold.
        """
        return self.threshold_net_pct + self.price_safety_margin_pct + self.gas_pct


def load_config(config_path: str) -> DexConfig:
    """
    Load and validate config from YAML file.

    Args:
        config_path: Path to config YAML file

    Returns:
        Validated DexConfig instance

    Raises:
        ConfigError: If config invalid or file not found
        yaml.YAMLError: If YAML parsing fails
    """
    if not os.path.exists(config_path):
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML: {e}") from e

    if not isinstance(config_dict, dict):
        raise ConfigError("Config file must contain a YAML dictionary")

    return DexConfig(config_dict)
