#!/usr/bin/env python3
"""
Tests for dynamic volatility-based thresholds in DecisionEngine.
"""

import pytest

from triangular_arbitrage.metrics import VolatilityMonitor
from decision_engine import DecisionEngine


class TestVolatilityMonitor:
    """Test suite for VolatilityMonitor in isolation."""

    def test_empty_monitor_returns_none(self):
        """Sigma and moving average are None with no data."""
        monitor = VolatilityMonitor(window_size=10)
        assert monitor.get_sigma() is None
        assert monitor.get_moving_average() is None
        assert monitor.get_dynamic_threshold(1.0) is None

    def test_single_observation_returns_none(self):
        """A single observation is not enough for statistics."""
        monitor = VolatilityMonitor(window_size=10)
        monitor.add_observation(0.5)
        assert monitor.count == 1
        assert monitor.get_sigma() is None
        assert monitor.get_moving_average() is None

    def test_moving_average_correctness(self):
        """Moving average is the mean of observations."""
        monitor = VolatilityMonitor(window_size=5)
        for val in [0.10, 0.20, 0.30, 0.40, 0.50]:
            monitor.add_observation(val)
        avg = monitor.get_moving_average()
        assert avg is not None
        assert abs(avg - 0.30) < 0.001

    def test_sigma_correctness(self):
        """Sigma is the population standard deviation."""
        monitor = VolatilityMonitor(window_size=5)
        # Values: 1, 2, 3, 4, 5 -> mean=3, variance=2, sigma=sqrt(2)
        for val in [1.0, 2.0, 3.0, 4.0, 5.0]:
            monitor.add_observation(val)
        sigma = monitor.get_sigma()
        assert sigma is not None
        assert abs(sigma - (2.0 ** 0.5)) < 0.001

    def test_dynamic_threshold_formula(self):
        """Dynamic threshold = moving_avg + sigma_multiplier * sigma."""
        monitor = VolatilityMonitor(window_size=5)
        for val in [1.0, 2.0, 3.0, 4.0, 5.0]:
            monitor.add_observation(val)
        # mean=3.0, sigma=sqrt(2)
        threshold = monitor.get_dynamic_threshold(1.0)
        assert threshold is not None
        assert abs(threshold - (3.0 + 2.0 ** 0.5)) < 0.001

    def test_is_ready_before_and_after_full(self):
        """is_ready becomes True only when window is fully populated."""
        monitor = VolatilityMonitor(window_size=5)
        for i in range(4):
            monitor.add_observation(float(i))
            assert not monitor.is_ready
        monitor.add_observation(4.0)
        assert monitor.is_ready

    def test_rolling_window_evicts_old(self):
        """Old observations are evicted when window overflows."""
        monitor = VolatilityMonitor(window_size=3)
        monitor.add_observation(100.0)
        monitor.add_observation(100.0)
        monitor.add_observation(100.0)
        assert abs(monitor.get_moving_average() - 100.0) < 0.001
        # Push in lower values, evicting the 100s
        monitor.add_observation(1.0)
        monitor.add_observation(1.0)
        monitor.add_observation(1.0)
        assert abs(monitor.get_moving_average() - 1.0) < 0.001

    def test_zero_sigma_multiplier(self):
        """With sigma_multiplier=0, threshold equals the moving average."""
        monitor = VolatilityMonitor(window_size=3)
        for val in [0.5, 0.5, 0.5]:
            monitor.add_observation(val)
        threshold = monitor.get_dynamic_threshold(0.0)
        avg = monitor.get_moving_average()
        assert threshold is not None and avg is not None
        assert abs(threshold - avg) < 0.001


class TestDecisionEngineDynamicThresholds:
    """Test DecisionEngine with volatility-based dynamic thresholds."""

    def _make_engine(self, **overrides):
        """Helper to create engine with volatility config."""
        config = {
            "min_profit_threshold_pct": 0.20,
            "max_position_usd": 10000.0,
            "volatility_window_size": 5,
            "sigma_multiplier": 1.0,
        }
        config.update(overrides)
        return DecisionEngine(config)

    def _feed_observations(self, engine, values):
        """Feed net_pct observations by calling evaluate_opportunity.

        Costs total 0.10 (fees=0.05 + slip=0.03 + gas=0.02),
        so gross_pct = desired_net + 0.10.
        """
        for net in values:
            engine.evaluate_opportunity(
                gross_pct=net + 0.10,
                fees_pct=0.05,
                slip_pct=0.03,
                gas_pct=0.02,
                size_usd=1000.0,
            )

    def test_backward_compat_no_volatility_config(self):
        """Without volatility config, engine uses static threshold."""
        engine = DecisionEngine({"min_profit_threshold_pct": 0.20})
        decision = engine.evaluate_opportunity(
            gross_pct=0.80,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        assert decision.action == "EXECUTE"
        assert abs(decision.metrics["net_pct"] - 0.40) < 0.001
        assert "effective_threshold_pct" not in decision.metrics

    def test_warmup_uses_static_threshold(self):
        """During warmup (insufficient data), static threshold is used."""
        engine = self._make_engine(volatility_window_size=10, sigma_multiplier=1.0)
        # Feed only 5 observations (window needs 10)
        self._feed_observations(engine, [0.3, 0.3, 0.3, 0.3, 0.3])

        decision = engine.evaluate_opportunity(
            gross_pct=0.80,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        # Static threshold is 0.20; net is 0.40 -> EXECUTE
        assert decision.action == "EXECUTE"
        assert abs(decision.metrics["using_dynamic_threshold"] - 0.0) < 0.001

    def test_quiet_market_lowers_threshold(self):
        """In a quiet market (low sigma), dynamic threshold can be lower than static."""
        engine = self._make_engine(
            min_profit_threshold_pct=0.50,
            volatility_window_size=5,
            sigma_multiplier=1.0,
        )
        # Feed 5 identical observations -> sigma=0, avg=0.20
        self._feed_observations(engine, [0.20, 0.20, 0.20, 0.20, 0.20])
        # Dynamic threshold = 0.20 + 1.0 * 0.0 = 0.20 (lower than static 0.50)
        decision = engine.evaluate_opportunity(
            gross_pct=0.70,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        # net = 0.30, dynamic threshold = 0.20 -> EXECUTE
        # (would have been SKIP with static 0.50 threshold)
        assert decision.action == "EXECUTE"
        assert abs(decision.metrics["using_dynamic_threshold"] - 1.0) < 0.001

    def test_noisy_market_raises_threshold(self):
        """In a noisy market (high sigma), dynamic threshold rejects marginal trades."""
        engine = self._make_engine(
            min_profit_threshold_pct=0.10,
            volatility_window_size=5,
            sigma_multiplier=2.0,
        )
        # Feed widely spread observations -> high sigma
        self._feed_observations(engine, [-1.0, -0.5, 0.0, 0.5, 1.0])
        # mean=0.0, sigma~0.7071, dynamic threshold = 0.0 + 2.0 * 0.7071 ~ 1.4142
        decision = engine.evaluate_opportunity(
            gross_pct=1.50,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        # net = 1.10, dynamic threshold ~ 1.41 -> SKIP
        assert decision.action == "SKIP"
        assert any("threshold" in r for r in decision.reasons)
        assert any("dynamic" in r for r in decision.reasons)

    def test_threshold_rises_during_noisy_period(self):
        """Threshold increases as volatile observations enter the window."""
        engine = self._make_engine(
            min_profit_threshold_pct=0.10,
            volatility_window_size=5,
            sigma_multiplier=1.0,
        )
        # Calm observations
        self._feed_observations(engine, [0.30, 0.30, 0.30, 0.30, 0.30])

        decision1 = engine.evaluate_opportunity(
            gross_pct=0.80,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        threshold_1 = decision1.metrics["effective_threshold_pct"]

        # Inject volatile observations (these push out calm ones)
        self._feed_observations(engine, [-1.0, 2.0, -1.0, 2.0, -1.0])

        decision2 = engine.evaluate_opportunity(
            gross_pct=0.80,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        threshold_2 = decision2.metrics["effective_threshold_pct"]

        assert threshold_2 > threshold_1

    def test_metrics_include_volatility_info(self):
        """Metrics dict contains volatility diagnostic fields when configured."""
        engine = self._make_engine(volatility_window_size=5, sigma_multiplier=1.0)
        self._feed_observations(engine, [0.1, 0.2, 0.3, 0.4, 0.5])

        decision = engine.evaluate_opportunity(
            gross_pct=5.0,
            fees_pct=0.30,
            slip_pct=0.05,
            gas_pct=0.05,
            size_usd=1000.0,
        )
        m = decision.metrics
        assert "volatility_window_count" in m
        assert "using_dynamic_threshold" in m
        assert "effective_threshold_pct" in m
        assert "volatility_sigma" in m
        assert "volatility_moving_avg" in m


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
