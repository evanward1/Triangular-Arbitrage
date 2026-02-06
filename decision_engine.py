#!/usr/bin/env python3
"""
Decision Engine for Triangular Arbitrage
Provides explicit trade execution decisions with detailed reasoning and metrics
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from triangular_arbitrage.metrics import VolatilityMonitor

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    """
    Represents a trade execution decision with full reasoning and metrics.

    All percentages are stored as floats (e.g., 0.25 for 0.25%, not 25.0 or 0.0025).
    Conversion to bps happens only for display/logging purposes.
    """

    action: str  # "EXECUTE" or "SKIP"
    reasons: List[str] = field(
        default_factory=list
    )  # Empty for EXECUTE, list of issues for SKIP
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary for JSON serialization"""
        return {"action": self.action, "reasons": self.reasons, "metrics": self.metrics}


class DecisionEngine:
    """
    Unified decision engine for both CEX and DEX arbitrage opportunities.

    Responsibilities:
    1. Compute breakeven gross percentage from threshold, fees, slippage, and gas
    2. Evaluate opportunities against all execution criteria
    3. Return explicit EXECUTE or SKIP decisions with detailed reasoning
    4. Convert all numeric inputs from strings to float/int at the edge
    5. Never round percentages until after decision is made

    All internal calculations use percentages (not bps).
    """

    # Minimum position size in USD to prevent dust trades
    MIN_POSITION_USD = 10.0

    # Minimum notional per leg in USD (for CEX to avoid exchange minimums)
    LEG_MIN_NOTIONAL_USD = 5.0

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize decision engine with configuration.

        Args:
            config: Configuration dictionary with keys:
                - min_profit_threshold_pct: Minimum net profit threshold in percent
                - max_position_usd: Maximum position size in USD
                - expected_maker_legs: Expected number of maker legs (optional)
                - max_concurrent_trades: Maximum concurrent trades (optional)
                - cooldown_seconds: Cooldown between trades (optional)
                - volatility_window_size: Rolling window size for dynamic
                  threshold (optional, enables dynamic mode)
                - sigma_multiplier: Number of standard deviations above the
                  moving average for the dynamic threshold (optional, default 1.5)
        """
        self.config = config or {}

        # Convert string inputs to proper types at the edge
        self.min_profit_threshold_pct = float(
            self.config.get("min_profit_threshold_pct", 0.0)
        )
        self.max_position_usd = float(self.config.get("max_position_usd", 10000.0))
        self.expected_maker_legs = (
            int(self.config.get("expected_maker_legs"))
            if self.config.get("expected_maker_legs") is not None
            else None
        )
        self.max_concurrent_trades = (
            int(self.config.get("max_concurrent_trades"))
            if self.config.get("max_concurrent_trades") is not None
            else None
        )
        self.cooldown_seconds = (
            float(self.config.get("cooldown_seconds"))
            if self.config.get("cooldown_seconds") is not None
            else None
        )

        # Volatility-based dynamic thresholds (optional)
        self.volatility_window_size = (
            int(self.config.get("volatility_window_size"))
            if self.config.get("volatility_window_size") is not None
            else None
        )
        self.sigma_multiplier = (
            float(self.config.get("sigma_multiplier"))
            if self.config.get("sigma_multiplier") is not None
            else None
        )

        self._volatility_monitor = None
        if self.volatility_window_size is not None and self.sigma_multiplier is not None:
            self._volatility_monitor = VolatilityMonitor(
                window_size=self.volatility_window_size
            )

    def evaluate_opportunity(
        self,
        gross_pct: float,
        fees_pct: float,
        slip_pct: float,
        gas_pct: float,
        size_usd: float,
        depth_limited_size_usd: Optional[float] = None,
        actual_maker_legs: Optional[int] = None,
        current_concurrent_trades: int = 0,
        seconds_since_last_trade: Optional[float] = None,
        exchange_ready: bool = True,
        legs_data: Optional[List[Dict[str, Any]]] = None,
        has_quote: bool = True,
        has_gas_estimate: bool = True,
    ) -> Decision:
        """
        Evaluate an arbitrage opportunity and return an execution decision.

        All percentage inputs should be in percent format (e.g., 0.25 for 0.25%).

        Args:
            gross_pct: Gross profit percentage before fees/slippage/gas
            fees_pct: Total fees percentage
            slip_pct: Slippage percentage
            gas_pct: Gas cost percentage (for DEX, 0 for CEX)
            size_usd: Proposed execution size in USD
            depth_limited_size_usd: Size after depth limiting (if reduced)
            actual_maker_legs: Actual number of maker legs (for CEX)
            current_concurrent_trades: Number of trades currently executing
            seconds_since_last_trade: Time since last trade (for cooldown check)
            exchange_ready: Whether exchange connections are ready
            legs_data: Optional list of leg details with notional amounts
            has_quote: Whether quote data is available (for DEX)
            has_gas_estimate: Whether gas estimate is available (for DEX)

        Returns:
            Decision object with action ("EXECUTE" or "SKIP"), reasons, and metrics
        """
        # Convert all inputs to float at the edge (defensive programming)
        gross_pct = float(gross_pct)
        fees_pct = float(fees_pct)
        slip_pct = float(slip_pct)
        gas_pct = float(gas_pct)
        size_usd = float(size_usd)

        # Calculate net profit
        net_pct = gross_pct - fees_pct - slip_pct - gas_pct

        # Feed observation to volatility monitor (always, regardless of decision)
        if self._volatility_monitor is not None:
            self._volatility_monitor.add_observation(net_pct)

        # Determine effective threshold: dynamic if monitor is ready, static otherwise
        effective_threshold = self.min_profit_threshold_pct
        using_dynamic = False
        if self._volatility_monitor is not None and self._volatility_monitor.is_ready:
            dynamic = self._volatility_monitor.get_dynamic_threshold(
                self.sigma_multiplier
            )
            if dynamic is not None:
                effective_threshold = dynamic
                using_dynamic = True

        # Calculate breakeven gross (minimum gross needed to meet threshold after costs)
        breakeven_gross_pct = effective_threshold + fees_pct + slip_pct + gas_pct

        # Build metrics dictionary
        metrics = {
            "gross_pct": gross_pct,
            "net_pct": net_pct,
            "breakeven_gross_pct": breakeven_gross_pct,
            "fees_pct": fees_pct,
            "slip_pct": slip_pct,
            "gas_pct": gas_pct,
            "size_usd": size_usd,
        }

        # Add dynamic threshold diagnostics when volatility monitoring is active
        if self._volatility_monitor is not None:
            metrics["volatility_window_count"] = self._volatility_monitor.count
            metrics["using_dynamic_threshold"] = 1.0 if using_dynamic else 0.0
            metrics["effective_threshold_pct"] = effective_threshold
            sigma = self._volatility_monitor.get_sigma()
            if sigma is not None:
                metrics["volatility_sigma"] = sigma
            moving_avg = self._volatility_monitor.get_moving_average()
            if moving_avg is not None:
                metrics["volatility_moving_avg"] = moving_avg

        # Collect rejection reasons
        reasons = []

        # Check 1: Net profit must meet or exceed threshold
        if net_pct < effective_threshold:
            reasons.append(
                f"threshold: net {net_pct:.4f}% < {effective_threshold:.4f}%"
                + (" (dynamic)" if using_dynamic else "")
            )

        # Check 2: Size must be within limits
        if size_usd < self.MIN_POSITION_USD:
            reasons.append(f"size: ${size_usd:.2f} < min ${self.MIN_POSITION_USD:.2f}")

        if size_usd > self.max_position_usd:
            reasons.append(f"size: ${size_usd:.2f} > max ${self.max_position_usd:.2f}")

        # Check 3: Depth-limited size check
        if depth_limited_size_usd is not None:
            depth_limited_size_usd = float(depth_limited_size_usd)
            if depth_limited_size_usd < self.MIN_POSITION_USD:
                reasons.append(
                    f"depth: reduced to ${depth_limited_size_usd:.2f} < min ${self.MIN_POSITION_USD:.2f}"
                )
            metrics["depth_limited_size_usd"] = depth_limited_size_usd

        # Check 4: Per-leg notional minimums (for CEX)
        if legs_data:
            for i, leg in enumerate(legs_data):
                notional_usd = float(leg.get("notional_usd", 0))
                if notional_usd < self.LEG_MIN_NOTIONAL_USD:
                    reasons.append(
                        f"leg{i+1}: notional ${notional_usd:.2f} < min ${self.LEG_MIN_NOTIONAL_USD:.2f}"
                    )

        # Check 5: Expected maker legs (for CEX fee optimization)
        if self.expected_maker_legs is not None and actual_maker_legs is not None:
            actual_maker_legs = int(actual_maker_legs)
            if actual_maker_legs < self.expected_maker_legs:
                reasons.append(
                    f"maker_legs: {actual_maker_legs} < expected {self.expected_maker_legs}"
                )
            metrics["actual_maker_legs"] = actual_maker_legs

        # Check 6: Concurrent trade limits
        if self.max_concurrent_trades is not None:
            if current_concurrent_trades >= self.max_concurrent_trades:
                reasons.append(
                    f"concurrent: {current_concurrent_trades} >= max {self.max_concurrent_trades}"
                )

        # Check 7: Cooldown period
        if self.cooldown_seconds is not None and seconds_since_last_trade is not None:
            seconds_since_last_trade = float(seconds_since_last_trade)
            if seconds_since_last_trade < self.cooldown_seconds:
                reasons.append(
                    f"cooldown: {seconds_since_last_trade:.1f}s < {self.cooldown_seconds:.1f}s"
                )

        # Check 8: Exchange connectivity
        if not exchange_ready:
            reasons.append("exchange: not ready")

        # Check 9: Quote availability (for DEX)
        if not has_quote:
            reasons.append("quote: missing")

        # Check 10: Gas estimate availability (for DEX)
        if not has_gas_estimate:
            reasons.append("gas: estimate missing")

        # Make decision
        if reasons:
            return Decision(action="SKIP", reasons=reasons, metrics=metrics)
        else:
            return Decision(action="EXECUTE", reasons=[], metrics=metrics)

    def format_decision_log(
        self, decision: Decision, timestamp: Optional[str] = None
    ) -> str:
        """
        Format a decision as a single-line log entry.

        Args:
            decision: Decision object to format
            timestamp: Optional timestamp string (will use current time if not provided)

        Returns:
            Formatted log string
        """
        m = decision.metrics

        # Format reasons compactly
        reasons_str = ", ".join(decision.reasons) if decision.reasons else "none"

        # Build log line with all metrics
        parts = [
            f"Decision {decision.action}",
            f"reasons=[{reasons_str}]",
            "metrics:",
            f"gross={m.get('gross_pct', 0):.4f}%",
            f"net={m.get('net_pct', 0):.4f}%",
            f"breakeven={m.get('breakeven_gross_pct', 0):.4f}%",
            f"fees={m.get('fees_pct', 0):.4f}%",
            f"slip={m.get('slip_pct', 0):.4f}%",
            f"gas={m.get('gas_pct', 0):.4f}%",
            f"size=${m.get('size_usd', 0):.2f}",
        ]

        # Add optional metrics if present
        if "depth_limited_size_usd" in m:
            parts.append(f"depth_size=${m['depth_limited_size_usd']:.2f}")
        if "actual_maker_legs" in m:
            parts.append(f"maker_legs={m['actual_maker_legs']}")
        if "effective_threshold_pct" in m:
            parts.append(f"threshold={m['effective_threshold_pct']:.4f}%")
        if "volatility_sigma" in m:
            parts.append(f"sigma={m['volatility_sigma']:.4f}")

        log_line = " ".join(parts)

        if timestamp:
            return f"[{timestamp}] {log_line}"
        else:
            return log_line
