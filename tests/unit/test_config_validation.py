"""
Unit tests for configuration schema validation
"""

import pytest
import tempfile
import os
from pathlib import Path
from pydantic import ValidationError

from triangular_arbitrage.config_schema import (
    StrategyConfig,
    validate_strategy_config,
    validate_config_file,
    ExecutionConfig,
    PaperExecutionConfig,
    BacktestExecutionConfig,
    CapitalAllocationConfig,
    RiskControlsConfig,
    FeesConfig,
    OrderConfig,
)


@pytest.fixture
def valid_minimal_config():
    """Minimal valid configuration"""
    return {
        "name": "test_strategy",
        "exchange": "binance",
        "trading_pairs_file": "data/cycles/test_cycles.csv",
        "min_profit_bps": 10,
        "max_slippage_bps": 20,
        "max_leg_latency_ms": 500,
        "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
        "risk_controls": {"max_open_cycles": 1},
        "fees": {"taker_bps": 10, "maker_bps": 5},
        "order": {
            "type": "market",
            "allow_partial_fills": False,
            "max_retries": 3,
            "retry_delay_ms": 1000,
        },
    }


@pytest.fixture
def valid_comprehensive_config():
    """Comprehensive valid configuration with all features"""
    return {
        "name": "comprehensive_strategy",
        "exchange": "kraken",
        "trading_pairs_file": "data/cycles/kraken_cycles.csv",
        "min_profit_bps": 15,
        "max_slippage_bps": 25,
        "max_leg_latency_ms": 400,
        "execution": {
            "mode": "paper",
            "paper": {
                "fee_bps": 30,
                "fill_ratio": 0.95,
                "initial_balances": {"BTC": 1.0, "USDT": 10000.0},
                "slippage_model": {
                    "base_slippage_bps": 2,
                    "volatility_multiplier": 1.5,
                    "random_component_bps": 3,
                },
                "market_impact": {
                    "enabled": True,
                    "impact_coefficient": 0.1,
                    "max_impact_bps": 50,
                },
            },
        },
        "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.2},
        "risk_controls": {
            "max_open_cycles": 3,
            "stop_after_consecutive_losses": 4,
            "slippage_cooldown_seconds": 300,
        },
        "fees": {"taker_bps": 15, "maker_bps": 8},
        "order": {
            "type": "market",
            "allow_partial_fills": True,
            "max_retries": 3,
            "retry_delay_ms": 1000,
            "monitoring": {
                "initial_delay_ms": 100,
                "max_delay_ms": 5000,
                "backoff_multiplier": 2.0,
            },
        },
        "panic_sell": {
            "enabled": True,
            "base_currencies": ["USDT", "USD"],
            "max_slippage_bps": 100,
        },
        "observability": {
            "metrics": {"enabled": True, "port": 8000, "path": "/metrics"},
            "logging": {"level": "INFO", "structured_format": True},
        },
        "reconciliation": {
            "partial_fills": {
                "enabled": True,
                "hedge_threshold_bps": 50,
                "cancel_threshold_bps": 200,
                "max_wait_time_ms": 5000,
            }
        },
    }


class TestStrategyConfigValidation:
    """Test strategy configuration validation"""

    def test_valid_minimal_config(self, valid_minimal_config):
        """Test validation of minimal valid configuration"""
        config = validate_strategy_config(valid_minimal_config)
        assert config.name == "test_strategy"
        assert config.exchange == "binance"
        assert config.min_profit_bps == 10

    def test_valid_comprehensive_config(self, valid_comprehensive_config):
        """Test validation of comprehensive configuration"""
        config = validate_strategy_config(valid_comprehensive_config)
        assert config.name == "comprehensive_strategy"
        assert config.execution.mode == "paper"
        assert config.execution.paper.fee_bps == 30
        assert config.observability.metrics.enabled is True

    def test_required_fields_missing(self):
        """Test validation fails when required fields are missing"""
        incomplete_config = {
            "name": "test_strategy"
            # Missing required fields
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_strategy_config(incomplete_config)

        error = str(exc_info.value)
        assert "exchange" in error or "field required" in error

    def test_invalid_name_validation(self):
        """Test name validation rules"""
        base_config = {
            "exchange": "binance",
            "trading_pairs_file": "data/cycles/test.csv",
            "min_profit_bps": 10,
            "max_slippage_bps": 20,
            "max_leg_latency_ms": 500,
            "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
            "risk_controls": {"max_open_cycles": 1},
            "fees": {"taker_bps": 10, "maker_bps": 5},
            "order": {
                "type": "market",
                "allow_partial_fills": False,
                "max_retries": 3,
                "retry_delay_ms": 1000,
            },
        }

        # Empty name
        with pytest.raises(ValidationError):
            validate_strategy_config({**base_config, "name": ""})

        # Name with invalid characters
        with pytest.raises(ValidationError):
            validate_strategy_config({**base_config, "name": "strategy/with/slash"})

    def test_numeric_field_validation(self):
        """Test validation of numeric fields"""
        base_config = {
            "name": "test_strategy",
            "exchange": "binance",
            "trading_pairs_file": "data/cycles/test.csv",
            "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
            "risk_controls": {"max_open_cycles": 1},
            "fees": {"taker_bps": 10, "maker_bps": 5},
            "order": {
                "type": "market",
                "allow_partial_fills": False,
                "max_retries": 3,
                "retry_delay_ms": 1000,
            },
        }

        # Negative min_profit_bps (extreme)
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {
                    **base_config,
                    "min_profit_bps": -2000,  # Too low
                    "max_slippage_bps": 20,
                    "max_leg_latency_ms": 500,
                }
            )

        # Negative max_slippage_bps
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {
                    **base_config,
                    "min_profit_bps": 10,
                    "max_slippage_bps": -5,  # Invalid
                    "max_leg_latency_ms": 500,
                }
            )

        # Negative max_leg_latency_ms
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {
                    **base_config,
                    "min_profit_bps": 10,
                    "max_slippage_bps": 20,
                    "max_leg_latency_ms": -100,  # Invalid
                }
            )

    def test_execution_mode_validation(self):
        """Test execution mode configuration validation"""
        base_config = {
            "name": "test_strategy",
            "exchange": "binance",
            "trading_pairs_file": "data/cycles/test.csv",
            "min_profit_bps": 10,
            "max_slippage_bps": 20,
            "max_leg_latency_ms": 500,
            "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
            "risk_controls": {"max_open_cycles": 1},
            "fees": {"taker_bps": 10, "maker_bps": 5},
            "order": {
                "type": "market",
                "allow_partial_fills": False,
                "max_retries": 3,
                "retry_delay_ms": 1000,
            },
        }

        # Paper mode without paper config
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {
                    **base_config,
                    "execution": {
                        "mode": "paper"
                        # Missing paper config
                    },
                }
            )

        # Backtest mode without backtest config
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {
                    **base_config,
                    "execution": {
                        "mode": "backtest"
                        # Missing backtest config
                    },
                }
            )

        # Invalid execution mode
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {**base_config, "execution": {"mode": "invalid_mode"}}
            )

    def test_paper_execution_config_validation(self):
        """Test paper execution configuration validation"""
        paper_config = {
            "fee_bps": 30,
            "fill_ratio": 0.95,
            "initial_balances": {"BTC": 1.0, "USDT": 10000.0},
        }

        # Valid config
        config = PaperExecutionConfig(**paper_config)
        assert config.fee_bps == 30
        assert config.fill_ratio == 0.95

        # Invalid fee_bps
        with pytest.raises(ValidationError):
            PaperExecutionConfig(**{**paper_config, "fee_bps": -10})

        # Invalid fill_ratio
        with pytest.raises(ValidationError):
            PaperExecutionConfig(**{**paper_config, "fill_ratio": 1.5})

        # Empty initial_balances
        with pytest.raises(ValidationError):
            PaperExecutionConfig(**{**paper_config, "initial_balances": {}})

        # Negative balance
        with pytest.raises(ValidationError):
            PaperExecutionConfig(
                **{**paper_config, "initial_balances": {"BTC": -1.0, "USDT": 10000.0}}
            )

    def test_backtest_execution_config_validation(self):
        """Test backtest execution configuration validation"""
        backtest_config = {
            "data_file": "data/backtest_data.csv",
            "initial_balances": {"BTC": 1.0, "USDT": 50000.0},
        }

        # Valid config
        config = BacktestExecutionConfig(**backtest_config)
        assert config.data_file == "data/backtest_data.csv"

        # Empty data_file
        with pytest.raises(ValidationError):
            BacktestExecutionConfig(**{**backtest_config, "data_file": ""})

        # Invalid time range
        with pytest.raises(ValidationError):
            BacktestExecutionConfig(
                **{
                    **backtest_config,
                    "start_time": 1700000000,
                    "end_time": 1600000000,  # End before start
                }
            )

        # Invalid time_acceleration
        with pytest.raises(ValidationError):
            BacktestExecutionConfig(**{**backtest_config, "time_acceleration": -1.0})

    def test_capital_allocation_validation(self):
        """Test capital allocation configuration validation"""
        # Fixed fraction mode without fraction
        with pytest.raises(ValidationError):
            CapitalAllocationConfig(mode="fixed_fraction")

        # Fixed amount mode without amount
        with pytest.raises(ValidationError):
            CapitalAllocationConfig(mode="fixed_amount")

        # Valid fixed fraction
        config = CapitalAllocationConfig(mode="fixed_fraction", fraction=0.1)
        assert config.mode == "fixed_fraction"
        assert config.fraction == 0.1

        # Valid fixed amount
        config = CapitalAllocationConfig(mode="fixed_amount", amount=1000.0)
        assert config.mode == "fixed_amount"
        assert config.amount == 1000.0

        # Invalid fraction (too high)
        with pytest.raises(ValidationError):
            CapitalAllocationConfig(mode="fixed_fraction", fraction=1.5)

    def test_risk_controls_validation(self):
        """Test risk controls configuration validation"""
        # Valid config
        config = RiskControlsConfig(max_open_cycles=3)
        assert config.max_open_cycles == 3

        # Invalid max_open_cycles
        with pytest.raises(ValidationError):
            RiskControlsConfig(max_open_cycles=0)  # Too low

        with pytest.raises(ValidationError):
            RiskControlsConfig(max_open_cycles=200)  # Too high

        # Invalid cooldown
        with pytest.raises(ValidationError):
            RiskControlsConfig(max_open_cycles=3, slippage_cooldown_seconds=-100)

    def test_fees_validation(self):
        """Test fees configuration validation"""
        # Valid fees
        config = FeesConfig(taker_bps=10, maker_bps=5)
        assert config.taker_bps == 10
        assert config.maker_bps == 5

        # Negative fees
        with pytest.raises(ValidationError):
            FeesConfig(taker_bps=-5, maker_bps=5)

        with pytest.raises(ValidationError):
            FeesConfig(taker_bps=10, maker_bps=-2)

        # Very high fees
        with pytest.raises(ValidationError):
            FeesConfig(taker_bps=2000, maker_bps=5)  # Too high

    def test_order_config_validation(self):
        """Test order configuration validation"""
        # Valid config
        config = OrderConfig(
            type="market", allow_partial_fills=True, max_retries=3, retry_delay_ms=1000
        )
        assert config.type == "market"
        assert config.max_retries == 3

        # Invalid order type
        with pytest.raises(ValidationError):
            OrderConfig(
                type="invalid_type",
                allow_partial_fills=False,
                max_retries=3,
                retry_delay_ms=1000,
            )

        # Invalid max_retries
        with pytest.raises(ValidationError):
            OrderConfig(
                type="market",
                allow_partial_fills=False,
                max_retries=-1,  # Negative
                retry_delay_ms=1000,
            )

    def test_panic_sell_validation(self):
        """Test panic sell configuration validation"""
        base_config = {
            "name": "test_strategy",
            "exchange": "binance",
            "trading_pairs_file": "data/cycles/test.csv",
            "min_profit_bps": 10,
            "max_slippage_bps": 20,
            "max_leg_latency_ms": 500,
            "capital_allocation": {"mode": "fixed_fraction", "fraction": 0.1},
            "risk_controls": {"max_open_cycles": 1},
            "fees": {"taker_bps": 10, "maker_bps": 5},
            "order": {
                "type": "market",
                "allow_partial_fills": False,
                "max_retries": 3,
                "retry_delay_ms": 1000,
            },
        }

        # Valid panic sell config
        config = validate_strategy_config(
            {
                **base_config,
                "panic_sell": {
                    "enabled": True,
                    "base_currencies": ["USDT", "USD"],
                    "max_slippage_bps": 100,
                },
            }
        )
        assert config.panic_sell.enabled is True
        assert "USDT" in config.panic_sell.base_currencies

        # Empty base_currencies
        with pytest.raises(ValidationError):
            validate_strategy_config(
                {
                    **base_config,
                    "panic_sell": {
                        "enabled": True,
                        "base_currencies": [],  # Empty
                        "max_slippage_bps": 100,
                    },
                }
            )

    def test_extra_fields_forbidden(self, valid_minimal_config):
        """Test that extra fields are forbidden"""
        invalid_config = {**valid_minimal_config, "extra_field": "not_allowed"}

        with pytest.raises(ValidationError) as exc_info:
            validate_strategy_config(invalid_config)

        error = str(exc_info.value)
        assert "extra_field" in error or "extra fields not permitted" in error


class TestConfigFileValidation:
    """Test configuration file validation"""

    def test_validate_existing_config_file(self, valid_minimal_config):
        """Test validation of YAML file"""
        import yaml
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(valid_minimal_config, f)
            temp_path = f.name

        try:
            config = validate_config_file(temp_path)
            assert config.name == "test_strategy"
        finally:
            os.unlink(temp_path)

    def test_validate_nonexistent_file(self):
        """Test validation of non-existent file"""
        with pytest.raises(FileNotFoundError):
            validate_config_file("/nonexistent/path/config.yaml")

    def test_validate_invalid_yaml_file(self):
        """Test validation of invalid YAML"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")  # Invalid YAML
            temp_path = f.name

        try:
            with pytest.raises(Exception):  # Should raise YAML parsing error
                validate_config_file(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_empty_config_file(self):
        """Test validation of empty file"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name

        try:
            with pytest.raises(ValueError):
                validate_config_file(temp_path)
        finally:
            os.unlink(temp_path)


class TestPartialFillsValidation:
    """Test partial fills configuration validation"""

    def test_valid_threshold_relationship(self):
        """Test that hedge threshold is less than cancel threshold"""
        from triangular_arbitrage.config_schema import PartialFillsConfig

        # Valid relationship
        config = PartialFillsConfig(
            enabled=True,
            hedge_threshold_bps=50,
            cancel_threshold_bps=200,
            max_wait_time_ms=5000,
        )
        assert config.hedge_threshold_bps == 50
        assert config.cancel_threshold_bps == 200

        # Invalid relationship (hedge >= cancel)
        with pytest.raises(ValidationError):
            PartialFillsConfig(
                enabled=True,
                hedge_threshold_bps=200,  # Same as cancel
                cancel_threshold_bps=200,
                max_wait_time_ms=5000,
            )

        with pytest.raises(ValidationError):
            PartialFillsConfig(
                enabled=True,
                hedge_threshold_bps=300,  # Greater than cancel
                cancel_threshold_bps=200,
                max_wait_time_ms=5000,
            )


class TestOrderMonitoringValidation:
    """Test order monitoring configuration validation"""

    def test_delay_validation(self):
        """Test monitoring delay validation"""
        from triangular_arbitrage.config_schema import OrderMonitoringConfig

        # Valid delays
        config = OrderMonitoringConfig(
            initial_delay_ms=100, max_delay_ms=5000, backoff_multiplier=2.0
        )
        assert config.initial_delay_ms == 100
        assert config.max_delay_ms == 5000

        # Invalid relationship (initial >= max)
        with pytest.raises(ValidationError):
            OrderMonitoringConfig(
                initial_delay_ms=5000,  # Same as max
                max_delay_ms=5000,
                backoff_multiplier=2.0,
            )

        with pytest.raises(ValidationError):
            OrderMonitoringConfig(
                initial_delay_ms=6000,  # Greater than max
                max_delay_ms=5000,
                backoff_multiplier=2.0,
            )


class TestSlippageModelValidation:
    """Test slippage model configuration validation"""

    def test_valid_slippage_model(self):
        """Test valid slippage model configuration"""
        from triangular_arbitrage.config_schema import SlippageModel

        config = SlippageModel(
            base_slippage_bps=2,
            volatility_multiplier=1.5,
            random_component_bps=3,
            max_slippage_bps=100,
        )
        assert config.base_slippage_bps == 2
        assert config.volatility_multiplier == 1.5

    def test_slippage_bounds(self):
        """Test slippage model bounds"""
        from triangular_arbitrage.config_schema import SlippageModel

        # Negative base slippage
        with pytest.raises(ValidationError):
            SlippageModel(base_slippage_bps=-1)

        # Extremely high slippage
        with pytest.raises(ValidationError):
            SlippageModel(base_slippage_bps=2000)  # > 1000 bps limit

        # Invalid multiplier
        with pytest.raises(ValidationError):
            SlippageModel(base_slippage_bps=2, volatility_multiplier=-0.5)  # Negative
