#!/usr/bin/env python3
"""
Unit tests for duplicate event suppression
"""

import tempfile
import shutil
import time
from triangular_arbitrage.risk_controls import RiskControlManager, RiskControlViolation


class TestDuplicateSuppression:
    def test_duplicate_within_window_suppressed(self):
        """Test that duplicate events within 2s window are suppressed"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            cycle_id = "test-cycle-1"
            stop_reason = "latency_exceeded"

            violation = RiskControlViolation(
                timestamp=time.time(),
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation, is_executed=False)

            time.sleep(0.1)

            manager.logger.log_violation(violation, is_executed=False)

            stats = manager.logger.get_suppression_stats()
            assert stats['total_duplicates_suppressed'] == 1
            assert stats['cache_size'] == 1

        finally:
            shutil.rmtree(temp_dir)

    def test_different_stop_reasons_not_suppressed(self):
        """Test that different stop reasons are not suppressed"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            cycle_id = "test-cycle-1"

            violation1 = RiskControlViolation(
                timestamp=time.time(),
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type="latency_exceeded",
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            violation2 = RiskControlViolation(
                timestamp=time.time(),
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type="slippage_exceeded",
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[100, 100, 100],
                slippages_bps=[100, 50, 50],
                threshold_violated={"slippage_bps": 100},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation1, is_executed=False)
            manager.logger.log_violation(violation2, is_executed=False)

            stats = manager.logger.get_suppression_stats()
            assert stats['total_duplicates_suppressed'] == 0
            assert stats['cache_size'] == 2

        finally:
            shutil.rmtree(temp_dir)

    def test_different_cycle_ids_not_suppressed(self):
        """Test that different cycle IDs are not suppressed"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            stop_reason = "latency_exceeded"

            violation1 = RiskControlViolation(
                timestamp=time.time(),
                cycle_id="test-cycle-1",
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            violation2 = RiskControlViolation(
                timestamp=time.time(),
                cycle_id="test-cycle-2",
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation1, is_executed=False)
            manager.logger.log_violation(violation2, is_executed=False)

            stats = manager.logger.get_suppression_stats()
            assert stats['total_duplicates_suppressed'] == 0
            assert stats['cache_size'] == 2

        finally:
            shutil.rmtree(temp_dir)

    def test_after_window_not_suppressed(self):
        """Test that events after >2s window are not suppressed"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=0.3,
                log_dir=temp_dir
            )

            cycle_id = "test-cycle-1"
            stop_reason = "latency_exceeded"

            ts1 = time.time()
            violation1 = RiskControlViolation(
                timestamp=ts1,
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation1, is_executed=False)

            time.sleep(0.4)

            ts2 = time.time()
            violation2 = RiskControlViolation(
                timestamp=ts2,
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation2, is_executed=False)

            stats = manager.logger.get_suppression_stats()
            assert stats['total_duplicates_suppressed'] == 0
            assert stats['cache_size'] == 1

        finally:
            shutil.rmtree(temp_dir)

    def test_executed_events_never_suppressed(self):
        """Test that executed events are never suppressed"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            cycle_id = "test-cycle-1"
            stop_reason = "executed"

            violation = RiskControlViolation(
                timestamp=time.time(),
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[100, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={},
                leg_details=[],
                metadata={"profit_bps": 10}
            )

            manager.logger.log_violation(violation, is_executed=True)

            time.sleep(0.1)

            manager.logger.log_violation(violation, is_executed=True)

            stats = manager.logger.get_suppression_stats()
            assert stats['total_duplicates_suppressed'] == 0

        finally:
            shutil.rmtree(temp_dir)

    def test_configurable_suppression_window(self):
        """Test that suppression window is configurable"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=5.0,
                log_dir=temp_dir
            )

            stats = manager.logger.get_suppression_stats()
            assert stats['suppression_window_seconds'] == 5.0

        finally:
            shutil.rmtree(temp_dir)


class TestSuppressedHistory:
    def test_get_recent_suppressed_returns_metadata(self):
        """Test that get_recent_suppressed returns correct metadata"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            cycle_id = "test-cycle-1"
            stop_reason = "latency_exceeded"

            ts1 = time.time()
            violation1 = RiskControlViolation(
                timestamp=ts1,
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation1, is_executed=False)

            time.sleep(0.1)

            ts2 = time.time()
            violation2 = RiskControlViolation(
                timestamp=ts2,
                cycle_id=cycle_id,
                strategy_name="test_strategy",
                violation_type=stop_reason,
                cycle_path=["BTC", "ETH", "USDT"],
                cycle_direction="forward",
                expected_prices=[1.0, 1.0, 1.0],
                actual_prices=[1.0, 1.0, 1.0],
                latencies_ms=[150, 100, 100],
                slippages_bps=[0, 0, 0],
                threshold_violated={"latency_ms": 150},
                leg_details=[],
                metadata={}
            )

            manager.logger.log_violation(violation2, is_executed=False)

            suppressed = manager.logger.get_recent_suppressed(limit=10)

            assert len(suppressed) == 1
            assert suppressed[0]['cycle_id'] == cycle_id
            assert suppressed[0]['stop_reason'] == stop_reason
            assert suppressed[0]['duplicate_count'] == 1
            assert suppressed[0]['first_seen'] == ts1
            assert suppressed[0]['last_seen'] == ts2

        finally:
            shutil.rmtree(temp_dir)

    def test_get_recent_suppressed_limit(self):
        """Test that get_recent_suppressed respects limit parameter"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            for i in range(15):
                ts = time.time()
                violation1 = RiskControlViolation(
                    timestamp=ts,
                    cycle_id=f"cycle-{i}",
                    strategy_name="test_strategy",
                    violation_type="latency_exceeded",
                    cycle_path=["BTC", "ETH", "USDT"],
                    cycle_direction="forward",
                    expected_prices=[1.0, 1.0, 1.0],
                    actual_prices=[1.0, 1.0, 1.0],
                    latencies_ms=[150, 100, 100],
                    slippages_bps=[0, 0, 0],
                    threshold_violated={"latency_ms": 150},
                    leg_details=[],
                    metadata={}
                )
                manager.logger.log_violation(violation1, is_executed=False)

                time.sleep(0.01)

                violation2 = RiskControlViolation(
                    timestamp=time.time(),
                    cycle_id=f"cycle-{i}",
                    strategy_name="test_strategy",
                    violation_type="latency_exceeded",
                    cycle_path=["BTC", "ETH", "USDT"],
                    cycle_direction="forward",
                    expected_prices=[1.0, 1.0, 1.0],
                    actual_prices=[1.0, 1.0, 1.0],
                    latencies_ms=[150, 100, 100],
                    slippages_bps=[0, 0, 0],
                    threshold_violated={"latency_ms": 150},
                    leg_details=[],
                    metadata={}
                )
                manager.logger.log_violation(violation2, is_executed=False)

            suppressed = manager.logger.get_recent_suppressed(limit=5)

            assert len(suppressed) == 5

            suppressed_all = manager.logger.get_recent_suppressed(limit=20)
            assert len(suppressed_all) == 15

        finally:
            shutil.rmtree(temp_dir)

    def test_get_recent_suppressed_sorted_by_last_seen(self):
        """Test that get_recent_suppressed returns most recent first"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            for i in range(3):
                ts = time.time()
                violation1 = RiskControlViolation(
                    timestamp=ts,
                    cycle_id=f"cycle-{i}",
                    strategy_name="test_strategy",
                    violation_type="latency_exceeded",
                    cycle_path=["BTC", "ETH", "USDT"],
                    cycle_direction="forward",
                    expected_prices=[1.0, 1.0, 1.0],
                    actual_prices=[1.0, 1.0, 1.0],
                    latencies_ms=[150, 100, 100],
                    slippages_bps=[0, 0, 0],
                    threshold_violated={"latency_ms": 150},
                    leg_details=[],
                    metadata={}
                )
                manager.logger.log_violation(violation1, is_executed=False)

                time.sleep(0.05)

                violation2 = RiskControlViolation(
                    timestamp=time.time(),
                    cycle_id=f"cycle-{i}",
                    strategy_name="test_strategy",
                    violation_type="latency_exceeded",
                    cycle_path=["BTC", "ETH", "USDT"],
                    cycle_direction="forward",
                    expected_prices=[1.0, 1.0, 1.0],
                    actual_prices=[1.0, 1.0, 1.0],
                    latencies_ms=[150, 100, 100],
                    slippages_bps=[0, 0, 0],
                    threshold_violated={"latency_ms": 150},
                    leg_details=[],
                    metadata={}
                )
                manager.logger.log_violation(violation2, is_executed=False)

                time.sleep(0.05)

            suppressed = manager.logger.get_recent_suppressed(limit=10)

            assert suppressed[0]['cycle_id'] == "cycle-2"
            assert suppressed[1]['cycle_id'] == "cycle-1"
            assert suppressed[2]['cycle_id'] == "cycle-0"

        finally:
            shutil.rmtree(temp_dir)


class TestSuppressionSummary:
    def test_get_suppression_summary_with_recent_events(self):
        """Test that get_suppression_summary returns correct aggregates"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            cycles = [
                ("BTC->ETH->USDT", "latency_exceeded", 5),
                ("ETH->USDT->BTC", "slippage_exceeded", 3),
                ("USDT->BTC->ETH", "latency_exceeded", 2)
            ]

            for cycle_id, reason, dup_count in cycles:
                for i in range(dup_count + 1):
                    violation = RiskControlViolation(
                        timestamp=time.time(),
                        cycle_id=cycle_id,
                        strategy_name="test_strategy",
                        violation_type=reason,
                        cycle_path=cycle_id.split("->"),
                        cycle_direction="forward",
                        expected_prices=[1.0, 1.0, 1.0],
                        actual_prices=[1.0, 1.0, 1.0],
                        latencies_ms=[150, 100, 100],
                        slippages_bps=[0, 0, 0],
                        threshold_violated={},
                        leg_details=[],
                        metadata={}
                    )
                    manager.logger.log_violation(violation, is_executed=False)
                    time.sleep(0.01)

            summary = manager.logger.get_suppression_summary(window_seconds=60)

            assert summary['total_suppressed'] == 10
            assert summary['unique_pairs'] == 3
            assert summary['suppression_rate'] > 0
            assert len(summary['top_pairs']) == 3
            assert summary['top_pairs'][0]['cycle_id'] == "BTC->ETH->USDT"
            assert summary['top_pairs'][0]['count'] == 5

        finally:
            shutil.rmtree(temp_dir)

    def test_get_suppression_summary_window_filtering(self):
        """Test that summary excludes events outside window"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            old_time = time.time() - 400
            manager.logger._suppressed_history.append({
                'cycle_id': 'OLD->CYCLE',
                'stop_reason': 'latency_exceeded',
                'first_seen': old_time,
                'last_seen': old_time,
                'duplicate_count': 10
            })

            for i in range(3):
                violation = RiskControlViolation(
                    timestamp=time.time(),
                    cycle_id="NEW->CYCLE",
                    strategy_name="test_strategy",
                    violation_type="latency_exceeded",
                    cycle_path=["NEW", "CYCLE"],
                    cycle_direction="forward",
                    expected_prices=[1.0, 1.0],
                    actual_prices=[1.0, 1.0],
                    latencies_ms=[150, 100],
                    slippages_bps=[0, 0],
                    threshold_violated={},
                    leg_details=[],
                    metadata={}
                )
                manager.logger.log_violation(violation, is_executed=False)
                time.sleep(0.01)

            summary = manager.logger.get_suppression_summary(window_seconds=300)

            assert summary['total_suppressed'] == 2
            assert summary['unique_pairs'] == 1
            assert summary['top_pairs'][0]['cycle_id'] == "NEW->CYCLE"

        finally:
            shutil.rmtree(temp_dir)

    def test_get_suppression_summary_empty(self):
        """Test summary when no events in window"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            summary = manager.logger.get_suppression_summary(window_seconds=300)

            assert summary['total_suppressed'] == 0
            assert summary['unique_pairs'] == 0
            assert summary['suppression_rate'] == 0.0
            assert summary['top_pairs'] == []

        finally:
            shutil.rmtree(temp_dir)

    def test_get_suppression_summary_top_pairs_sorted(self):
        """Test that top pairs are sorted by count descending"""
        temp_dir = tempfile.mkdtemp()

        try:
            manager = RiskControlManager(
                max_leg_latency_ms=100,
                max_slippage_bps=50,
                slippage_cooldown_seconds=300,
                duplicate_suppression_window=2.0,
                log_dir=temp_dir
            )

            cycles = [
                ("CYCLE-A", 2),
                ("CYCLE-B", 5),
                ("CYCLE-C", 3),
                ("CYCLE-D", 1),
                ("CYCLE-E", 4)
            ]

            for cycle_id, dup_count in cycles:
                for i in range(dup_count + 1):
                    violation = RiskControlViolation(
                        timestamp=time.time(),
                        cycle_id=cycle_id,
                        strategy_name="test_strategy",
                        violation_type="latency_exceeded",
                        cycle_path=[cycle_id],
                        cycle_direction="forward",
                        expected_prices=[1.0],
                        actual_prices=[1.0],
                        latencies_ms=[150],
                        slippages_bps=[0],
                        threshold_violated={},
                        leg_details=[],
                        metadata={}
                    )
                    manager.logger.log_violation(violation, is_executed=False)
                    time.sleep(0.01)

            summary = manager.logger.get_suppression_summary(window_seconds=60)

            assert len(summary['top_pairs']) == 3
            assert summary['top_pairs'][0]['cycle_id'] == "CYCLE-B"
            assert summary['top_pairs'][0]['count'] == 5
            assert summary['top_pairs'][1]['cycle_id'] == "CYCLE-E"
            assert summary['top_pairs'][1]['count'] == 4
            assert summary['top_pairs'][2]['cycle_id'] == "CYCLE-C"
            assert summary['top_pairs'][2]['count'] == 3

        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])