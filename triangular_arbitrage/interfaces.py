"""
Dependency injection interfaces for improved testability and modularity.

Provides lightweight protocols and interfaces for time, random number generation,
and other system dependencies to reduce singletons and enable better testing.
"""

import random
import time
# ABC and abstractmethod removed - using Protocol instead
from typing import Protocol, runtime_checkable


@runtime_checkable
class TimeProvider(Protocol):
    """Protocol for time-related operations."""

    def current_timestamp(self) -> float:
        """Get current Unix timestamp."""
        ...

    def sleep(self, duration: float) -> None:
        """Sleep for specified duration in seconds."""
        ...

    def current_time_ms(self) -> int:
        """Get current time in milliseconds."""
        ...


@runtime_checkable
class RandomProvider(Protocol):
    """Protocol for random number generation."""

    def random(self) -> float:
        """Generate random float between 0.0 and 1.0."""
        ...

    def randint(self, a: int, b: int) -> int:
        """Generate random integer between a and b (inclusive)."""
        ...

    def uniform(self, a: float, b: float) -> float:
        """Generate random float between a and b."""
        ...

    def seed(self, seed_value: int) -> None:
        """Set random seed for reproducibility."""
        ...


class SystemTimeProvider:
    """Production time provider using system time."""

    def current_timestamp(self) -> float:
        """Get current Unix timestamp."""
        return time.time()

    def sleep(self, duration: float) -> None:
        """Sleep for specified duration in seconds."""
        time.sleep(duration)

    def current_time_ms(self) -> int:
        """Get current time in milliseconds."""
        return int(time.time() * 1000)


class SystemRandomProvider:
    """Production random provider using system random."""

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)

    def random(self) -> float:
        """Generate random float between 0.0 and 1.0."""
        return random.random()

    def randint(self, a: int, b: int) -> int:
        """Generate random integer between a and b (inclusive)."""
        return random.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        """Generate random float between a and b."""
        return random.uniform(a, b)

    def seed(self, seed_value: int) -> None:
        """Set random seed for reproducibility."""
        random.seed(seed_value)


class DeterministicTimeProvider:
    """Deterministic time provider for testing and backtesting."""

    def __init__(self, start_time: float = 1640995200.0):  # 2022-01-01
        self._current_time = start_time

    def current_timestamp(self) -> float:
        """Get current timestamp."""
        return self._current_time

    def sleep(self, duration: float) -> None:
        """Advance time by duration instead of actually sleeping."""
        self._current_time += duration

    def current_time_ms(self) -> int:
        """Get current time in milliseconds."""
        return int(self._current_time * 1000)

    def advance_time(self, seconds: float) -> None:
        """Manually advance time by specified seconds."""
        self._current_time += seconds

    def set_time(self, timestamp: float) -> None:
        """Set current time to specific timestamp."""
        self._current_time = timestamp


class DeterministicRandomProvider:
    """Deterministic random provider for testing and backtesting."""

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def random(self) -> float:
        """Generate random float between 0.0 and 1.0."""
        return self._rng.random()

    def randint(self, a: int, b: int) -> int:
        """Generate random integer between a and b (inclusive)."""
        return self._rng.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        """Generate random float between a and b."""
        return self._rng.uniform(a, b)

    def seed(self, seed_value: int) -> None:
        """Set random seed."""
        self._rng = random.Random(seed_value)


# Default providers - can be overridden for testing
_default_time_provider = SystemTimeProvider()
_default_random_provider = SystemRandomProvider()


def get_time_provider() -> TimeProvider:
    """Get the current time provider instance."""
    return _default_time_provider


def get_random_provider() -> RandomProvider:
    """Get the current random provider instance."""
    return _default_random_provider


def set_time_provider(provider: TimeProvider) -> None:
    """Set the global time provider (mainly for testing)."""
    global _default_time_provider
    _default_time_provider = provider


def set_random_provider(provider: RandomProvider) -> None:
    """Set the global random provider (mainly for testing)."""
    global _default_random_provider
    _default_random_provider = provider


# Convenience functions that delegate to current providers
def current_timestamp() -> float:
    """Get current timestamp using the configured time provider."""
    return get_time_provider().current_timestamp()


def sleep(duration: float) -> None:
    """Sleep using the configured time provider."""
    return get_time_provider().sleep(duration)


def random_float() -> float:
    """Get random float using the configured random provider."""
    return get_random_provider().random()


def random_int(a: int, b: int) -> int:
    """Get random integer using the configured random provider."""
    return get_random_provider().randint(a, b)


def uniform(a: float, b: float) -> float:
    """Get uniform random float using the configured random provider."""
    return get_random_provider().uniform(a, b)
