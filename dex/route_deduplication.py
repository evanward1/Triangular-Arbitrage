"""
Route deduplication and cooldown management for DEX arbitrage.

Prevents repeated execution of the same opportunity by:
1. Fingerprinting routes based on path, block, and prices
2. Tracking last execution per route with cooldown
3. Enforcing hysteresis to prevent rapid re-triggering
"""

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class RouteExecution:
    """Record of a route execution."""

    block_number: int
    net_pct: float
    exec_ts: float
    fingerprint: str


class RouteDeduplicator:
    """
    Manages route fingerprints and execution cooldowns.

    Prevents the same opportunity from being executed multiple times
    within a cooldown window.
    """

    def __init__(
        self,
        route_cooldown_sec: float = 60.0,
        hysteresis_addl_net_pct: float = 0.05,
        fingerprint_ttl_sec: float = 60.0,
    ):
        """
        Initialize deduplicator.

        Args:
            route_cooldown_sec: Minimum seconds between executions of same route
            hysteresis_addl_net_pct: Additional net % required to re-trigger
            fingerprint_ttl_sec: How long to remember fingerprints
        """
        self.route_cooldown_sec = route_cooldown_sec
        self.hysteresis_addl_net_pct = hysteresis_addl_net_pct
        self.fingerprint_ttl_sec = fingerprint_ttl_sec

        # Track seen fingerprints with timestamp
        self.seen_fingerprints: Dict[str, float] = {}

        # Track last execution by route_id
        self.last_executed: Dict[str, RouteExecution] = {}

    def create_route_id(self, path: List[str], pool_addresses: List[str]) -> str:
        """
        Create stable route ID from path and pool addresses.

        Args:
            path: Token path (e.g., ["USDC", "WETH", "DAI"])
            pool_addresses: Pool contract addresses for each leg

        Returns:
            Stable route ID string
        """
        # Sort path to normalize different starting points of same cycle
        sorted_path = tuple(sorted(path))
        # Sort pool addresses to normalize
        sorted_pools = tuple(sorted(pool_addresses))
        return f"{'-'.join(sorted_path)}:{'-'.join(sorted_pools)}"

    def create_fingerprint(
        self,
        route_id: str,
        block_number: int,
        gross_bps: float,
        fee_bps: float,
        gas_usd: float,
    ) -> str:
        """
        Create fingerprint from route and current state.

        Args:
            route_id: Stable route identifier
            block_number: Current block number
            gross_bps: Gross profit in basis points
            fee_bps: Fee in basis points
            gas_usd: Gas cost in USD

        Returns:
            SHA1 fingerprint hex string
        """
        # Create stable string representation
        data = f"{route_id}:{block_number}:{gross_bps:.6f}:{fee_bps:.6f}:{gas_usd:.6f}"
        return hashlib.sha1(data.encode()).hexdigest()[:16]

    def cleanup_expired(self, now: float):
        """
        Remove expired fingerprints from tracking.

        Args:
            now: Current timestamp
        """
        # Clean fingerprints older than TTL
        expired = [
            fp
            for fp, ts in self.seen_fingerprints.items()
            if now - ts > self.fingerprint_ttl_sec
        ]
        for fp in expired:
            del self.seen_fingerprints[fp]

    def should_execute(
        self,
        route_id: str,
        fingerprint: str,
        block_number: int,
        net_pct: float,
        now: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if opportunity should be executed.

        Args:
            route_id: Route identifier
            fingerprint: Current fingerprint
            block_number: Current block number
            net_pct: Net profit percentage
            now: Current timestamp

        Returns:
            (should_execute, skip_reason) tuple
        """
        # Clean expired entries
        self.cleanup_expired(now)

        # Check if fingerprint already seen
        if fingerprint in self.seen_fingerprints:
            time_since = now - self.seen_fingerprints[fingerprint]
            return False, f"Repeated fingerprint (seen {time_since:.1f}s ago)"

        # Check if route executed recently
        if route_id in self.last_executed:
            last_exec = self.last_executed[route_id]

            # Same block check
            if last_exec.block_number == block_number:
                return False, f"Already executed in block {block_number}"

            # Cooldown check
            time_since_exec = now - last_exec.exec_ts
            if time_since_exec < self.route_cooldown_sec:
                remaining = self.route_cooldown_sec - time_since_exec
                return (
                    False,
                    f"Route cooldown ({remaining:.1f}s remaining)",
                )

            # Hysteresis check
            required_net = last_exec.net_pct + self.hysteresis_addl_net_pct
            if net_pct < required_net:
                return (
                    False,
                    f"Hysteresis: need {required_net:.3f}%, got {net_pct:.3f}%",
                )

        # All checks passed
        return True, None

    def record_execution(
        self,
        route_id: str,
        fingerprint: str,
        block_number: int,
        net_pct: float,
        now: float,
    ):
        """
        Record successful execution.

        Args:
            route_id: Route identifier
            fingerprint: Fingerprint that was executed
            block_number: Current block number
            net_pct: Net profit percentage
            now: Current timestamp
        """
        # Record fingerprint
        self.seen_fingerprints[fingerprint] = now

        # Record execution
        self.last_executed[route_id] = RouteExecution(
            block_number=block_number,
            net_pct=net_pct,
            exec_ts=now,
            fingerprint=fingerprint,
        )

    def get_stats(self) -> Dict[str, int]:
        """Get current statistics."""
        return {
            "tracked_fingerprints": len(self.seen_fingerprints),
            "tracked_routes": len(self.last_executed),
        }
