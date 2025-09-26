import time
import logging
import json
import os
import tempfile
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class LatencyMeasurement:
    leg_index: int
    market_symbol: str
    start_time: float
    end_time: float
    latency_ms: float
    side: str


@dataclass
class SlippageMeasurement:
    leg_index: int
    market_symbol: str
    expected_price: float
    executed_price: float
    slippage_bps: float
    side: str


@dataclass
class RiskControlViolation:
    timestamp: float
    cycle_id: str
    strategy_name: str
    violation_type: str
    cycle_path: List[str]
    cycle_direction: str
    expected_prices: List[float]
    actual_prices: List[float]
    latencies_ms: List[float]
    slippages_bps: List[float]
    threshold_violated: Dict[str, Any]
    leg_details: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class LatencyMonitor:
    def __init__(self, max_leg_latency_ms: float):
        self.max_leg_latency_ms = max_leg_latency_ms
        self.measurements: List[LatencyMeasurement] = []

    def start_measurement(self) -> float:
        return time.time()

    def end_measurement(
        self,
        leg_index: int,
        market_symbol: str,
        start_time: float,
        side: str
    ) -> LatencyMeasurement:
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000

        measurement = LatencyMeasurement(
            leg_index=leg_index,
            market_symbol=market_symbol,
            start_time=start_time,
            end_time=end_time,
            latency_ms=latency_ms,
            side=side
        )

        self.measurements.append(measurement)
        return measurement

    def check_violation(self, measurement: LatencyMeasurement) -> bool:
        return measurement.latency_ms > self.max_leg_latency_ms

    def get_all_measurements(self) -> List[LatencyMeasurement]:
        return self.measurements

    def reset(self):
        self.measurements.clear()


class SlippageTracker:
    def __init__(self, max_slippage_bps: float, cooldown_seconds: float = 300):
        self.max_slippage_bps = max_slippage_bps
        self.cooldown_seconds = cooldown_seconds
        self.measurements: List[SlippageMeasurement] = []
        self.cooldown_cycles: Dict[str, float] = {}

    def calculate_slippage(
        self,
        leg_index: int,
        market_symbol: str,
        expected_price: float,
        executed_price: float,
        side: str
    ) -> SlippageMeasurement:
        if side == 'buy':
            slippage_bps = ((executed_price - expected_price) / expected_price) * 10000
        else:
            slippage_bps = ((expected_price - executed_price) / expected_price) * 10000

        measurement = SlippageMeasurement(
            leg_index=leg_index,
            market_symbol=market_symbol,
            expected_price=expected_price,
            executed_price=executed_price,
            slippage_bps=slippage_bps,
            side=side
        )

        self.measurements.append(measurement)
        return measurement

    def check_violation(self, measurement: SlippageMeasurement) -> bool:
        return abs(measurement.slippage_bps) > self.max_slippage_bps

    def add_to_cooldown(self, cycle_key: str):
        self.cooldown_cycles[cycle_key] = time.time()
        logger.info(f"Added cycle {cycle_key} to cooldown for {self.cooldown_seconds}s")

    def is_in_cooldown(self, cycle_key: str) -> bool:
        if cycle_key not in self.cooldown_cycles:
            return False

        elapsed = time.time() - self.cooldown_cycles[cycle_key]
        if elapsed >= self.cooldown_seconds:
            del self.cooldown_cycles[cycle_key]
            return False

        return True

    def get_cooldown_remaining(self, cycle_key: str) -> float:
        if cycle_key not in self.cooldown_cycles:
            return 0.0

        elapsed = time.time() - self.cooldown_cycles[cycle_key]
        remaining = max(0.0, self.cooldown_seconds - elapsed)
        return remaining

    def cleanup_expired_cooldowns(self):
        current_time = time.time()
        expired = [
            k for k, v in self.cooldown_cycles.items()
            if current_time - v >= self.cooldown_seconds
        ]
        for k in expired:
            del self.cooldown_cycles[k]
        return len(expired)

    def get_all_measurements(self) -> List[SlippageMeasurement]:
        return self.measurements

    def reset(self):
        self.measurements.clear()


class RiskControlLogger:
    def __init__(self, log_dir: str = "logs/risk_controls", suppression_window: float = 2.0):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.json_log_file = self.log_dir / "risk_violations.jsonl"
        self.console_logger = logging.getLogger("risk_controls")

        self.suppression_window = suppression_window
        self._duplicate_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        self._total_duplicates_suppressed = 0
        self._suppressed_history: List[Dict[str, Any]] = []
        self._max_history_size = 100

    def _is_duplicate_event(self, cycle_id: str, stop_reason: str, timestamp: float) -> bool:
        if self.suppression_window <= 0:
            return False

        with self._cache_lock:
            key = (cycle_id, stop_reason)

            if key in self._duplicate_cache:
                cached = self._duplicate_cache[key]
                elapsed = timestamp - cached['last_timestamp']

                if elapsed <= self.suppression_window:
                    cached['duplicate_count'] += 1
                    cached['last_timestamp'] = timestamp
                    self._total_duplicates_suppressed += 1

                    self._update_suppressed_history(cycle_id, stop_reason, cached)
                    return True
                else:
                    cached['last_timestamp'] = timestamp
                    cached['duplicate_count'] = 0
                    cached['first_timestamp'] = timestamp
                    return False
            else:
                self._duplicate_cache[key] = {
                    'first_timestamp': timestamp,
                    'last_timestamp': timestamp,
                    'duplicate_count': 0
                }
                return False

    def log_violation(self, violation: RiskControlViolation, is_executed: bool = False):
        if not is_executed:
            stop_reason = violation.violation_type
            if self._is_duplicate_event(violation.cycle_id, stop_reason, violation.timestamp):
                return

        log_entry = asdict(violation)
        log_entry['timestamp_readable'] = datetime.fromtimestamp(
            violation.timestamp
        ).isoformat()

        with open(self.json_log_file, 'a') as f:
            json.dump(log_entry, f)
            f.write('\n')

        self._log_to_console(violation)

    def _log_to_console(self, violation: RiskControlViolation):
        self.console_logger.warning("=" * 80)
        self.console_logger.warning(f"RISK CONTROL VIOLATION: {violation.violation_type}")
        self.console_logger.warning("=" * 80)
        self.console_logger.warning(f"Cycle ID: {violation.cycle_id}")
        self.console_logger.warning(f"Strategy: {violation.strategy_name}")
        self.console_logger.warning(f"Trading Pair: {' -> '.join(violation.cycle_path)}")
        self.console_logger.warning(f"Direction: {violation.cycle_direction}")
        self.console_logger.warning(f"Threshold Violated: {violation.threshold_violated}")

        if violation.violation_type == "LATENCY_EXCEEDED":
            self.console_logger.warning("\nLatency Details (ms):")
            for i, (latency, leg) in enumerate(zip(violation.latencies_ms, violation.leg_details)):
                status = "VIOLATED" if latency > violation.threshold_violated['max_leg_latency_ms'] else "OK"
                self.console_logger.warning(
                    f"  Leg {i+1} ({leg['market']} {leg['side']}): {latency:.2f}ms [{status}]"
                )

        elif violation.violation_type == "SLIPPAGE_EXCEEDED":
            self.console_logger.warning("\nSlippage Details:")
            for i, (slippage, expected, actual, leg) in enumerate(zip(
                violation.slippages_bps,
                violation.expected_prices,
                violation.actual_prices,
                violation.leg_details
            )):
                status = "VIOLATED" if abs(slippage) > violation.threshold_violated['max_slippage_bps'] else "OK"
                self.console_logger.warning(
                    f"  Leg {i+1} ({leg['market']} {leg['side']}): "
                    f"Expected: {expected:.8f}, Actual: {actual:.8f}, "
                    f"Slippage: {slippage:.2f} bps [{status}]"
                )

        self.console_logger.warning("=" * 80)

    def _update_suppressed_history(self, cycle_id: str, stop_reason: str, cached: Dict[str, Any]):
        record = {
            'cycle_id': cycle_id,
            'stop_reason': stop_reason,
            'first_seen': cached.get('first_timestamp', cached['last_timestamp']),
            'last_seen': cached['last_timestamp'],
            'duplicate_count': cached['duplicate_count']
        }

        existing_idx = None
        for i, rec in enumerate(self._suppressed_history):
            if rec['cycle_id'] == cycle_id and rec['stop_reason'] == stop_reason:
                existing_idx = i
                break

        if existing_idx is not None:
            self._suppressed_history[existing_idx] = record
        else:
            self._suppressed_history.append(record)

        if len(self._suppressed_history) > self._max_history_size:
            self._suppressed_history.pop(0)

    def get_recent_suppressed(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._cache_lock:
            sorted_history = sorted(
                self._suppressed_history,
                key=lambda x: x['last_seen'],
                reverse=True
            )
            return sorted_history[:limit]

    def get_suppression_summary(self, window_seconds: int = 300) -> Dict[str, Any]:
        with self._cache_lock:
            current_time = time.time()
            cutoff_time = current_time - window_seconds

            recent_events = [
                event for event in self._suppressed_history
                if event['last_seen'] >= cutoff_time
            ]

            if not recent_events:
                return {
                    'total_suppressed': 0,
                    'unique_pairs': 0,
                    'top_pairs': [],
                    'suppression_rate': 0.0,
                    'window_seconds': window_seconds
                }

            total_suppressed = sum(event['duplicate_count'] for event in recent_events)
            unique_pairs = len(recent_events)

            unique_events = len(recent_events)
            total_events = total_suppressed + unique_events
            suppression_rate = (total_suppressed / total_events * 100) if total_events > 0 else 0.0

            sorted_events = sorted(
                recent_events,
                key=lambda x: x['duplicate_count'],
                reverse=True
            )
            top_pairs = [
                {
                    'cycle_id': event['cycle_id'],
                    'stop_reason': event['stop_reason'],
                    'count': event['duplicate_count']
                }
                for event in sorted_events[:3]
            ]

            return {
                'total_suppressed': total_suppressed,
                'unique_pairs': unique_pairs,
                'top_pairs': top_pairs,
                'suppression_rate': round(suppression_rate, 2),
                'window_seconds': window_seconds
            }

    def get_suppression_stats(self) -> Dict[str, Any]:
        with self._cache_lock:
            return {
                'total_duplicates_suppressed': self._total_duplicates_suppressed,
                'cache_size': len(self._duplicate_cache),
                'suppression_window_seconds': self.suppression_window
            }

    def get_violation_stats(self, time_window_seconds: Optional[int] = None) -> Dict[str, Any]:
        if not self.json_log_file.exists():
            return {
                'total_violations': 0,
                'by_type': {},
                'by_strategy': {},
                'by_cycle': {}
            }

        violations = []
        current_time = time.time()

        with open(self.json_log_file, 'r') as f:
            for line in f:
                try:
                    violation = json.loads(line)
                    if time_window_seconds is None or \
                       (current_time - violation['timestamp']) <= time_window_seconds:
                        violations.append(violation)
                except json.JSONDecodeError:
                    continue

        stats = {
            'total_violations': len(violations),
            'by_type': defaultdict(int),
            'by_strategy': defaultdict(int),
            'by_cycle': defaultdict(int)
        }

        for v in violations:
            stats['by_type'][v['violation_type']] += 1
            stats['by_strategy'][v['strategy_name']] += 1
            cycle_key = '->'.join(v['cycle_path'])
            stats['by_cycle'][cycle_key] += 1

        stats['by_type'] = dict(stats['by_type'])
        stats['by_strategy'] = dict(stats['by_strategy'])
        stats['by_cycle'] = dict(stats['by_cycle'])

        return stats


class RiskControlManager:
    def __init__(
        self,
        max_leg_latency_ms: float,
        max_slippage_bps: float,
        slippage_cooldown_seconds: float = 300,
        log_dir: str = "logs/risk_controls",
        duplicate_suppression_window: float = 2.0
    ):
        self.latency_monitor = LatencyMonitor(max_leg_latency_ms)
        self.slippage_tracker = SlippageTracker(max_slippage_bps, slippage_cooldown_seconds)
        self.logger = RiskControlLogger(log_dir, duplicate_suppression_window)
        self.max_leg_latency_ms = max_leg_latency_ms
        self.max_slippage_bps = max_slippage_bps
        self.log_dir = log_dir
        self.default_state_path = f"{log_dir}/cooldowns_state.json"

    def start_leg_timing(self) -> float:
        return self.latency_monitor.start_measurement()

    def end_leg_timing(
        self,
        leg_index: int,
        market_symbol: str,
        start_time: float,
        side: str
    ) -> Tuple[LatencyMeasurement, bool]:
        measurement = self.latency_monitor.end_measurement(
            leg_index, market_symbol, start_time, side
        )
        violated = self.latency_monitor.check_violation(measurement)
        return measurement, violated

    def track_slippage(
        self,
        leg_index: int,
        market_symbol: str,
        expected_price: float,
        executed_price: float,
        side: str
    ) -> Tuple[SlippageMeasurement, bool]:
        measurement = self.slippage_tracker.calculate_slippage(
            leg_index, market_symbol, expected_price, executed_price, side
        )
        violated = self.slippage_tracker.check_violation(measurement)
        return measurement, violated

    def is_cycle_in_cooldown(self, cycle_path: List[str]) -> bool:
        cycle_key = "->".join(cycle_path)
        return self.slippage_tracker.is_in_cooldown(cycle_key)

    def get_cycle_cooldown_remaining(self, cycle_path: List[str]) -> float:
        cycle_key = "->".join(cycle_path)
        return self.slippage_tracker.get_cooldown_remaining(cycle_key)

    def log_latency_violation(
        self,
        cycle_id: str,
        strategy_name: str,
        cycle_path: List[str],
        cycle_direction: str,
        violated_leg: LatencyMeasurement,
        all_measurements: Optional[List[LatencyMeasurement]] = None
    ):
        if all_measurements is None:
            all_measurements = [violated_leg]

        violation = RiskControlViolation(
            timestamp=time.time(),
            cycle_id=cycle_id,
            strategy_name=strategy_name,
            violation_type="LATENCY_EXCEEDED",
            cycle_path=cycle_path,
            cycle_direction=cycle_direction,
            expected_prices=[],
            actual_prices=[],
            latencies_ms=[m.latency_ms for m in all_measurements],
            slippages_bps=[],
            threshold_violated={
                'max_leg_latency_ms': self.max_leg_latency_ms,
                'violated_leg': violated_leg.leg_index,
                'violated_latency_ms': violated_leg.latency_ms
            },
            leg_details=[{
                'leg_index': m.leg_index,
                'market': m.market_symbol,
                'side': m.side,
                'latency_ms': m.latency_ms
            } for m in all_measurements],
            metadata={}
        )

        self.logger.log_violation(violation)

    def log_slippage_violation(
        self,
        cycle_id: str,
        strategy_name: str,
        cycle_path: List[str],
        cycle_direction: str,
        violated_leg: SlippageMeasurement,
        all_measurements: Optional[List[SlippageMeasurement]] = None
    ):
        if all_measurements is None:
            all_measurements = [violated_leg]

        cycle_key = "->".join(cycle_path)
        self.slippage_tracker.add_to_cooldown(cycle_key)

        violation = RiskControlViolation(
            timestamp=time.time(),
            cycle_id=cycle_id,
            strategy_name=strategy_name,
            violation_type="SLIPPAGE_EXCEEDED",
            cycle_path=cycle_path,
            cycle_direction=cycle_direction,
            expected_prices=[m.expected_price for m in all_measurements],
            actual_prices=[m.executed_price for m in all_measurements],
            latencies_ms=[],
            slippages_bps=[m.slippage_bps for m in all_measurements],
            threshold_violated={
                'max_slippage_bps': self.max_slippage_bps,
                'violated_leg': violated_leg.leg_index,
                'violated_slippage_bps': violated_leg.slippage_bps,
                'cooldown_seconds': self.slippage_tracker.cooldown_seconds
            },
            leg_details=[{
                'leg_index': m.leg_index,
                'market': m.market_symbol,
                'side': m.side,
                'expected_price': m.expected_price,
                'executed_price': m.executed_price,
                'slippage_bps': m.slippage_bps
            } for m in all_measurements],
            metadata={}
        )

        self.logger.log_violation(violation)

    def reset_cycle_measurements(self):
        self.latency_monitor.reset()
        self.slippage_tracker.reset()

    def cleanup_expired_cooldowns(self) -> int:
        return self.slippage_tracker.cleanup_expired_cooldowns()

    def get_stats(self, time_window_seconds: Optional[int] = None) -> Dict[str, Any]:
        violation_stats = self.logger.get_violation_stats(time_window_seconds)
        suppression_stats = self.logger.get_suppression_stats()

        return {
            'violations': violation_stats,
            'active_cooldowns': len(self.slippage_tracker.cooldown_cycles),
            'suppression': suppression_stats,
            'config': {
                'max_leg_latency_ms': self.max_leg_latency_ms,
                'max_slippage_bps': self.max_slippage_bps,
                'cooldown_seconds': self.slippage_tracker.cooldown_seconds
            }
        }

    def save_cooldowns(self, path: Optional[str] = None):
        if path is None:
            path = self.default_state_path
        cooldown_data = {}
        current_time = time.time()

        for cycle_key, start_time in self.slippage_tracker.cooldown_cycles.items():
            cooldown_end = start_time + self.slippage_tracker.cooldown_seconds
            if cooldown_end > current_time:
                cooldown_data[cycle_key] = cooldown_end

        state_path = Path(path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(
            dir=state_path.parent,
            prefix='.cooldowns_',
            suffix='.tmp'
        )

        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(cooldown_data, f, indent=2)

            os.replace(temp_path, state_path)
            logger.info(f"Saved {len(cooldown_data)} active cooldowns to {path}")

        except Exception as e:
            try:
                os.unlink(temp_path)
            except:
                pass
            logger.error(f"Failed to save cooldowns: {e}")
            raise

    def load_cooldowns(self, path: Optional[str] = None) -> int:
        if path is None:
            path = self.default_state_path
        state_path = Path(path)

        if not state_path.exists():
            logger.info(f"No cooldown state file found at {path}")
            return 0

        try:
            with open(state_path, 'r') as f:
                cooldown_data = json.load(f)

            current_time = time.time()
            restored_count = 0
            expired_count = 0

            for cycle_key, cooldown_end in cooldown_data.items():
                if cooldown_end > current_time:
                    cooldown_start = cooldown_end - self.slippage_tracker.cooldown_seconds
                    self.slippage_tracker.cooldown_cycles[cycle_key] = cooldown_start
                    restored_count += 1
                else:
                    expired_count += 1

            logger.info(
                f"Loaded {restored_count} active cooldowns from {path} "
                f"({expired_count} already expired)"
            )
            return restored_count

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse cooldown state file: {e}")
            return 0
        except Exception as e:
            logger.error(f"Failed to load cooldowns: {e}")
            return 0

    def get_active_cooldowns(self) -> List[Tuple[str, float]]:
        current_time = time.time()
        active = []

        for cycle_key, start_time in self.slippage_tracker.cooldown_cycles.items():
            remaining = (start_time + self.slippage_tracker.cooldown_seconds) - current_time
            if remaining > 0:
                active.append((cycle_key, remaining))

        return sorted(active, key=lambda x: x[1], reverse=True)

    def clear_cooldown(self, pair: str) -> bool:
        if pair in self.slippage_tracker.cooldown_cycles:
            del self.slippage_tracker.cooldown_cycles[pair]
            self.save_cooldowns()
            logger.info(f"Cleared cooldown for {pair}")
            return True
        return False

    def get_cooldown_end(self, pair: str) -> Optional[float]:
        if pair in self.slippage_tracker.cooldown_cycles:
            start_time = self.slippage_tracker.cooldown_cycles[pair]
            return start_time + self.slippage_tracker.cooldown_seconds
        return None

    def extend_cooldown(self, pair: str, seconds: int) -> bool:
        if pair not in self.slippage_tracker.cooldown_cycles:
            return False

        current_start = self.slippage_tracker.cooldown_cycles[pair]
        current_end = current_start + self.slippage_tracker.cooldown_seconds
        new_end = current_end + seconds

        min_end = time.time() + 1.0
        clamped_end = max(new_end, min_end)

        new_start = clamped_end - self.slippage_tracker.cooldown_seconds
        self.slippage_tracker.cooldown_cycles[pair] = new_start

        self.save_cooldowns()
        logger.info(f"Extended cooldown for {pair} by {seconds}s (clamped end: {clamped_end})")
        return True

    def clear_all_cooldowns(self) -> int:
        count = len(self.slippage_tracker.cooldown_cycles)
        self.slippage_tracker.cooldown_cycles.clear()
        self.save_cooldowns()
        logger.info(f"Cleared all cooldowns (count: {count}) at {datetime.now().isoformat()}")
        return count