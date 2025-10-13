"""
Unit tests for DEX/MEV web server endpoints.
Tests all new DEX endpoints, WebSocket functionality, and mock runner.
"""

import sys
from pathlib import Path

# Add parent directory to path before imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web_server import DexFill, DexOpportunity, app, dex_state  # noqa: E402


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def reset_dex_state():
    """Reset DEX state before each test"""
    dex_state.running = False
    dex_state.opportunities.clear()
    dex_state.fills.clear()
    dex_state.equity_history.clear()
    dex_state.pools_loaded = 0
    dex_state.last_scan_ts = 0.0
    dex_state.best_gross_bps = 0.0
    dex_state.best_net_bps = 0.0
    yield
    # Cleanup after test
    if dex_state.runner_task and not dex_state.runner_task.done():
        dex_state.runner_task.cancel()
    dex_state.running = False


class TestDexStatusEndpoint:
    """Test GET /api/dex/status endpoint"""

    def test_status_returns_correct_shape(self, client, reset_dex_state):
        """Test that status endpoint returns expected JSON shape"""
        response = client.get("/api/dex/status")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data

        status = data["status"]
        assert "mode" in status
        assert "paper" in status
        assert "chain_id" in status
        assert "scan_interval_sec" in status
        assert "pools_loaded" in status
        assert "last_scan_ts" in status
        assert "best_gross_bps" in status
        assert "best_net_bps" in status
        assert "config" in status

    def test_status_has_required_config_fields(self, client, reset_dex_state):
        """Test that config contains all required fields"""
        response = client.get("/api/dex/status")
        data = response.json()
        config = data["status"]["config"]

        assert "size_usd" in config
        assert "min_profit_threshold_bps" in config
        assert "slippage_mode" in config
        assert "slippage_floor_bps" in config
        assert "expected_maker_legs" in config

    def test_status_default_values(self, client, reset_dex_state):
        """Test that default values are set correctly"""
        response = client.get("/api/dex/status")
        data = response.json()
        status = data["status"]

        assert status["mode"] == "dex"
        assert status["paper"] is True
        assert status["chain_id"] == 1
        assert status["pools_loaded"] == 0
        assert status["best_gross_bps"] == 0.0
        assert status["best_net_bps"] == 0.0


class TestDexOpportunitiesEndpoint:
    """Test GET /api/dex/opportunities endpoint"""

    def test_opportunities_returns_empty_list(self, client, reset_dex_state):
        """Test that opportunities endpoint returns empty list initially"""
        response = client.get("/api/dex/opportunities")
        assert response.status_code == 200

        data = response.json()
        assert "opportunities" in data
        assert isinstance(data["opportunities"], list)
        assert len(data["opportunities"]) == 0

    def test_opportunities_returns_added_data(self, client, reset_dex_state):
        """Test that opportunities endpoint returns added opportunities"""
        # Add test opportunity
        opp = DexOpportunity(
            id="test_opp_1",
            path=["USDC", "WETH", "DAI"],
            gross_bps=25.0,
            net_bps=5.5,
            gas_bps=18.0,
            slip_bps=1.5,
            size_usd=1000.0,
            legs=[
                {
                    "pair": "USDC/WETH",
                    "side": "buy",
                    "price": 2500.0,
                    "liq_usd": 50000.0,
                    "slip_bps_est": 0.5,
                }
            ],
            ts=1234567890.0,
        )
        dex_state.add_opportunity(opp)

        response = client.get("/api/dex/opportunities")
        data = response.json()

        assert len(data["opportunities"]) == 1
        assert data["opportunities"][0]["id"] == "test_opp_1"
        assert data["opportunities"][0]["path"] == ["USDC", "WETH", "DAI"]
        assert data["opportunities"][0]["gross_bps"] == 25.0
        assert data["opportunities"][0]["net_bps"] == 5.5


class TestDexFillsEndpoint:
    """Test GET /api/dex/fills endpoint"""

    def test_fills_returns_empty_list(self, client, reset_dex_state):
        """Test that fills endpoint returns empty list initially"""
        response = client.get("/api/dex/fills")
        assert response.status_code == 200

        data = response.json()
        assert "fills" in data
        assert isinstance(data["fills"], list)
        assert len(data["fills"]) == 0

    def test_fills_returns_added_data(self, client, reset_dex_state):
        """Test that fills endpoint returns added fills"""
        # Add test fill
        fill = DexFill(
            id="test_fill_1",
            paper=True,
            tx_hash=None,
            net_bps=5.2,
            pnl_usd=2.34,
            ts=1234567890.0,
        )
        dex_state.add_fill(fill)

        response = client.get("/api/dex/fills")
        data = response.json()

        assert len(data["fills"]) == 1
        assert data["fills"][0]["id"] == "test_fill_1"
        assert data["fills"][0]["paper"] is True
        assert data["fills"][0]["tx_hash"] is None
        assert data["fills"][0]["net_bps"] == 5.2
        assert data["fills"][0]["pnl_usd"] == 2.34


class TestDexEquityEndpoint:
    """Test GET /api/dex/equity endpoint"""

    def test_equity_returns_empty_list(self, client, reset_dex_state):
        """Test that equity endpoint returns empty list initially"""
        response = client.get("/api/dex/equity")
        assert response.status_code == 200

        data = response.json()
        assert "equity" in data
        assert isinstance(data["equity"], list)
        assert len(data["equity"]) == 0

    def test_equity_returns_added_points(self, client, reset_dex_state):
        """Test that equity endpoint returns added equity points"""
        # Add equity points
        dex_state.add_equity_point(1000.0)
        dex_state.add_equity_point(1005.5)
        dex_state.add_equity_point(1010.2)

        response = client.get("/api/dex/equity")
        data = response.json()

        assert len(data["equity"]) == 3
        assert data["equity"][0]["equity_usd"] == 1000.0
        assert data["equity"][1]["equity_usd"] == 1005.5
        assert data["equity"][2]["equity_usd"] == 1010.2
        assert "ts" in data["equity"][0]


class TestDexControlEndpoint:
    """Test POST /api/dex/control endpoint"""

    @pytest.mark.asyncio
    async def test_control_start_action(self, client, reset_dex_state):
        """Test starting the DEX scanner"""
        response = client.post("/api/dex/control", json={"action": "start"})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "started"
        assert "config" in data

        # Verify state changed
        assert dex_state.running is True

        # Cleanup
        dex_state.running = False
        if dex_state.runner_task and not dex_state.runner_task.done():
            dex_state.runner_task.cancel()

    @pytest.mark.asyncio
    async def test_control_start_with_config(self, client, reset_dex_state):
        """Test starting with custom configuration"""
        response = client.post(
            "/api/dex/control",
            json={
                "action": "start",
                "config": {
                    "size_usd": 5000,
                    "min_profit_threshold_bps": 10,
                    "chain_id": 137,
                },
            },
        )
        assert response.status_code == 200

        # Verify config was updated
        assert dex_state.config["size_usd"] == 5000
        assert dex_state.config["min_profit_threshold_bps"] == 10
        assert dex_state.chain_id == 137

        # Cleanup
        dex_state.running = False
        if dex_state.runner_task and not dex_state.runner_task.done():
            dex_state.runner_task.cancel()

    @pytest.mark.asyncio
    async def test_control_stop_action(self, client, reset_dex_state):
        """Test stopping the DEX scanner"""
        # First start it
        dex_state.running = True

        response = client.post("/api/dex/control", json={"action": "stop"})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "stopped"

        # Verify state changed
        assert dex_state.running is False

    def test_control_already_running(self, client, reset_dex_state):
        """Test starting when already running"""
        dex_state.running = True

        response = client.post("/api/dex/control", json={"action": "start"})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "already_running"

    def test_control_stop_when_not_running(self, client, reset_dex_state):
        """Test stopping when not running"""
        dex_state.running = False

        response = client.post("/api/dex/control", json={"action": "stop"})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "not_running"

    def test_control_unknown_action(self, client, reset_dex_state):
        """Test unknown action"""
        response = client.post("/api/dex/control", json={"action": "unknown"})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "error"
        assert "unknown" in data["message"].lower()


class TestDexWebSocket:
    """Test WebSocket /ws/dex endpoint"""

    def test_websocket_connects(self, client, reset_dex_state):
        """Test WebSocket connection establishment"""
        with client.websocket_connect("/ws/dex") as websocket:
            # Should receive initial status
            data = websocket.receive_json()
            assert data["type"] == "status"
            assert "data" in data

    def test_websocket_receives_initial_state(self, client, reset_dex_state):
        """Test that initial state is sent on connection"""
        with client.websocket_connect("/ws/dex") as websocket:
            data = websocket.receive_json()

            assert data["type"] == "status"
            status = data["data"]
            assert "mode" in status
            assert "paper" in status
            assert "config" in status


class TestDexStateManager:
    """Test DexStateManager functionality"""

    def test_add_opportunity_updates_best_values(self, reset_dex_state):
        """Test that adding opportunities updates best gross/net BPS"""
        opp1 = DexOpportunity(
            id="opp1",
            path=["A", "B"],
            gross_bps=10.0,
            net_bps=5.0,
            gas_bps=4.0,
            slip_bps=1.0,
            size_usd=1000.0,
            legs=[],
            ts=1234567890.0,
        )
        dex_state.add_opportunity(opp1)

        assert dex_state.best_gross_bps == 10.0
        assert dex_state.best_net_bps == 5.0

        opp2 = DexOpportunity(
            id="opp2",
            path=["C", "D"],
            gross_bps=15.0,
            net_bps=8.0,
            gas_bps=6.0,
            slip_bps=1.0,
            size_usd=1000.0,
            legs=[],
            ts=1234567890.0,
        )
        dex_state.add_opportunity(opp2)

        assert dex_state.best_gross_bps == 15.0
        assert dex_state.best_net_bps == 8.0

    def test_ring_buffer_limits_opportunities(self, reset_dex_state):
        """Test that opportunity ring buffer respects max size"""
        # Add more than max (50 by default)
        for i in range(60):
            opp = DexOpportunity(
                id=f"opp{i}",
                path=["A", "B"],
                gross_bps=10.0,
                net_bps=5.0,
                gas_bps=4.0,
                slip_bps=1.0,
                size_usd=1000.0,
                legs=[],
                ts=float(i),
            )
            dex_state.add_opportunity(opp)

        # Should only keep last 50
        assert len(dex_state.opportunities) == 50
        # Most recent should be kept
        assert dex_state.opportunities[-1].id == "opp59"

    def test_ring_buffer_limits_fills(self, reset_dex_state):
        """Test that fill ring buffer respects max size"""
        # Add more than max (100 by default)
        for i in range(120):
            fill = DexFill(
                id=f"fill{i}",
                paper=True,
                tx_hash=None,
                net_bps=5.0,
                pnl_usd=2.5,
                ts=float(i),
            )
            dex_state.add_fill(fill)

        # Should only keep last 100
        assert len(dex_state.fills) == 100
        # Most recent should be kept
        assert dex_state.fills[-1].id == "fill119"

    def test_update_config_modifies_values(self, reset_dex_state):
        """Test that update_config correctly modifies configuration"""
        from web_server import DexConfig

        config = DexConfig(size_usd=5000, slippage_floor_bps=10, gas_model="instant")

        dex_state.update_config(config)

        assert dex_state.config["size_usd"] == 5000
        assert dex_state.config["slippage_floor_bps"] == 10
        assert dex_state.config["gas_model"] == "instant"


class TestMockDexRunner:
    """Test the mock DEX scanner functionality"""

    @pytest.mark.asyncio
    async def test_mock_runner_generates_opportunities(self, reset_dex_state):
        """Test that mock runner generates opportunities"""
        from web_server import run_dex_scanner

        dex_state.running = True
        dex_state.scan_interval_sec = 0.5  # Speed up for testing

        # Run scanner for a short time
        task = asyncio.create_task(run_dex_scanner())

        # Wait for a few scans
        await asyncio.sleep(2)

        # Stop scanner
        dex_state.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have generated some opportunities
        assert len(dex_state.opportunities) > 0

    @pytest.mark.asyncio
    async def test_mock_runner_generates_fills(self, reset_dex_state):
        """Test that mock runner generates fills"""
        from web_server import run_dex_scanner

        dex_state.running = True
        dex_state.scan_interval_sec = 0.5  # Speed up for testing

        # Run scanner for enough time to generate fills
        task = asyncio.create_task(run_dex_scanner())
        await asyncio.sleep(4)

        # Stop scanner
        dex_state.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have generated some fills (every 6th scan)
        assert len(dex_state.fills) > 0

    @pytest.mark.asyncio
    async def test_mock_runner_updates_pools_loaded(self, reset_dex_state):
        """Test that mock runner updates pools_loaded"""
        from web_server import run_dex_scanner

        dex_state.running = True
        dex_state.scan_interval_sec = 0.5

        task = asyncio.create_task(run_dex_scanner())
        await asyncio.sleep(1)

        # Stop scanner
        dex_state.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have set pools_loaded
        assert dex_state.pools_loaded > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
