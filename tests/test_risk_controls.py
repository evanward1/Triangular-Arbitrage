import pytest
import time
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from triangular_arbitrage.risk_controls import (
    LatencyMonitor,
    SlippageTracker,
    RiskControlLogger,
    RiskControlManager,
    LatencyMeasurement,
    SlippageMeasurement,
    RiskControlViolation,
)


class TestLatencyMonitor:
    def test_latency_measurement_basic(self):
        monitor = LatencyMonitor(max_leg_latency_ms=100)

        start_time = monitor.start_measurement()
        time.sleep(0.05)

        measurement = monitor.end_measurement(
            leg_index=0, market_symbol="BTC/USDT", start_time=start_time, side="buy"
        )

        assert measurement.leg_index == 0
        assert measurement.market_symbol == "BTC/USDT"
        assert measurement.side == "buy"
        assert 40 <= measurement.latency_ms <= 80

    def test_latency_violation_detection(self):
        monitor = LatencyMonitor(max_leg_latency_ms=50)

        start_time = time.time() - 0.1

        measurement = monitor.end_measurement(
            leg_index=0, market_symbol="ETH/USDT", start_time=start_time, side="sell"
        )

        assert monitor.check_violation(measurement) is True
        assert measurement.latency_ms > 50

    def test_latency_no_violation(self):
        monitor = LatencyMonitor(max_leg_latency_ms=1000)

        start_time = monitor.start_measurement()
        time.sleep(0.01)

        measurement = monitor.end_measurement(
            leg_index=0, market_symbol="BTC/USDT", start_time=start_time, side="buy"
        )

        assert monitor.check_violation(measurement) is False

    def test_multiple_measurements(self):
        monitor = LatencyMonitor(max_leg_latency_ms=100)

        for i in range(3):
            start_time = monitor.start_measurement()
            time.sleep(0.01)
            monitor.end_measurement(i, f"PAIR{i}/USDT", start_time, "buy")

        measurements = monitor.get_all_measurements()
        assert len(measurements) == 3

    def test_reset_measurements(self):
        monitor = LatencyMonitor(max_leg_latency_ms=100)

        start_time = monitor.start_measurement()
        monitor.end_measurement(0, "BTC/USDT", start_time, "buy")

        assert len(monitor.get_all_measurements()) == 1

        monitor.reset()
        assert len(monitor.get_all_measurements()) == 0


class TestSlippageTracker:
    def test_slippage_calculation_buy(self):
        tracker = SlippageTracker(max_slippage_bps=20)

        expected_price = 100.0
        executed_price = 101.0

        measurement = tracker.calculate_slippage(
            leg_index=0,
            market_symbol="BTC/USDT",
            expected_price=expected_price,
            executed_price=executed_price,
            side="buy",
        )

        assert measurement.slippage_bps == pytest.approx(100.0, rel=0.01)
        assert measurement.expected_price == 100.0
        assert measurement.executed_price == 101.0

    def test_slippage_calculation_sell(self):
        tracker = SlippageTracker(max_slippage_bps=20)

        expected_price = 100.0
        executed_price = 99.0

        measurement = tracker.calculate_slippage(
            leg_index=0,
            market_symbol="ETH/USDT",
            expected_price=expected_price,
            executed_price=executed_price,
            side="sell",
        )

        assert measurement.slippage_bps == pytest.approx(100.0, rel=0.01)

    def test_slippage_violation_detection(self):
        tracker = SlippageTracker(max_slippage_bps=50)

        measurement = tracker.calculate_slippage(
            leg_index=0,
            market_symbol="BTC/USDT",
            expected_price=100.0,
            executed_price=101.0,
            side="buy",
        )

        assert tracker.check_violation(measurement) is True

    def test_slippage_no_violation(self):
        tracker = SlippageTracker(max_slippage_bps=200)

        measurement = tracker.calculate_slippage(
            leg_index=0,
            market_symbol="BTC/USDT",
            expected_price=100.0,
            executed_price=100.5,
            side="buy",
        )

        assert tracker.check_violation(measurement) is False

    def test_cooldown_mechanism(self):
        tracker = SlippageTracker(max_slippage_bps=20, cooldown_seconds=2)

        cycle_key = "BTC->ETH->USDT"

        assert tracker.is_in_cooldown(cycle_key) is False

        tracker.add_to_cooldown(cycle_key)

        assert tracker.is_in_cooldown(cycle_key) is True

        remaining = tracker.get_cooldown_remaining(cycle_key)
        assert 1.5 <= remaining <= 2.0

        time.sleep(2.1)

        assert tracker.is_in_cooldown(cycle_key) is False
        assert tracker.get_cooldown_remaining(cycle_key) == 0.0

    def test_cleanup_expired_cooldowns(self):
        tracker = SlippageTracker(max_slippage_bps=20, cooldown_seconds=1)

        tracker.add_to_cooldown("cycle1")
        tracker.add_to_cooldown("cycle2")
        tracker.add_to_cooldown("cycle3")

        assert len(tracker.cooldown_cycles) == 3

        time.sleep(1.1)

        expired_count = tracker.cleanup_expired_cooldowns()

        assert expired_count == 3
        assert len(tracker.cooldown_cycles) == 0


class TestRiskControlLogger:
    @pytest.fixture
    def temp_log_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_log_violation_creates_file(self, temp_log_dir):
        logger = RiskControlLogger(log_dir=temp_log_dir)

        violation = RiskControlViolation(
            timestamp=time.time(),
            cycle_id="test_cycle_123",
            strategy_name="strategy_1",
            violation_type="LATENCY_EXCEEDED",
            cycle_path=["BTC", "ETH", "USDT"],
            cycle_direction="->",
            expected_prices=[],
            actual_prices=[],
            latencies_ms=[150.5, 75.2, 200.3],
            slippages_bps=[],
            threshold_violated={"max_leg_latency_ms": 100, "violated_leg": 2},
            leg_details=[
                {
                    "leg_index": 0,
                    "market": "ETH/BTC",
                    "side": "buy",
                    "latency_ms": 150.5,
                },
                {
                    "leg_index": 1,
                    "market": "USDT/ETH",
                    "side": "buy",
                    "latency_ms": 75.2,
                },
                {
                    "leg_index": 2,
                    "market": "BTC/USDT",
                    "side": "sell",
                    "latency_ms": 200.3,
                },
            ],
            metadata={},
        )

        logger.log_violation(violation)

        assert logger.json_log_file.exists()

        with open(logger.json_log_file, "r") as f:
            logged_data = json.loads(f.readline())

        assert logged_data["cycle_id"] == "test_cycle_123"
        assert logged_data["violation_type"] == "LATENCY_EXCEEDED"
        assert len(logged_data["latencies_ms"]) == 3

    def test_get_violation_stats(self, temp_log_dir):
        logger = RiskControlLogger(log_dir=temp_log_dir)

        for i in range(5):
            violation = RiskControlViolation(
                timestamp=time.time(),
                cycle_id=f"cycle_{i}",
                strategy_name="strategy_1" if i < 3 else "strategy_2",
                violation_type="LATENCY_EXCEEDED" if i < 2 else "SLIPPAGE_EXCEEDED",
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="->",
                expected_prices=[],
                actual_prices=[],
                latencies_ms=[],
                slippages_bps=[],
                threshold_violated={},
                leg_details=[],
                metadata={},
            )
            logger.log_violation(violation)

        stats = logger.get_violation_stats()

        assert stats["total_violations"] == 5
        assert stats["by_type"]["LATENCY_EXCEEDED"] == 2
        assert stats["by_type"]["SLIPPAGE_EXCEEDED"] == 3
        assert stats["by_strategy"]["strategy_1"] == 3
        assert stats["by_strategy"]["strategy_2"] == 2


class TestSlippageCooldownManager:
    def test_cooldown_prevents_immediate_retry(self):
        tracker = SlippageTracker(max_slippage_bps=20, cooldown_seconds=5)

        cycle_key = "BTC->ETH->USDT"
        tracker.add_to_cooldown(cycle_key)

        assert tracker.is_in_cooldown(cycle_key) is True

        time.sleep(1)
        assert tracker.is_in_cooldown(cycle_key) is True

    def test_multiple_cycles_in_cooldown(self):
        tracker = SlippageTracker(max_slippage_bps=20, cooldown_seconds=10)

        tracker.add_to_cooldown("cycle1")
        tracker.add_to_cooldown("cycle2")
        tracker.add_to_cooldown("cycle3")

        assert tracker.is_in_cooldown("cycle1") is True
        assert tracker.is_in_cooldown("cycle2") is True
        assert tracker.is_in_cooldown("cycle3") is True
        assert tracker.is_in_cooldown("cycle4") is False


class TestRiskControlManager:
    @pytest.fixture
    def temp_log_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_manager_initialization(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_log_dir,
        )

        assert manager.latency_monitor.max_leg_latency_ms == 100
        assert manager.slippage_tracker.max_slippage_bps == 50
        assert manager.slippage_tracker.cooldown_seconds == 300

    def test_latency_tracking_workflow(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=50, max_slippage_bps=100, log_dir=temp_log_dir
        )

        start_time = manager.start_leg_timing()
        time.sleep(0.06)

        measurement, violated = manager.end_leg_timing(
            leg_index=0, market_symbol="BTC/USDT", start_time=start_time, side="buy"
        )

        assert violated is True
        assert measurement.latency_ms > 50

    def test_slippage_tracking_workflow(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=1000, max_slippage_bps=50, log_dir=temp_log_dir
        )

        measurement, violated = manager.track_slippage(
            leg_index=0,
            market_symbol="ETH/USDT",
            expected_price=100.0,
            executed_price=101.0,
            side="buy",
        )

        assert violated is True
        assert measurement.slippage_bps > 50

    def test_cycle_cooldown_check(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=1000,
            max_slippage_bps=20,
            slippage_cooldown_seconds=5,
            log_dir=temp_log_dir,
        )

        cycle_path = ["BTC", "ETH", "USDT"]

        assert manager.is_cycle_in_cooldown(cycle_path) is False

        manager.slippage_tracker.add_to_cooldown("->".join(cycle_path))

        assert manager.is_cycle_in_cooldown(cycle_path) is True

        remaining = manager.get_cycle_cooldown_remaining(cycle_path)
        assert 4.5 <= remaining <= 5.0

    def test_log_latency_violation(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, log_dir=temp_log_dir
        )

        start_time = time.time() - 0.15
        measurement = LatencyMeasurement(
            leg_index=1,
            market_symbol="ETH/USDT",
            start_time=start_time,
            end_time=time.time(),
            latency_ms=150.0,
            side="buy",
        )

        manager.log_latency_violation(
            cycle_id="test_cycle",
            strategy_name="strategy_1",
            cycle_path=["BTC", "ETH", "USDT"],
            cycle_direction="->",
            violated_leg=measurement,
        )

        assert manager.logger.json_log_file.exists()

    def test_log_slippage_violation(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=1000,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_log_dir,
        )

        measurement = SlippageMeasurement(
            leg_index=0,
            market_symbol="BTC/USDT",
            expected_price=100.0,
            executed_price=102.0,
            slippage_bps=200.0,
            side="buy",
        )

        cycle_path = ["BTC", "ETH", "USDT"]

        manager.log_slippage_violation(
            cycle_id="test_cycle",
            strategy_name="strategy_1",
            cycle_path=cycle_path,
            cycle_direction="->",
            violated_leg=measurement,
        )

        assert manager.is_cycle_in_cooldown(cycle_path) is True

    def test_reset_cycle_measurements(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, log_dir=temp_log_dir
        )

        start_time = manager.start_leg_timing()
        manager.end_leg_timing(0, "BTC/USDT", start_time, "buy")

        manager.track_slippage(0, "ETH/USDT", 100.0, 101.0, "buy")

        assert len(manager.latency_monitor.get_all_measurements()) == 1
        assert len(manager.slippage_tracker.get_all_measurements()) == 1

        manager.reset_cycle_measurements()

        assert len(manager.latency_monitor.get_all_measurements()) == 0
        assert len(manager.slippage_tracker.get_all_measurements()) == 0

    def test_get_stats(self, temp_log_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=300,
            log_dir=temp_log_dir,
        )

        stats = manager.get_stats()

        assert "violations" in stats
        assert "active_cooldowns" in stats
        assert "config" in stats
        assert stats["config"]["max_leg_latency_ms"] == 100
        assert stats["config"]["max_slippage_bps"] == 50
        assert stats["config"]["cooldown_seconds"] == 300


class TestConfigurationIntegration:
    def test_yaml_config_loading(self, tmp_path):
        config_file = tmp_path / "test_strategy.yaml"
        config_content = """
name: test_strategy
exchange: coinbase
min_profit_bps: 10
max_slippage_bps: 25
max_leg_latency_ms: 150
capital_allocation:
  mode: fixed_fraction
  fraction: 0.5
risk_controls:
  max_open_cycles: 2
  stop_after_consecutive_losses: 3
  slippage_cooldown_seconds: 600
  enable_latency_checks: true
  enable_slippage_checks: true
"""
        config_file.write_text(config_content)

        import yaml

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        assert config["max_leg_latency_ms"] == 150
        assert config["max_slippage_bps"] == 25
        assert config["risk_controls"]["slippage_cooldown_seconds"] == 600
        assert config["risk_controls"]["enable_latency_checks"] is True
        assert config["risk_controls"]["enable_slippage_checks"] is True


class TestCooldownPersistence:
    @pytest.fixture
    def temp_state_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_save_cooldowns_creates_file(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")

        manager.save_cooldowns(state_file)

        assert Path(state_file).exists()

        with open(state_file, "r") as f:
            data = json.load(f)

        assert len(data) == 2
        assert "BTC->ETH->USDT" in data
        assert "ETH->USDT->BTC" in data

    def test_save_cooldowns_atomic_write(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=5
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.save_cooldowns(state_file)

        temp_files = [
            f for f in os.listdir(temp_state_dir) if f.startswith(".cooldowns_")
        ]
        assert len(temp_files) == 0

    def test_load_cooldowns_restores_state(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"

        manager1 = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        manager1.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager1.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")
        manager1.save_cooldowns(state_file)

        manager2 = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        restored = manager2.load_cooldowns(state_file)

        assert restored == 2
        assert manager2.is_cycle_in_cooldown(["BTC", "ETH", "USDT"])
        assert manager2.is_cycle_in_cooldown(["ETH", "USDT", "BTC"])

    def test_load_cooldowns_filters_expired(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"

        manager1 = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=1
        )

        manager1.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager1.save_cooldowns(state_file)

        time.sleep(1.2)

        manager2 = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=1
        )

        restored = manager2.load_cooldowns(state_file)

        assert restored == 0
        assert not manager2.is_cycle_in_cooldown(["BTC", "ETH", "USDT"])

    def test_simulated_restart_preserves_cooldown(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        cycle_path = ["BTC", "ETH", "USDT"]

        manager1 = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=5
        )

        assert not manager1.is_cycle_in_cooldown(cycle_path)

        manager1.slippage_tracker.add_to_cooldown("->".join(cycle_path))

        assert manager1.is_cycle_in_cooldown(cycle_path)

        manager1.save_cooldowns(state_file)

        manager2 = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=5
        )

        assert not manager2.is_cycle_in_cooldown(cycle_path)

        restored = manager2.load_cooldowns(state_file)
        assert restored == 1

        assert manager2.is_cycle_in_cooldown(cycle_path)

        time.sleep(5.1)

        assert not manager2.is_cycle_in_cooldown(cycle_path)

    def test_get_active_cooldowns(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        time.sleep(0.1)
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")

        active = manager.get_active_cooldowns()

        assert len(active) == 2
        assert all(isinstance(item, tuple) for item in active)
        assert all(len(item) == 2 for item in active)

        cycle_keys = [item[0] for item in active]
        assert "BTC->ETH->USDT" in cycle_keys
        assert "ETH->USDT->BTC" in cycle_keys

        remainings = [item[1] for item in active]
        assert all(r > 0 for r in remainings)
        assert all(r <= 10 for r in remainings)

    def test_load_nonexistent_file(self, temp_state_dir):
        state_file = f"{temp_state_dir}/nonexistent.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=5
        )

        restored = manager.load_cooldowns(state_file)
        assert restored == 0

    def test_clear_cooldown_active_pair(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)

        assert manager.is_cycle_in_cooldown(["BTC", "ETH", "USDT"])

        success = manager.clear_cooldown(pair)

        assert success is True
        assert not manager.is_cycle_in_cooldown(["BTC", "ETH", "USDT"])

        active = manager.get_active_cooldowns()
        assert len(active) == 0

        assert Path(state_file).exists()

        with open(state_file, "r") as f:
            data = json.load(f)
        assert pair not in data

    def test_clear_cooldown_inactive_pair(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        success = manager.clear_cooldown("BTC->ETH->USDT")

        assert success is False

    def test_clear_cooldown_updates_state_file(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")
        manager.save_cooldowns(state_file)

        with open(state_file, "r") as f:
            data_before = json.load(f)
        assert len(data_before) == 2

        manager.clear_cooldown("BTC->ETH->USDT")

        with open(state_file, "r") as f:
            data_after = json.load(f)

        assert len(data_after) == 1
        assert "BTC->ETH->USDT" not in data_after
        assert "ETH->USDT->BTC" in data_after

    def test_get_cooldown_end(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)

        end_time = manager.get_cooldown_end(pair)
        assert end_time is not None
        assert end_time > time.time()

        non_existent = manager.get_cooldown_end("NONEXISTENT")
        assert non_existent is None

    def test_extend_cooldown_increases_time(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)

        remaining_before = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])

        success = manager.extend_cooldown(pair, 5)

        assert success is True

        remaining_after = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])

        assert remaining_after > remaining_before
        assert abs(remaining_after - (remaining_before + 5)) < 0.1

        with open(state_file, "r") as f:
            data = json.load(f)
        assert pair in data

    def test_extend_cooldown_decreases_time(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)

        remaining_before = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])

        success = manager.extend_cooldown(pair, -5)

        assert success is True

        remaining_after = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])

        assert remaining_after < remaining_before

    def test_extend_cooldown_clamps_to_minimum(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        pair = "BTC->ETH->USDT"
        manager.slippage_tracker.add_to_cooldown(pair)

        success = manager.extend_cooldown(pair, -1000)

        assert success is True

        remaining = manager.get_cycle_cooldown_remaining(["BTC", "ETH", "USDT"])

        assert remaining >= 0.9
        assert remaining <= 2.0

    def test_extend_cooldown_not_found(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100, max_slippage_bps=50, slippage_cooldown_seconds=10
        )

        success = manager.extend_cooldown("NONEXISTENT", 10)

        assert success is False

    def test_clear_all_cooldowns(self, temp_state_dir):
        state_file = f"{temp_state_dir}/cooldowns_state.json"
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        manager.slippage_tracker.add_to_cooldown("BTC->ETH->USDT")
        manager.slippage_tracker.add_to_cooldown("ETH->USDT->BTC")
        manager.slippage_tracker.add_to_cooldown("USDT->BTC->ETH")
        manager.save_cooldowns()

        assert len(manager.slippage_tracker.cooldown_cycles) == 3

        count = manager.clear_all_cooldowns()

        assert count == 3
        assert len(manager.slippage_tracker.cooldown_cycles) == 0

        with open(state_file, "r") as f:
            data = json.load(f)
        assert len(data) == 0

    def test_clear_all_cooldowns_when_empty(self, temp_state_dir):
        manager = RiskControlManager(
            max_leg_latency_ms=100,
            max_slippage_bps=50,
            slippage_cooldown_seconds=10,
            log_dir=temp_state_dir,
        )

        count = manager.clear_all_cooldowns()

        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
