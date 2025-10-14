"""
Unit tests for dex/route_deduplication.py

Verifies that route fingerprinting, cooldown, and hysteresis work correctly.
"""

import time
import unittest

from dex.route_deduplication import RouteDeduplicator


class TestRouteDeduplicator(unittest.TestCase):
    """Test route deduplication and cooldown logic."""

    def setUp(self):
        """Create fresh deduplicator for each test."""
        self.dedup = RouteDeduplicator(
            route_cooldown_sec=60.0,
            hysteresis_addl_net_pct=0.05,
            fingerprint_ttl_sec=60.0,
        )

    def test_create_route_id(self):
        """Test that route IDs are stable and normalized."""
        path1 = ["USDC", "WETH", "DAI"]
        pools1 = ["0xABC", "0xDEF", "0xGHI"]

        path2 = ["DAI", "USDC", "WETH"]  # Different order, same triangle
        pools2 = ["0xGHI", "0xABC", "0xDEF"]  # Different order

        route_id1 = self.dedup.create_route_id(path1, pools1)
        route_id2 = self.dedup.create_route_id(path2, pools2)

        # Should be identical (normalized by sorting)
        self.assertEqual(route_id1, route_id2)

    def test_create_fingerprint(self):
        """Test that fingerprints are deterministic."""
        route_id = "DAI-USDC-WETH:0xABC-0xDEF-0xGHI"

        fp1 = self.dedup.create_fingerprint(
            route_id=route_id,
            block_number=100,
            gross_bps=125.0,
            fee_bps=90.0,
            gas_usd=1.80,
        )

        fp2 = self.dedup.create_fingerprint(
            route_id=route_id,
            block_number=100,
            gross_bps=125.0,
            fee_bps=90.0,
            gas_usd=1.80,
        )

        # Same inputs should produce same fingerprint
        self.assertEqual(fp1, fp2)

        # Different inputs should produce different fingerprint
        fp3 = self.dedup.create_fingerprint(
            route_id=route_id,
            block_number=101,  # Different block
            gross_bps=125.0,
            fee_bps=90.0,
            gas_usd=1.80,
        )
        self.assertNotEqual(fp1, fp3)

    def test_first_execution_allowed(self):
        """Test that first execution of a route is always allowed."""
        route_id = "test-route"
        fingerprint = "test-fp-001"

        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fingerprint,
            block_number=100,
            net_pct=0.15,
            now=time.time(),
        )

        self.assertTrue(should_exec)
        self.assertIsNone(reason)

    def test_repeated_fingerprint_blocked(self):
        """Test that same fingerprint is blocked within TTL."""
        route_id = "test-route"
        fingerprint = "test-fp-001"
        now = time.time()

        # First execution
        should_exec, _ = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fingerprint,
            block_number=100,
            net_pct=0.15,
            now=now,
        )
        self.assertTrue(should_exec)

        # Record execution
        self.dedup.record_execution(
            route_id=route_id,
            fingerprint=fingerprint,
            block_number=100,
            net_pct=0.15,
            now=now,
        )

        # Try again with same fingerprint immediately
        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fingerprint,
            block_number=100,
            net_pct=0.15,
            now=now + 1,
        )

        self.assertFalse(should_exec)
        self.assertIn("Repeated fingerprint", reason)

    def test_cooldown_enforced(self):
        """Test that route cooldown is enforced."""
        route_id = "test-route"
        fp1 = "test-fp-001"
        fp2 = "test-fp-002"  # Different fingerprint
        now = time.time()

        # First execution
        should_exec, _ = self.dedup.should_execute(
            route_id=route_id, fingerprint=fp1, block_number=100, net_pct=0.15, now=now
        )
        self.assertTrue(should_exec)

        self.dedup.record_execution(
            route_id=route_id, fingerprint=fp1, block_number=100, net_pct=0.15, now=now
        )

        # Try again 30 seconds later with different fingerprint
        # Should still be blocked by cooldown
        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fp2,
            block_number=101,
            net_pct=0.15,
            now=now + 30,
        )

        self.assertFalse(should_exec)
        self.assertIn("cooldown", reason.lower())

    def test_cooldown_expires(self):
        """Test that cooldown expires after cooldown_sec."""
        route_id = "test-route"
        fp1 = "test-fp-001"
        fp2 = "test-fp-002"
        now = time.time()

        # First execution
        self.dedup.record_execution(
            route_id=route_id, fingerprint=fp1, block_number=100, net_pct=0.15, now=now
        )

        # Try again 61 seconds later (after cooldown expires)
        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fp2,
            block_number=102,
            net_pct=0.20,  # Higher net (passes hysteresis)
            now=now + 61,
        )

        self.assertTrue(should_exec)
        self.assertIsNone(reason)

    def test_hysteresis_enforced(self):
        """Test that hysteresis prevents re-triggering without improvement."""
        route_id = "test-route"
        fp1 = "test-fp-001"
        fp2 = "test-fp-002"
        now = time.time()

        # First execution at 0.15% net
        self.dedup.record_execution(
            route_id=route_id, fingerprint=fp1, block_number=100, net_pct=0.15, now=now
        )

        # Try again 61 seconds later with same net% (should fail hysteresis)
        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fp2,
            block_number=102,
            net_pct=0.15,  # Same net, need 0.15 + 0.05 = 0.20%
            now=now + 61,
        )

        self.assertFalse(should_exec)
        self.assertIn("Hysteresis", reason)

    def test_hysteresis_passed_with_improvement(self):
        """Test that hysteresis allows execution with sufficient improvement."""
        route_id = "test-route"
        fp1 = "test-fp-001"
        fp2 = "test-fp-002"
        now = time.time()

        # First execution at 0.15% net
        self.dedup.record_execution(
            route_id=route_id, fingerprint=fp1, block_number=100, net_pct=0.15, now=now
        )

        # Try again 61 seconds later with improved net%
        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fp2,
            block_number=102,
            net_pct=0.21,  # 0.15 + 0.06 > 0.15 + 0.05 (passes hysteresis)
            now=now + 61,
        )

        self.assertTrue(should_exec)
        self.assertIsNone(reason)

    def test_same_block_rejected(self):
        """Test that same block number rejects re-execution."""
        route_id = "test-route"
        fp1 = "test-fp-001"
        fp2 = "test-fp-002"
        now = time.time()

        # First execution in block 100
        self.dedup.record_execution(
            route_id=route_id, fingerprint=fp1, block_number=100, net_pct=0.15, now=now
        )

        # Try again in same block (should be rejected)
        should_exec, reason = self.dedup.should_execute(
            route_id=route_id,
            fingerprint=fp2,
            block_number=100,  # Same block
            net_pct=0.25,
            now=now + 1,
        )

        self.assertFalse(should_exec)
        self.assertIn("Already executed in block", reason)

    def test_cleanup_expired_fingerprints(self):
        """Test that expired fingerprints are cleaned up."""
        route_id = "test-route"
        fingerprint = "test-fp-001"
        now = time.time()

        # Record execution
        self.dedup.record_execution(
            route_id=route_id,
            fingerprint=fingerprint,
            block_number=100,
            net_pct=0.15,
            now=now,
        )

        # Verify fingerprint is tracked
        self.assertEqual(len(self.dedup.seen_fingerprints), 1)

        # Clean up after TTL expires
        self.dedup.cleanup_expired(now + 61)

        # Fingerprint should be removed
        self.assertEqual(len(self.dedup.seen_fingerprints), 0)

    def test_stats_tracking(self):
        """Test that stats are tracked correctly."""
        route_id1 = "route-1"
        route_id2 = "route-2"
        now = time.time()

        # Record two routes
        self.dedup.record_execution(
            route_id=route_id1,
            fingerprint="fp1",
            block_number=100,
            net_pct=0.15,
            now=now,
        )
        self.dedup.record_execution(
            route_id=route_id2,
            fingerprint="fp2",
            block_number=100,
            net_pct=0.18,
            now=now,
        )

        stats = self.dedup.get_stats()

        self.assertEqual(stats["tracked_fingerprints"], 2)
        self.assertEqual(stats["tracked_routes"], 2)


if __name__ == "__main__":
    unittest.main()
