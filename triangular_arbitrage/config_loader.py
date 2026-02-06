"""
Configuration loading and normalization for triangular arbitrage system.

Provides a centralized way to load, validate, and normalize configuration
files with proper defaults and read-only access.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field

from .exceptions import ConfigurationError, ValidationError
from .config_schema import validate_strategy_config


@dataclass(frozen=True)
class ExecutionConfig:
    """Normalized execution configuration."""

    mode: str = "live"
    paper_balance_btc: float = 1.0
    paper_balance_eth: float = 10.0
    paper_balance_usdt: float = 10000.0
    backtest_start_date: Optional[str] = None
    backtest_end_date: Optional[str] = None
    backtest_data_dir: Optional[str] = None


@dataclass(frozen=True)
class RiskConfig:
    """Normalized risk control configuration."""

    max_position_size: float = 0.1
    max_daily_loss: float = 0.05
    max_drawdown: float = 0.1
    position_timeout: int = 300
    enable_kill_switch: bool = True
    max_open_positions: int = 3


@dataclass(frozen=True)
class ObservabilityConfig:
    """Normalized observability configuration."""

    enabled: bool = True
    prometheus_port: int = 8000
    grafana_port: int = 3000
    enable_detailed_metrics: bool = False
    metric_retention_days: int = 30


@dataclass(frozen=True)
class ExchangeConfig:
    """Normalized exchange configuration."""

    name: str
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    testnet: bool = True
    rate_limit: int = 10
    timeout: int = 30


@dataclass(frozen=True)
class StrategyRuntimeConfig:
    """Immutable runtime configuration object."""

    name: str
    exchange: ExchangeConfig
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    symbols: list = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "ETH/BTC"])
    min_profit_threshold: float = 0.001
    max_trade_amount_btc: float = 0.1
    fee_rate: float = 0.001
    volatility_window_size: Optional[int] = None
    sigma_multiplier: Optional[float] = None


def load_yaml_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Load and parse YAML configuration file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f)

        if config_dict is None:
            raise ConfigurationError(f"Empty configuration file: {config_path}")

        return config_dict
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {e}")
    except Exception as e:
        raise ConfigurationError(f"Failed to load config {config_path}: {e}")


def _normalize_execution_config(config_dict: Dict[str, Any]) -> ExecutionConfig:
    """Normalize execution configuration with defaults."""
    exec_config = config_dict.get("execution", {})

    # Handle legacy keys and aliases
    mode = exec_config.get("mode", exec_config.get("execution_mode", "live"))

    # Extract values from nested paper config or use defaults
    paper_balance_btc = 1.0
    paper_balance_eth = 10.0
    paper_balance_usdt = 10000.0

    if mode == "paper" and "paper" in exec_config:
        paper_config = exec_config["paper"]
        initial_balances = paper_config.get("initial_balances", {})
        paper_balance_btc = initial_balances.get("BTC", 1.0)
        paper_balance_eth = initial_balances.get("ETH", 10.0)
        paper_balance_usdt = initial_balances.get("USDT", 10000.0)
    elif mode == "paper":
        # Legacy format - values already extracted during normalization
        paper_balance_btc = exec_config.get("paper_balance_btc", 1.0)
        paper_balance_eth = exec_config.get("paper_balance_eth", 10.0)
        paper_balance_usdt = exec_config.get("paper_balance_usdt", 10000.0)

    # Apply backtest defaults
    backtest_defaults = {}
    if mode == "backtest":
        backtest_defaults = {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2024-01-31",
            "backtest_data_dir": "backtests/data",
        }

    return ExecutionConfig(
        mode=mode,
        paper_balance_btc=paper_balance_btc,
        paper_balance_eth=paper_balance_eth,
        paper_balance_usdt=paper_balance_usdt,
        backtest_start_date=exec_config.get(
            "backtest_start_date", backtest_defaults.get("backtest_start_date")
        ),
        backtest_end_date=exec_config.get(
            "backtest_end_date", backtest_defaults.get("backtest_end_date")
        ),
        backtest_data_dir=exec_config.get(
            "backtest_data_dir", backtest_defaults.get("backtest_data_dir")
        ),
    )


def _normalize_risk_config(config_dict: Dict[str, Any]) -> RiskConfig:
    """Normalize risk configuration with defaults."""
    # After normalization, risk data is in 'risk_controls'
    risk_config = config_dict.get("risk_controls", {})

    return RiskConfig(
        max_position_size=risk_config.get("max_position_size", 0.1),
        max_daily_loss=risk_config.get("max_daily_loss", 0.05),
        max_drawdown=risk_config.get("max_drawdown", 0.1),
        position_timeout=risk_config.get("position_timeout", 300),
        enable_kill_switch=risk_config.get("enable_kill_switch", True),
        max_open_positions=risk_config.get("max_open_positions", 3),
    )


def _normalize_observability_config(config_dict: Dict[str, Any]) -> ObservabilityConfig:
    """Normalize observability configuration with defaults."""
    obs_config = config_dict.get("observability", {})

    return ObservabilityConfig(
        enabled=obs_config.get("enabled", True),
        prometheus_port=obs_config.get("prometheus_port", 8000),
        grafana_port=obs_config.get("grafana_port", 3000),
        enable_detailed_metrics=obs_config.get("enable_detailed_metrics", False),
        metric_retention_days=obs_config.get("metric_retention_days", 30),
    )


def _normalize_exchange_config(config_dict: Dict[str, Any]) -> ExchangeConfig:
    """Normalize exchange configuration."""
    exchange_name = config_dict.get("exchange")
    if not exchange_name:
        raise ConfigurationError("Exchange name is required")

    # Check if we have stored exchange dict from normalization
    exchange_dict = config_dict.get("_exchange_dict")

    if exchange_dict:
        # Use the full dictionary data
        return ExchangeConfig(
            name=exchange_dict.get("name", "binance"),
            api_key=exchange_dict.get("api_key"),
            secret_key=exchange_dict.get("secret_key"),
            testnet=exchange_dict.get("testnet", True),
            rate_limit=exchange_dict.get("rate_limit", 10),
            timeout=exchange_dict.get("timeout", 30),
        )
    elif isinstance(exchange_name, str):
        # Simple string format
        return ExchangeConfig(name=exchange_name)
    else:
        raise ConfigurationError(f"Invalid exchange configuration: {exchange_name}")


def _normalize_legacy_fields(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize legacy field names to match current schema.

    Args:
        config_dict: Raw configuration dictionary

    Returns:
        Normalized configuration dictionary
    """
    config = config_dict.copy()

    # Convert fees from legacy format
    if "fees" in config and isinstance(config["fees"], dict):
        fees = config["fees"]
        if "maker" in fees and "maker_bps" not in fees:
            # Convert decimal fees to basis points
            config["fees"]["maker_bps"] = fees["maker"] * 10000
            config["fees"].pop("maker", None)
        if "taker" in fees and "taker_bps" not in fees:
            # Convert decimal fees to basis points
            config["fees"]["taker_bps"] = fees["taker"] * 10000
            config["fees"].pop("taker", None)

    # Handle risk config normalization - convert legacy 'risk' to 'risk_controls'
    if "risk" in config:
        if "risk_controls" not in config:
            config["risk_controls"] = config.pop("risk")
        else:
            # Merge risk fields into risk_controls
            risk_data = config.pop("risk")
            config["risk_controls"].update(risk_data)

    # Add missing required fields with defaults
    if "risk_controls" in config:
        risk = config["risk_controls"]
        if "max_open_cycles" not in risk:
            risk["max_open_cycles"] = 3

    if "order" in config:
        order = config["order"]
        if "type" not in order:
            order["type"] = "market"
        if "allow_partial_fills" not in order:
            order["allow_partial_fills"] = True
        if "max_retries" not in order:
            order["max_retries"] = 3
        if "retry_delay_ms" not in order:
            order["retry_delay_ms"] = 1000

    # Handle execution config normalization
    if "execution" in config:
        execution = config["execution"]
        if execution.get("mode") == "paper" and "paper" not in execution:
            # Convert legacy paper config format to nested format
            paper_config = {
                "fee_bps": execution.get("fee_bps", 30.0),
                "fill_ratio": execution.get("fill_ratio", 0.95),
                "initial_balances": {}
            }

            # Convert legacy balance fields
            if "paper_balance_btc" in execution:
                paper_config["initial_balances"]["BTC"] = execution.pop("paper_balance_btc")
            if "paper_balance_eth" in execution:
                paper_config["initial_balances"]["ETH"] = execution.pop("paper_balance_eth")
            if "paper_balance_usdt" in execution:
                paper_config["initial_balances"]["USDT"] = execution.pop("paper_balance_usdt")

            # Set default balances if none provided
            if not paper_config["initial_balances"]:
                paper_config["initial_balances"] = {"BTC": 1.0, "USDT": 50000.0}

            execution["paper"] = paper_config

    # Handle exchange config normalization - convert dict to string for validation
    if "exchange" in config and isinstance(config["exchange"], dict):
        # Store the full exchange config for later use in _normalize_exchange_config
        config["_exchange_dict"] = config["exchange"]
        # For validation, use just the exchange name
        config["exchange"] = config["exchange"].get("name", "binance")

    return config


def load_strategy_config(config_path: Union[str, Path]) -> StrategyRuntimeConfig:
    """
    Load and normalize a strategy configuration file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Normalized and frozen strategy configuration

    Raises:
        ConfigurationError: If the configuration cannot be loaded or is invalid
        ValidationError: If the configuration fails schema validation
    """
    # Load raw YAML
    config_dict = load_yaml_config(config_path)

    # Normalize legacy field names
    config_dict = _normalize_legacy_fields(config_dict)

    # Validate against schema first (remove internal fields)
    validation_dict = config_dict.copy()
    validation_dict.pop("_exchange_dict", None)  # Remove internal storage field
    try:
        validate_strategy_config(validation_dict)
    except Exception as e:
        raise ValidationError(f"Configuration validation failed: {e}")

    # Normalize components
    try:
        execution_config = _normalize_execution_config(config_dict)
        risk_config = _normalize_risk_config(config_dict)
        observability_config = _normalize_observability_config(config_dict)
        exchange_config = _normalize_exchange_config(config_dict)

        return StrategyRuntimeConfig(
            name=config_dict.get("name", "default_strategy"),
            exchange=exchange_config,
            execution=execution_config,
            risk=risk_config,
            observability=observability_config,
            symbols=config_dict.get("symbols", ["BTC/USDT", "ETH/USDT", "ETH/BTC"]),
            min_profit_threshold=config_dict.get("min_profit_threshold", 0.001),
            max_trade_amount_btc=config_dict.get("max_trade_amount_btc", 0.1),
            fee_rate=config_dict.get("fee_rate", 0.001),
            volatility_window_size=config_dict.get("volatility_window_size"),
            sigma_multiplier=config_dict.get("sigma_multiplier"),
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to normalize configuration: {e}")


def get_default_config() -> StrategyRuntimeConfig:
    """Get a default configuration for testing or fallback purposes."""
    return StrategyRuntimeConfig(
        name="default_strategy", exchange=ExchangeConfig(name="binance")
    )
