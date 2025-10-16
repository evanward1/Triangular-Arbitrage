"""
Slippage monitoring for detecting chronic high-slippage trading pairs.
"""

from collections import defaultdict, deque
from typing import Dict


class SlippageMonitor:
    """
    Monitors per-symbol slippage over a rolling window to detect chronic offenders.
    Tracks median slippage and identifies pairs that consistently exceed caps.
    """

    def __init__(self, window: int = 20):
        """
        Initialize slippage monitor.

        Args:
            window: Number of samples to track per symbol (default 20)
        """
        self.window = window
        self.data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window))

    def record(self, symbol: str, slippage_pct: float):
        """
        Record a slippage observation for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BONK/USD")
            slippage_pct: Observed slippage percentage (e.g., 1.23 for 1.23%)
        """
        self.data[symbol].append(slippage_pct)

    def median(self, symbol: str) -> float:
        """
        Calculate median slippage for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Median slippage percentage, or 0.0 if no data
        """
        if symbol not in self.data or not self.data[symbol]:
            return 0.0

        sorted_data = sorted(self.data[symbol])
        n = len(sorted_data)
        if n % 2 == 1:
            return sorted_data[n // 2]
        else:
            return 0.5 * (sorted_data[n // 2 - 1] + sorted_data[n // 2])

    def is_chronic(self, symbol: str, cap: float) -> bool:
        """
        Check if a symbol is a chronic slippage offender.

        Args:
            symbol: Trading pair symbol
            cap: Slippage cap percentage to compare against

        Returns:
            True if median slippage exceeds cap, False otherwise
        """
        # Need at least half the window filled to make a determination
        if symbol not in self.data or len(self.data[symbol]) < self.window // 2:
            return False

        return self.median(symbol) > cap

    def get_stats(self, symbol: str) -> Dict[str, float]:
        """
        Get statistics for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary with 'median', 'count', 'min', 'max' keys
        """
        if symbol not in self.data or not self.data[symbol]:
            return {"median": 0.0, "count": 0, "min": 0.0, "max": 0.0}

        data_list = list(self.data[symbol])
        return {
            "median": self.median(symbol),
            "count": len(data_list),
            "min": min(data_list),
            "max": max(data_list),
        }
