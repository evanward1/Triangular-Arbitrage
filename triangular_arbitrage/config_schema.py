"""
Configuration schema validation using Pydantic
"""

from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from pathlib import Path


class SlippageModel(BaseModel):
    """Slippage model configuration"""

    base_slippage_bps: float = Field(
        ge=0, le=1000, description="Base slippage in basis points"
    )
    volatility_multiplier: Optional[float] = Field(ge=0, le=10, default=1.0)
    random_component_bps: Optional[float] = Field(ge=0, le=100, default=0)
    adverse_selection_bps: Optional[float] = Field(ge=0, le=100, default=0)
    size_impact_coefficient: Optional[float] = Field(ge=0, le=1, default=0)
    max_slippage_bps: Optional[float] = Field(ge=0, le=10000, default=1000)


class MarketImpactModel(BaseModel):
    """Market impact model configuration"""

    enabled: bool = True
    impact_coefficient: float = Field(
        ge=0, le=10, description="Impact coefficient per $1000 notional"
    )
    max_impact_bps: float = Field(
        ge=0, le=1000, description="Maximum market impact in bps"
    )


class PartialFillModel(BaseModel):
    """Partial fill model configuration"""

    enabled: bool = True
    min_fill_ratio: float = Field(
        ge=0.01, le=1.0, description="Minimum fill percentage"
    )
    fill_time_spread_ms: Optional[int] = Field(ge=0, le=60000, default=1000)
    large_order_threshold: Optional[float] = Field(ge=0, default=1000)


class FillModel(BaseModel):
    """Fill behavior model for backtesting"""

    fill_probability: float = Field(
        ge=0, le=1.0, description="Probability that order fills"
    )
    partial_fill_threshold: float = Field(
        ge=0, description="USD threshold for partial fills"
    )
    min_fill_ratio: float = Field(
        ge=0.01, le=1.0, description="Minimum fill ratio for partials"
    )
    max_fill_time_ms: int = Field(
        ge=0, le=300000, description="Maximum time for fill completion"
    )


class PaperExecutionConfig(BaseModel):
    """Paper trading execution configuration"""

    fee_bps: float = Field(ge=0, le=1000, description="Trading fees in basis points")
    fill_ratio: float = Field(ge=0, le=1.0, description="Fill probability")
    spread_padding_bps: Optional[float] = Field(ge=0, le=100, default=0)
    random_seed: Optional[int] = Field(ge=1, le=2147483647, default=None)
    latency_sim_ms: Optional[int] = Field(ge=0, le=10000, default=0)
    initial_balances: Dict[str, float] = Field(
        description="Initial balances for paper trading"
    )
    slippage_model: Optional[SlippageModel] = None
    market_impact: Optional[MarketImpactModel] = None
    partial_fill_model: Optional[PartialFillModel] = None

    @field_validator("initial_balances")
    @classmethod
    def validate_initial_balances(cls, v):
        if not v:
            raise ValueError("initial_balances cannot be empty")
        for currency, balance in v.items():
            if not isinstance(currency, str) or len(currency) < 2:
                raise ValueError(f"Invalid currency code: {currency}")
            if balance < 0:
                raise ValueError(
                    f"Balance for {currency} cannot be negative: {balance}"
                )
        return v


class BacktestExecutionConfig(BaseModel):
    """Backtest execution configuration"""

    data_file: str = Field(description="Path to backtest data file")
    start_time: Optional[Union[int, float]] = Field(
        default=None, description="Start timestamp"
    )
    end_time: Optional[Union[int, float]] = Field(
        default=None, description="End timestamp"
    )
    time_acceleration: Optional[float] = Field(ge=0.1, le=1000, default=1.0)
    random_seed: Optional[int] = Field(ge=1, le=2147483647, default=None)
    initial_balances: Dict[str, float] = Field(
        description="Initial balances for backtesting"
    )
    slippage_model: Optional[SlippageModel] = None
    fill_model: Optional[FillModel] = None

    @field_validator("data_file")
    @classmethod
    def validate_data_file(cls, v):
        if not v:
            raise ValueError("data_file cannot be empty")
        # Note: File existence check would happen at runtime, not schema validation
        return v

    @field_validator("initial_balances")
    @classmethod
    def validate_initial_balances(cls, v):
        if not v:
            raise ValueError("initial_balances cannot be empty")
        for currency, balance in v.items():
            if not isinstance(currency, str) or len(currency) < 2:
                raise ValueError(f"Invalid currency code: {currency}")
            if balance < 0:
                raise ValueError(
                    f"Balance for {currency} cannot be negative: {balance}"
                )
        return v

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be less than end_time")
        return self


class ExecutionConfig(BaseModel):
    """Execution mode configuration"""

    mode: Literal["live", "paper", "backtest"] = Field(description="Execution mode")
    paper: Optional[PaperExecutionConfig] = None
    backtest: Optional[BacktestExecutionConfig] = None

    @model_validator(mode="after")
    def validate_mode_config(self):
        if self.mode == "paper" and not self.paper:
            raise ValueError("paper configuration required when mode is 'paper'")
        if self.mode == "backtest" and not self.backtest:
            raise ValueError("backtest configuration required when mode is 'backtest'")
        return self


class CapitalAllocationConfig(BaseModel):
    """Capital allocation configuration"""

    mode: Literal["fixed_amount", "fixed_fraction", "kelly", "risk_parity"] = Field(
        description="Allocation mode"
    )
    fraction: Optional[float] = Field(ge=0.001, le=1.0, default=None)
    amount: Optional[float] = Field(ge=0, default=None)
    max_allocation: Optional[float] = Field(ge=0, le=1.0, default=None)

    @model_validator(mode="after")
    def validate_allocation_params(self):
        if self.mode == "fixed_fraction" and self.fraction is None:
            raise ValueError("fraction required for fixed_fraction mode")
        if self.mode == "fixed_amount" and self.amount is None:
            raise ValueError("amount required for fixed_amount mode")
        return self


class RiskControlsConfig(BaseModel):
    """Risk controls configuration"""

    max_open_cycles: int = Field(ge=1, le=100, description="Maximum concurrent cycles")
    stop_after_consecutive_losses: Optional[int] = Field(ge=1, le=100, default=None)
    slippage_cooldown_seconds: Optional[int] = Field(ge=0, le=86400, default=0)
    enable_latency_checks: Optional[bool] = True
    enable_slippage_checks: Optional[bool] = True
    max_position_size: Optional[float] = Field(ge=0, default=None)
    daily_loss_limit: Optional[float] = Field(ge=0, default=None)


class FeesConfig(BaseModel):
    """Trading fees configuration"""

    taker_bps: float = Field(ge=0, le=1000, description="Taker fees in basis points")
    maker_bps: float = Field(ge=0, le=1000, description="Maker fees in basis points")

    @field_validator("maker_bps", "taker_bps")
    @classmethod
    def validate_fees(cls, v):
        if v < 0:
            raise ValueError("Fees cannot be negative")
        return v


class OrderMonitoringConfig(BaseModel):
    """Order monitoring configuration"""

    initial_delay_ms: int = Field(
        ge=0, le=60000, description="Initial monitoring delay"
    )
    max_delay_ms: int = Field(ge=1, le=300000, description="Maximum monitoring delay")
    backoff_multiplier: float = Field(ge=1.0, le=10.0, description="Backoff multiplier")

    @model_validator(mode="after")
    def validate_delays(self):
        if (
            self.initial_delay_ms
            and self.max_delay_ms
            and self.initial_delay_ms >= self.max_delay_ms
        ):
            raise ValueError("initial_delay_ms must be less than max_delay_ms")
        return self


class OrderConfig(BaseModel):
    """Order configuration"""

    type: Literal["market", "limit", "stop"] = Field(description="Order type")
    allow_partial_fills: bool = Field(description="Allow partial fills")
    max_retries: int = Field(ge=0, le=10, description="Maximum retry attempts")
    retry_delay_ms: int = Field(
        ge=0, le=60000, description="Retry delay in milliseconds"
    )
    monitoring: Optional[OrderMonitoringConfig] = None


class PanicSellConfig(BaseModel):
    """Panic sell configuration"""

    enabled: bool = Field(description="Enable panic sell functionality")
    base_currencies: List[str] = Field(
        min_length=1, description="Base currencies for panic sell"
    )
    max_slippage_bps: float = Field(
        ge=0, le=10000, description="Maximum slippage for panic sell"
    )
    use_enhanced_routing: Optional[bool] = True

    @field_validator("base_currencies")
    @classmethod
    def validate_base_currencies(cls, v):
        if not v:
            raise ValueError("base_currencies cannot be empty")
        for currency in v:
            if not isinstance(currency, str) or len(currency) < 2:
                raise ValueError(f"Invalid currency code: {currency}")
        return v


class SimulationConfig(BaseModel):
    """Simulation configuration"""

    enable: bool = Field(description="Enable simulation mode")
    book_depth_levels: Optional[int] = Field(ge=1, le=20, default=5)
    latency_ms: Optional[int] = Field(ge=0, le=10000, default=0)


class MetricsConfig(BaseModel):
    """Metrics server configuration"""

    enabled: bool = True
    port: int = Field(ge=1024, le=65535, description="Metrics server port")
    path: str = Field(
        pattern=r"^/[a-zA-Z0-9_/-]*$", description="Metrics endpoint path"
    )
    expose: Optional[List[str]] = Field(
        default=None, description="Specific metrics to expose"
    )


class LoggingConfig(BaseModel):
    """Logging configuration"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    trade_csv: Optional[str] = None
    risk_json: Optional[str] = None
    daily_rolling: Optional[bool] = False
    max_log_files: Optional[int] = Field(ge=1, le=365, default=30)
    structured_format: Optional[bool] = False
    include_metadata: Optional[bool] = False


class ObservabilityConfig(BaseModel):
    """Observability configuration"""

    metrics: Optional[MetricsConfig] = None
    logging: Optional[LoggingConfig] = None


class PartialFillsConfig(BaseModel):
    """Partial fills configuration"""

    enabled: bool = True
    hedge_threshold_bps: float = Field(
        ge=0, le=10000, description="Hedge threshold in bps"
    )
    cancel_threshold_bps: float = Field(
        ge=0, le=10000, description="Cancel threshold in bps"
    )
    max_wait_time_ms: int = Field(ge=0, le=300000, description="Max wait time in ms")

    @model_validator(mode="after")
    def validate_thresholds(self):
        if (
            self.hedge_threshold_bps
            and self.cancel_threshold_bps
            and self.hedge_threshold_bps >= self.cancel_threshold_bps
        ):
            raise ValueError(
                "hedge_threshold_bps must be less than cancel_threshold_bps"
            )
        return self


class PositionTrackingConfig(BaseModel):
    """Position tracking configuration"""

    enabled: bool = True
    tolerance_bps: float = Field(ge=0, le=1000, description="Position tolerance in bps")
    reconcile_on_cycle_end: Optional[bool] = True


class SlippageDecisionsConfig(BaseModel):
    """Slippage-based decisions configuration"""

    hedge_on_high_slippage: Optional[bool] = True
    cancel_on_extreme_slippage: Optional[bool] = True
    dynamic_thresholds: Optional[bool] = True


class ReconciliationConfig(BaseModel):
    """Reconciliation configuration"""

    partial_fills: Optional[PartialFillsConfig] = None
    position_tracking: Optional[PositionTrackingConfig] = None
    slippage_decisions: Optional[SlippageDecisionsConfig] = None


class StrategyConfig(BaseModel):
    """Complete strategy configuration schema"""

    # Core strategy parameters
    name: str = Field(min_length=1, max_length=100, description="Strategy name")
    exchange: str = Field(min_length=1, description="Exchange identifier")
    trading_pairs_file: str = Field(description="Path to trading pairs file")
    min_profit_bps: float = Field(
        ge=-1000, le=10000, description="Minimum profit in basis points"
    )
    max_slippage_bps: float = Field(
        ge=0, le=10000, description="Maximum acceptable slippage"
    )
    max_leg_latency_ms: int = Field(
        ge=0, le=60000, description="Maximum leg latency in milliseconds"
    )

    # Execution configuration
    execution: Optional[ExecutionConfig] = None

    # Risk and capital management
    capital_allocation: CapitalAllocationConfig
    risk_controls: RiskControlsConfig
    fees: FeesConfig

    # Order management
    order: OrderConfig
    panic_sell: Optional[PanicSellConfig] = None

    # Simulation
    simulation: Optional[SimulationConfig] = None

    # Observability
    observability: Optional[ObservabilityConfig] = None

    # Reconciliation
    reconciliation: Optional[ReconciliationConfig] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Strategy name cannot be empty")
        # Ensure valid filename characters
        invalid_chars = set('<>:"/\\|?*')
        if any(char in v for char in invalid_chars):
            raise ValueError(
                f"Strategy name contains invalid characters: {invalid_chars}"
            )
        return v.strip()

    @field_validator("min_profit_bps")
    @classmethod
    def validate_min_profit(cls, v):
        if v <= -1000:
            raise ValueError(
                "min_profit_bps too low - would result in guaranteed losses"
            )
        return v

    @model_validator(mode="after")
    def validate_profit_slippage_relationship(self):
        if self.min_profit_bps and self.max_slippage_bps:
            # Warn if slippage threshold is higher than profit threshold
            if self.max_slippage_bps > self.min_profit_bps:
                # This is allowed but worth noting in logs during runtime
                pass
        return self

    model_config = {
        "extra": "forbid",  # Disallow extra fields
        "validate_assignment": True,
    }


def validate_strategy_config(config_dict: Dict) -> StrategyConfig:
    """
    Validate a strategy configuration dictionary

    Args:
        config_dict: Dictionary representation of strategy config

    Returns:
        Validated StrategyConfig object

    Raises:
        ValidationError: If configuration is invalid
    """
    return StrategyConfig(**config_dict)


def validate_config_file(config_path: Union[str, Path]) -> StrategyConfig:
    """
    Validate a strategy configuration file

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Validated StrategyConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If configuration is invalid
        yaml.YAMLError: If YAML parsing fails
    """
    import yaml
    from pathlib import Path

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)

    if config_dict is None:
        raise ValueError("Configuration file is empty or invalid")

    return validate_strategy_config(config_dict)
