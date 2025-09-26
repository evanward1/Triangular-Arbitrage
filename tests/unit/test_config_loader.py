"""Tests for the config_loader module."""

import pytest
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile
from triangular_arbitrage.config_loader import (
    load_yaml_config,
    load_strategy_config,
    get_default_config,
    ExecutionConfig,
    RiskConfig,
    ObservabilityConfig,
    ExchangeConfig,
    StrategyRuntimeConfig,
)
from triangular_arbitrage.exceptions import ConfigurationError, ValidationError


def test_load_yaml_config_valid():
    """Test loading a valid YAML configuration."""
    config_data = {
        'name': 'test_strategy',
        'exchange': 'binance',
        'min_profit_threshold': 0.001
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_yaml_config(f.name)
        assert result == config_data

    Path(f.name).unlink()


def test_load_yaml_config_file_not_found():
    """Test loading config from non-existent file."""
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        load_yaml_config("/non/existent/file.yaml")


def test_load_yaml_config_empty_file():
    """Test loading config from empty file."""
    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("")
        f.flush()

        with pytest.raises(ConfigurationError, match="Empty configuration file"):
            load_yaml_config(f.name)

    Path(f.name).unlink()


def test_load_yaml_config_invalid_yaml():
    """Test loading config with invalid YAML."""
    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("invalid: yaml: content: [")
        f.flush()

        with pytest.raises(ConfigurationError, match="Invalid YAML"):
            load_yaml_config(f.name)

    Path(f.name).unlink()


def test_execution_config_defaults():
    """Test ExecutionConfig with defaults."""
    config = ExecutionConfig()
    assert config.mode == "live"
    assert config.paper_balance_btc == 1.0
    assert config.paper_balance_eth == 10.0
    assert config.paper_balance_usdt == 10000.0
    assert config.backtest_start_date is None


def test_execution_config_custom_values():
    """Test ExecutionConfig with custom values."""
    config = ExecutionConfig(
        mode="paper",
        paper_balance_btc=2.0,
        backtest_start_date="2024-01-01"
    )
    assert config.mode == "paper"
    assert config.paper_balance_btc == 2.0
    assert config.backtest_start_date == "2024-01-01"


def test_risk_config_defaults():
    """Test RiskConfig with defaults."""
    config = RiskConfig()
    assert config.max_position_size == 0.1
    assert config.max_daily_loss == 0.05
    assert config.enable_kill_switch == True
    assert config.max_open_positions == 3


def test_observability_config_defaults():
    """Test ObservabilityConfig with defaults."""
    config = ObservabilityConfig()
    assert config.enabled == True
    assert config.prometheus_port == 8000
    assert config.grafana_port == 3000
    assert config.metric_retention_days == 30


def test_exchange_config():
    """Test ExchangeConfig."""
    config = ExchangeConfig(name="binance", testnet=False)
    assert config.name == "binance"
    assert config.testnet == False
    assert config.rate_limit == 10


def test_strategy_runtime_config():
    """Test StrategyRuntimeConfig."""
    exchange_config = ExchangeConfig(name="binance")
    config = StrategyRuntimeConfig(
        name="test_strategy",
        exchange=exchange_config
    )
    assert config.name == "test_strategy"
    assert config.exchange.name == "binance"
    assert config.min_profit_threshold == 0.001
    assert isinstance(config.execution, ExecutionConfig)
    assert isinstance(config.risk, RiskConfig)
    assert isinstance(config.observability, ObservabilityConfig)


def test_get_default_config():
    """Test getting default configuration."""
    config = get_default_config()
    assert isinstance(config, StrategyRuntimeConfig)
    assert config.name == "default_strategy"
    assert config.exchange.name == "binance"


def test_load_strategy_config_minimal():
    """Test loading minimal strategy config."""
    config_data = {
        'name': 'minimal_strategy',
        'exchange': 'binance',
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000}
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_strategy_config(f.name)
        assert isinstance(result, StrategyRuntimeConfig)
        assert result.name == 'minimal_strategy'
        assert result.exchange.name == 'binance'

    Path(f.name).unlink()


def test_load_strategy_config_with_execution():
    """Test loading strategy config with execution settings."""
    config_data = {
        'name': 'paper_strategy',
        'exchange': 'binance',
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000},
        'execution': {
            'mode': 'paper',
            'paper_balance_btc': 2.0
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_strategy_config(f.name)
        assert result.execution.mode == 'paper'
        assert result.execution.paper_balance_btc == 2.0

    Path(f.name).unlink()


def test_load_strategy_config_with_risk():
    """Test loading strategy config with risk settings."""
    config_data = {
        'name': 'risk_strategy',
        'exchange': 'binance',
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000},
        'risk': {
            'max_position_size': 0.05,
            'enable_kill_switch': False
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_strategy_config(f.name)
        assert result.risk.max_position_size == 0.05
        assert result.risk.enable_kill_switch == False

    Path(f.name).unlink()


def test_load_strategy_config_frozen():
    """Test that loaded config is frozen (immutable)."""
    config_data = {
        'name': 'frozen_strategy',
        'exchange': 'binance',
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000}
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_strategy_config(f.name)

        # Should not be able to modify frozen dataclass
        with pytest.raises(AttributeError):
            result.name = "new_name"

        with pytest.raises(AttributeError):
            result.execution.mode = "backtest"

    Path(f.name).unlink()


def test_legacy_exchange_config_string():
    """Test handling legacy string exchange config."""
    config_data = {
        'name': 'legacy_strategy',
        'exchange': 'binance',
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000}
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_strategy_config(f.name)
        assert result.exchange.name == 'binance'
        assert result.exchange.testnet == True  # default

    Path(f.name).unlink()


def test_exchange_config_dict():
    """Test handling dict-based exchange config."""
    config_data = {
        'name': 'dict_strategy',
        'exchange': {
            'name': 'coinbase',
            'testnet': False,
            'rate_limit': 5
        },
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000}
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        result = load_strategy_config(f.name)
        assert result.exchange.name == 'coinbase'
        assert result.exchange.testnet == False
        assert result.exchange.rate_limit == 5

    Path(f.name).unlink()


def test_load_strategy_config_missing_exchange():
    """Test loading strategy config without exchange."""
    config_data = {
        'name': 'no_exchange_strategy',
        'trading_pairs_file': 'pairs.txt',
        'min_profit_bps': 10,
        'max_slippage_bps': 5,
        'max_leg_latency_ms': 100,
        'capital_allocation': {'mode': 'fixed_fraction', 'fraction': 0.1},
        'risk_controls': {'max_position_usd': 1000},
        'fees': {'maker': 0.001, 'taker': 0.001},
        'order': {'default_timeout_ms': 30000}
        # Missing exchange field
    }

    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        f.flush()

        with pytest.raises(ValidationError, match="Field required"):
            load_strategy_config(f.name)

    Path(f.name).unlink()


def test_immutable_configs():
    """Test that all config objects are immutable."""
    exec_config = ExecutionConfig()
    risk_config = RiskConfig()
    obs_config = ObservabilityConfig()
    exchange_config = ExchangeConfig(name="test")

    # All should be frozen dataclasses
    with pytest.raises(AttributeError):
        exec_config.mode = "new_mode"

    with pytest.raises(AttributeError):
        risk_config.max_position_size = 0.5

    with pytest.raises(AttributeError):
        obs_config.enabled = False

    with pytest.raises(AttributeError):
        exchange_config.name = "new_exchange"