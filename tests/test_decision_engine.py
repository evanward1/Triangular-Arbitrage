#!/usr/bin/env python3
"""
Tests for Decision Engine
"""

import pytest

from decision_engine import DecisionEngine


class TestDecisionEngine:
    """Test suite for DecisionEngine"""

    def test_decision_engine_threshold_exec(self):
        """Test that opportunity with net profit above threshold returns EXECUTE"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.20})

        # Create opportunity: gross 0.80%, fees 0.30%, slip 0.05%, gas 0.05% → net 0.40%
        decision = engine.evaluate_opportunity(
            gross_pct=0.80,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )

        assert decision.action == "EXECUTE"
        assert len(decision.reasons) == 0
        assert abs(decision.metrics["net_pct"] - 0.40) < 0.001
        assert abs(decision.metrics["gross_pct"] - 0.80) < 0.001
        assert (
            abs(decision.metrics["breakeven_gross_pct"] - 0.60) < 0.001
        )  # 0.20 + 0.30 + 0.05 + 0.05

    def test_decision_engine_threshold_skip(self):
        """Test that opportunity with net profit below threshold returns SKIP with reason"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.20})

        # Create opportunity: gross 0.39%, fees 0.30%, slip 0.05%, gas 0.00% → net 0.04%
        decision = engine.evaluate_opportunity(
            gross_pct=0.39,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=100.0,
        )

        assert decision.action == "SKIP"
        assert len(decision.reasons) > 0
        assert any("threshold" in r for r in decision.reasons)
        assert abs(decision.metrics["net_pct"] - 0.04) < 0.001

    def test_decision_engine_size_too_small(self):
        """Test that size below minimum returns SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.10})

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=5.0,  # Below $10 minimum
        )

        assert decision.action == "SKIP"
        assert any("size" in r and "min" in r for r in decision.reasons)

    def test_decision_engine_size_too_large(self):
        """Test that size above maximum returns SKIP"""
        engine = DecisionEngine(
            {"min_profit_threshold_pct": 0.10, "max_position_usd": 5000.0}
        )

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=10000.0,  # Above $5000 maximum
        )

        assert decision.action == "SKIP"
        assert any("size" in r and "max" in r for r in decision.reasons)

    def test_decision_engine_depth_limited(self):
        """Test that depth-limited size below minimum returns SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.10})

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            depth_limited_size_usd=8.0,  # Reduced below $10 minimum
        )

        assert decision.action == "SKIP"
        assert any("depth" in r for r in decision.reasons)
        assert decision.metrics["depth_limited_size_usd"] == 8.0

    def test_decision_engine_maker_legs(self):
        """Test that insufficient maker legs returns SKIP"""
        engine = DecisionEngine(
            {"min_profit_threshold_pct": 0.10, "expected_maker_legs": 2}
        )

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            actual_maker_legs=1,  # Less than expected 2
        )

        assert decision.action == "SKIP"
        assert any("maker_legs" in r for r in decision.reasons)

    def test_decision_engine_concurrent_limit(self):
        """Test that concurrent trade limit returns SKIP"""
        engine = DecisionEngine(
            {"min_profit_threshold_pct": 0.10, "max_concurrent_trades": 2}
        )

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            current_concurrent_trades=2,  # At limit
        )

        assert decision.action == "SKIP"
        assert any("concurrent" in r for r in decision.reasons)

    def test_decision_engine_cooldown(self):
        """Test that cooldown period returns SKIP"""
        engine = DecisionEngine(
            {"min_profit_threshold_pct": 0.10, "cooldown_seconds": 30.0}
        )

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            seconds_since_last_trade=10.0,  # Less than 30s cooldown
        )

        assert decision.action == "SKIP"
        assert any("cooldown" in r for r in decision.reasons)

    def test_decision_engine_exchange_not_ready(self):
        """Test that exchange not ready returns SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.10})

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            exchange_ready=False,
        )

        assert decision.action == "SKIP"
        assert any("exchange" in r for r in decision.reasons)

    def test_decision_engine_missing_quote(self):
        """Test that missing quote data returns SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.10})

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            has_quote=False,
        )

        assert decision.action == "SKIP"
        assert any("quote" in r for r in decision.reasons)

    def test_decision_engine_missing_gas_estimate(self):
        """Test that missing gas estimate returns SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.10})

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            has_gas_estimate=False,
        )

        assert decision.action == "SKIP"
        assert any("gas" in r and "estimate" in r for r in decision.reasons)

    def test_decision_engine_multiple_reasons(self):
        """Test that multiple rejection reasons are all captured"""
        engine = DecisionEngine(
            {"min_profit_threshold_pct": 0.50, "expected_maker_legs": 2}
        )

        decision = engine.evaluate_opportunity(
            gross_pct=0.60,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=5.0,  # Too small
            actual_maker_legs=0,  # Too few
        )

        assert decision.action == "SKIP"
        # Should have at least 2 reasons: size and maker_legs
        assert len(decision.reasons) >= 2
        assert any("size" in r for r in decision.reasons)
        assert any("maker_legs" in r for r in decision.reasons)

    def test_decision_engine_per_leg_notional(self):
        """Test that per-leg notional below minimum returns SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.10})

        legs_data = [
            {"notional_usd": 4.0},  # Below $5 minimum
            {"notional_usd": 10.0},
            {"notional_usd": 15.0},
        ]

        decision = engine.evaluate_opportunity(
            gross_pct=1.00,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=1000.0,
            legs_data=legs_data,
        )

        assert decision.action == "SKIP"
        assert any("leg1" in r and "notional" in r for r in decision.reasons)

    def test_format_decision_log(self):
        """Test decision log formatting"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.20})

        decision = engine.evaluate_opportunity(
            gross_pct=0.80,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )

        log = engine.format_decision_log(decision)

        assert "Decision EXECUTE" in log
        assert "reasons=[none]" in log or "reasons=[]" in log
        assert "gross=0.8" in log
        assert "net=0.4" in log
        assert "breakeven=0.6" in log
        assert "size=$1000" in log

    def test_format_decision_log_with_skip(self):
        """Test decision log formatting for SKIP"""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.20})

        decision = engine.evaluate_opportunity(
            gross_pct=0.39,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.00,
            size_usd=100.0,
        )

        log = engine.format_decision_log(decision)

        assert "Decision SKIP" in log
        assert "threshold" in log
        assert "net=0.04" in log

    def test_string_input_conversion(self):
        """Test that string inputs are converted to float/int at the edge"""
        engine = DecisionEngine({"min_profit_threshold_pct": "0.20"})

        # Pass strings instead of floats
        decision = engine.evaluate_opportunity(
            gross_pct="0.80",
            fees_pct="0.30",
            slip_pct="0.05",
            gas_pct="0.05",
            size_usd="1000.0",
        )

        assert decision.action == "EXECUTE"
        assert isinstance(decision.metrics["gross_pct"], float)
        assert isinstance(decision.metrics["net_pct"], float)
        assert isinstance(decision.metrics["size_usd"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
