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

    # Apply mode-specific defaults
    defaults = {}
    if mode == "paper":
        defaults = {
            "paper_balance_btc": 1.0,
            "paper_balance_eth": 10.0,
            "paper_balance_usdt": 10000.0,
        }
    elif mode == "backtest":
        defaults = {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2024-01-31",
            "backtest_data_dir": "backtests/data",
        }

    return ExecutionConfig(
        mode=mode,
        paper_balance_btc=exec_config.get(
            "paper_balance_btc", defaults.get("paper_balance_btc", 1.0)
        ),
        paper_balance_eth=exec_config.get(
            "paper_balance_eth", defaults.get("paper_balance_eth", 10.0)
        ),
        paper_balance_usdt=exec_config.get(
            "paper_balance_usdt", defaults.get("paper_balance_usdt", 10000.0)
        ),
        backtest_start_date=exec_config.get(
            "backtest_start_date", defaults.get("backtest_start_date")
        ),
        backtest_end_date=exec_config.get(
            "backtest_end_date", defaults.get("backtest_end_date")
        ),
        backtest_data_dir=exec_config.get(
            "backtest_data_dir", defaults.get("backtest_data_dir")
        ),
    )


def _normalize_risk_config(config_dict: Dict[str, Any]) -> RiskConfig:
    """Normalize risk configuration with defaults."""
    risk_config = config_dict.get("risk", {})

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

    # Handle legacy exchange config format
    if isinstance(exchange_name, str):
        return ExchangeConfig(name=exchange_name)
    elif isinstance(exchange_name, dict):
        return ExchangeConfig(
            name=exchange_name.get("name", "binance"),
            api_key=exchange_name.get("api_key"),
            secret_key=exchange_name.get("secret_key"),
            testnet=exchange_name.get("testnet", True),
            rate_limit=exchange_name.get("rate_limit", 10),
            timeout=exchange_name.get("timeout", 30),
        )
    else:
        raise ConfigurationError(f"Invalid exchange configuration: {exchange_name}")


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

    # Validate against schema first
    try:
        validate_strategy_config(config_dict)
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
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to normalize configuration: {e}")


def get_default_config() -> StrategyRuntimeConfig:
    """Get a default configuration for testing or fallback purposes."""
    return StrategyRuntimeConfig(
        name="default_strategy", exchange=ExchangeConfig(name="binance")
    )
