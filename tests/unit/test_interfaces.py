"""Tests for dependency injection interfaces."""

import time
import pytest
from triangular_arbitrage.interfaces import (
    TimeProvider,
    RandomProvider,
    SystemTimeProvider,
    SystemRandomProvider,
    DeterministicTimeProvider,
    DeterministicRandomProvider,
    get_time_provider,
    get_random_provider,
    set_time_provider,
    set_random_provider,
    current_timestamp,
    sleep,
    random_float,
    random_int,
    uniform,
)


def test_system_time_provider():
    """Test SystemTimeProvider."""
    provider = SystemTimeProvider()

    # Test current_timestamp
    ts1 = provider.current_timestamp()
    time.sleep(0.01)  # Small delay
    ts2 = provider.current_timestamp()
    assert ts2 > ts1

    # Test current_time_ms
    ms = provider.current_time_ms()
    assert isinstance(ms, int)
    assert ms > 0

    # Test sleep (hard to test without actually sleeping)
    start = provider.current_timestamp()
    provider.sleep(0.01)
    end = provider.current_timestamp()
    assert end >= start + 0.01


def test_system_random_provider():
    """Test SystemRandomProvider."""
    provider = SystemRandomProvider(seed=42)

    # Test random
    r1 = provider.random()
    assert 0.0 <= r1 < 1.0

    # Test randint
    ri = provider.randint(1, 10)
    assert 1 <= ri <= 10

    # Test uniform
    ru = provider.uniform(5.0, 10.0)
    assert 5.0 <= ru <= 10.0

    # Test seeding for reproducibility
    provider.seed(42)
    r2 = provider.random()
    provider.seed(42)
    r3 = provider.random()
    assert r2 == r3


def test_deterministic_time_provider():
    """Test DeterministicTimeProvider."""
    start_time = 1000.0
    provider = DeterministicTimeProvider(start_time)

    # Test initial time
    assert provider.current_timestamp() == start_time

    # Test advance_time
    provider.advance_time(10.0)
    assert provider.current_timestamp() == start_time + 10.0

    # Test set_time
    new_time = 2000.0
    provider.set_time(new_time)
    assert provider.current_timestamp() == new_time

    # Test sleep (should advance time instead of sleeping)
    provider.sleep(5.0)
    assert provider.current_timestamp() == new_time + 5.0

    # Test current_time_ms
    ms = provider.current_time_ms()
    assert ms == int((new_time + 5.0) * 1000)


def test_deterministic_random_provider():
    """Test DeterministicRandomProvider."""
    provider = DeterministicRandomProvider(seed=42)

    # Test reproducibility
    r1 = provider.random()
    ri1 = provider.randint(1, 10)
    ru1 = provider.uniform(5.0, 10.0)

    provider.seed(42)
    r2 = provider.random()
    ri2 = provider.randint(1, 10)
    ru2 = provider.uniform(5.0, 10.0)

    assert r1 == r2
    assert ri1 == ri2
    assert ru1 == ru2

    # Test ranges
    assert 0.0 <= r1 < 1.0
    assert 1 <= ri1 <= 10
    assert 5.0 <= ru1 <= 10.0


def test_provider_protocols():
    """Test that providers implement the protocols correctly."""
    time_provider = SystemTimeProvider()
    random_provider = SystemRandomProvider()
    det_time_provider = DeterministicTimeProvider()
    det_random_provider = DeterministicRandomProvider()

    # Test protocol compliance
    assert isinstance(time_provider, TimeProvider)
    assert isinstance(random_provider, RandomProvider)
    assert isinstance(det_time_provider, TimeProvider)
    assert isinstance(det_random_provider, RandomProvider)


def test_global_provider_management():
    """Test global provider getter/setter functions."""
    # Store original providers
    original_time = get_time_provider()
    original_random = get_random_provider()

    try:
        # Test setting custom providers
        custom_time = DeterministicTimeProvider(5000.0)
        custom_random = DeterministicRandomProvider(seed=123)

        set_time_provider(custom_time)
        set_random_provider(custom_random)

        assert get_time_provider() is custom_time
        assert get_random_provider() is custom_random

        # Test that convenience functions use the set providers
        assert current_timestamp() == 5000.0

        custom_time.advance_time(100.0)
        assert current_timestamp() == 5100.0

        # Test random convenience functions
        custom_random.seed(123)
        r1 = random_float()
        custom_random.seed(123)
        r2 = random_float()
        assert r1 == r2

        ri = random_int(1, 5)
        assert 1 <= ri <= 5

        ru = uniform(2.0, 8.0)
        assert 2.0 <= ru <= 8.0

    finally:
        # Restore original providers
        set_time_provider(original_time)
        set_random_provider(original_random)


def test_convenience_functions():
    """Test convenience functions with default providers."""
    # Test current_timestamp
    ts = current_timestamp()
    assert isinstance(ts, float)
    assert ts > 0

    # Test random functions
    rf = random_float()
    assert 0.0 <= rf < 1.0

    ri = random_int(1, 100)
    assert 1 <= ri <= 100

    ru = uniform(10.0, 20.0)
    assert 10.0 <= ru <= 20.0


def test_sleep_with_deterministic_provider():
    """Test that sleep works correctly with deterministic provider."""
    det_time = DeterministicTimeProvider(1000.0)
    original_time = get_time_provider()

    try:
        set_time_provider(det_time)

        # Sleep should advance time, not actually sleep
        start_time = time.time()
        sleep(1.0)  # Should advance deterministic time, not real time
        end_time = time.time()

        # Real time should be nearly the same (very fast execution)
        assert end_time - start_time < 0.1

        # Deterministic time should have advanced
        assert current_timestamp() == 1001.0

    finally:
        set_time_provider(original_time)