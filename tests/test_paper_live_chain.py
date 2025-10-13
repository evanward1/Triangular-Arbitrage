"""
Unit tests for paper_live_chain mode.
Tests that paper mode uses live chain data paths while never broadcasting.
"""

import sys
from pathlib import Path

# Add parent directory to path before imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web_server import (  # noqa: E402
    DexConfig,
    DexExecutor,
    DexOpportunity,
    MockRPCClient,
    TradingMode,
    app,
    dex_state,
)


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def reset_dex_state():
    """Reset DEX state before each test"""
    dex_state.running = False
    dex_state.mode = TradingMode.PAPER_LIVE_CHAIN
    dex_state.opportunities.clear()
    dex_state.fills.clear()
    dex_state.equity_history.clear()
    yield
    if dex_state.runner_task and not dex_state.runner_task.done():
        dex_state.runner_task.cancel()
    dex_state.running = False


class TestTradingModeEnum:
    """Test TradingMode enum values"""

    def test_mode_enum_values(self):
        """Test that mode enum has correct values"""
        assert TradingMode.OFF.value == "off"
        assert TradingMode.PAPER_LIVE_CHAIN.value == "paper_live_chain"
        assert TradingMode.LIVE.value == "live"

    def test_default_mode_is_paper_live_chain(self, reset_dex_state):
        """Test that default mode is paper_live_chain for safety"""
        assert dex_state.mode == TradingMode.PAPER_LIVE_CHAIN


class TestMockRPCClient:
    """Test MockRPCClient simulates live chain data"""

    @pytest.mark.asyncio
    async def test_get_pool_reserves(self):
        """Test pool reserve simulation"""
        rpc = MockRPCClient()
        reserves = await rpc.get_pool_reserves("0xPoolAddress")

        assert "reserve0" in reserves
        assert "reserve1" in reserves
        assert "timestamp" in reserves
        assert reserves["reserve0"] > 0
        assert reserves["reserve1"] > 0

    @pytest.mark.asyncio
    async def test_estimate_gas(self):
        """Test gas estimation returns realistic values"""
        rpc = MockRPCClient()
        tx_request = {"to": "0xRouter", "data": "0x1234"}

        gas_estimate = await rpc.estimate_gas(tx_request)

        # Should be in realistic range for DEX swap
        assert 100000 < gas_estimate < 300000

    @pytest.mark.asyncio
    async def test_call_transaction(self):
        """Test transaction simulation via eth_call"""
        rpc = MockRPCClient()
        tx_request = {"to": "0xRouter", "data": "0x1234"}

        result = await rpc.call_transaction(tx_request)

        assert result["success"] is True
        assert "gas_used" in result
        assert result["gas_used"] > 0

    @pytest.mark.asyncio
    async def test_get_gas_price(self):
        """Test gas price retrieval"""
        rpc = MockRPCClient()
        gas_price = await rpc.get_gas_price()

        # Should return gas price in wei (realistic range 10-100 gwei)
        assert 10 * 10**9 < gas_price < 100 * 10**9


class TestDexExecutor:
    """Test DexExecutor builds, estimates, and conditionally broadcasts"""

    @pytest.mark.asyncio
    async def test_build_transaction_shared_path(self):
        """Test that build_transaction_request is shared by both modes"""
        rpc = MockRPCClient()
        executor_paper = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)
        executor_live = DexExecutor(rpc, TradingMode.LIVE)

        opp = DexOpportunity(
            id="test1",
            path=["USDC", "WETH"],
            gross_bps=25.0,
            net_bps=5.0,
            gas_bps=18.0,
            slip_bps=2.0,
            size_usd=1000,
            legs=[],
            ts=123456.0,
        )

        tx_paper = await executor_paper.build_transaction_request(opp)
        tx_live = await executor_live.build_transaction_request(opp)

        # Both should build same transaction structure
        assert tx_paper["to"] == tx_live["to"]
        assert "data" in tx_paper
        assert "data" in tx_live
        assert "gasPrice" in tx_paper
        assert "gasPrice" in tx_live

    @pytest.mark.asyncio
    async def test_estimate_and_simulate_shared_path(self):
        """Test that estimate and simulate are shared by both modes"""
        rpc = MockRPCClient()
        executor_paper = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)
        executor_live = DexExecutor(rpc, TradingMode.LIVE)

        tx_request = {"to": "0xRouter", "data": "0x1234", "gasPrice": 25 * 10**9}

        est_paper = await executor_paper.estimate_and_simulate(tx_request)
        est_live = await executor_live.estimate_and_simulate(tx_request)

        # Both should call same estimation methods
        assert "gas_estimate" in est_paper
        assert "simulation" in est_paper
        assert "gas_estimate" in est_live
        assert "simulation" in est_live

    @pytest.mark.asyncio
    async def test_paper_live_chain_no_broadcast(self):
        """Test that paper_live_chain mode never broadcasts"""
        rpc = MockRPCClient()
        executor = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)

        opp = DexOpportunity(
            id="test1",
            path=["USDC", "WETH"],
            gross_bps=25.0,
            net_bps=5.0,
            gas_bps=18.0,
            slip_bps=2.0,
            size_usd=1000,
            legs=[],
            ts=123456.0,
        )

        # Execute in paper_live_chain mode
        fill = await executor.execute(opp)

        # Should have paper=True and no tx_hash
        assert fill.paper is True
        assert fill.tx_hash is None
        assert fill.simulation is not None
        assert "gas_used" in fill.simulation
        assert "success" in fill.simulation

    @pytest.mark.asyncio
    async def test_live_mode_broadcasts(self):
        """Test that live mode calls broadcast method"""
        rpc = MockRPCClient()
        executor = DexExecutor(rpc, TradingMode.LIVE)

        opp = DexOpportunity(
            id="test1",
            path=["USDC", "WETH"],
            gross_bps=25.0,
            net_bps=5.0,
            gas_bps=18.0,
            slip_bps=2.0,
            size_usd=1000,
            legs=[],
            ts=123456.0,
        )

        # Execute in live mode
        fill = await executor.execute(opp)

        # Should have paper=False and a tx_hash
        assert fill.paper is False
        assert fill.tx_hash is not None
        assert fill.tx_hash.startswith("0x")

    @pytest.mark.asyncio
    async def test_broadcast_guard_prevents_paper_broadcast(self):
        """Test that broadcast guard prevents calling in paper mode"""
        rpc = MockRPCClient()
        executor = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)

        tx_request = {"to": "0xRouter", "data": "0x1234"}

        # Attempting to call _broadcast_transaction in paper mode should raise
        with pytest.raises(RuntimeError, match="CRITICAL.*non-live mode"):
            await executor._broadcast_transaction(tx_request)

    @pytest.mark.asyncio
    async def test_simulation_fields_in_fill(self):
        """Test that paper_live_chain fills include simulation fields"""
        rpc = MockRPCClient()
        executor = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)

        opp = DexOpportunity(
            id="test1",
            path=["USDC", "WETH"],
            gross_bps=25.0,
            net_bps=5.0,
            gas_bps=18.0,
            slip_bps=2.0,
            size_usd=1000,
            legs=[],
            ts=123456.0,
        )

        fill = await executor.execute(opp)

        # Verify simulation fields
        assert fill.simulation is not None
        assert fill.simulation["gas_used"] > 0
        assert fill.simulation["success"] is True
        assert "gas_estimate" in fill.simulation

    @pytest.mark.asyncio
    async def test_gas_costs_computed_from_estimates(self):
        """Test that gas costs are computed from live estimates"""
        rpc = MockRPCClient()
        executor = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)

        opp = DexOpportunity(
            id="test1",
            path=["USDC", "WETH"],
            gross_bps=25.0,
            net_bps=10.0,  # High net to ensure positive after gas
            gas_bps=5.0,
            slip_bps=2.0,
            size_usd=1000,
            legs=[],
            ts=123456.0,
        )

        fill = await executor.execute(opp)

        # Net BPS should be adjusted based on actual gas costs
        # It should differ from the opportunity's original net_bps
        assert fill.net_bps != opp.net_bps


class TestConfigUpdate:
    """Test config update handles mode correctly"""

    def test_mode_field_sets_trading_mode(self, reset_dex_state):
        """Test that mode field sets TradingMode enum"""
        config = DexConfig(mode="paper_live_chain")
        dex_state.update_config(config)
        assert dex_state.mode == TradingMode.PAPER_LIVE_CHAIN

        config = DexConfig(mode="live")
        dex_state.update_config(config)
        assert dex_state.mode == TradingMode.LIVE

    def test_legacy_paper_flag_maps_to_mode(self, reset_dex_state):
        """Test that legacy paper flag maps to mode"""
        # paper=True should map to paper_live_chain
        config = DexConfig(paper=True)
        dex_state.update_config(config)
        assert dex_state.mode == TradingMode.PAPER_LIVE_CHAIN

        # paper=False should map to live
        config = DexConfig(paper=False)
        dex_state.update_config(config)
        assert dex_state.mode == TradingMode.LIVE

    def test_rpc_url_and_simulation_config(self, reset_dex_state):
        """Test that RPC and simulation config are stored"""
        config = DexConfig(
            rpc_url="https://eth.llamarpc.com",
            gas_oracle="etherscan",
            simulate_via="mev_sim",
            log_tx_objects=True,
        )
        dex_state.update_config(config)

        assert dex_state.config["rpc_url"] == "https://eth.llamarpc.com"
        assert dex_state.config["gas_oracle"] == "etherscan"
        assert dex_state.config["simulate_via"] == "mev_sim"
        assert dex_state.config["log_tx_objects"] is True


class TestStatusEndpoint:
    """Test status endpoint returns correct mode"""

    def test_status_includes_mode_string(self, client, reset_dex_state):
        """Test that status includes mode as string"""
        response = client.get("/api/dex/status")
        assert response.status_code == 200

        data = response.json()
        status = data["status"]

        assert "mode" in status
        assert status["mode"] in ["off", "paper_live_chain", "live"]

    def test_paper_flag_true_for_paper_live_chain(self, client, reset_dex_state):
        """Test that paper flag is True for paper_live_chain mode"""
        dex_state.mode = TradingMode.PAPER_LIVE_CHAIN

        response = client.get("/api/dex/status")
        status = response.json()["status"]

        assert status["paper"] is True
        assert status["mode"] == "paper_live_chain"

    def test_paper_flag_false_for_live(self, client, reset_dex_state):
        """Test that paper flag is False only for live mode"""
        dex_state.mode = TradingMode.LIVE

        response = client.get("/api/dex/status")
        status = response.json()["status"]

        assert status["paper"] is False
        assert status["mode"] == "live"


class TestControlEndpoint:
    """Test control endpoint accepts and validates mode"""

    @pytest.mark.asyncio
    async def test_control_starts_with_paper_live_chain(self, client, reset_dex_state):
        """Test starting scanner with paper_live_chain mode"""
        response = client.post(
            "/api/dex/control",
            json={"action": "start", "config": {"mode": "paper_live_chain"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

        # Verify mode was set
        assert dex_state.mode == TradingMode.PAPER_LIVE_CHAIN

        # Cleanup
        dex_state.running = False
        if dex_state.runner_task:
            dex_state.runner_task.cancel()

    @pytest.mark.asyncio
    async def test_control_starts_with_live_mode(self, client, reset_dex_state):
        """Test starting scanner with live mode"""
        response = client.post(
            "/api/dex/control", json={"action": "start", "config": {"mode": "live"}}
        )
        assert response.status_code == 200

        # Verify mode was set
        assert dex_state.mode == TradingMode.LIVE

        # Cleanup
        dex_state.running = False
        if dex_state.runner_task:
            dex_state.runner_task.cancel()


class TestIntegration:
    """Integration tests for full flow"""

    @pytest.mark.asyncio
    async def test_scanner_uses_mode_from_state(self):
        """Test that scanner respects mode from dex_state"""
        from web_server import run_dex_scanner

        # Set paper_live_chain mode
        dex_state.mode = TradingMode.PAPER_LIVE_CHAIN
        dex_state.running = True
        dex_state.scan_interval_sec = 0.5

        # Run scanner briefly
        task = asyncio.create_task(run_dex_scanner())
        await asyncio.sleep(2)

        # Stop scanner
        dex_state.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Check that fills were created with paper=True and no tx_hash
        if len(dex_state.fills) > 0:
            for fill in dex_state.fills:
                assert fill.paper is True
                assert fill.tx_hash is None
                assert fill.simulation is not None

    @pytest.mark.asyncio
    async def test_paper_live_chain_never_calls_broadcast(self):
        """Test that paper_live_chain path never attempts broadcast"""
        rpc = MockRPCClient()
        executor = DexExecutor(rpc, TradingMode.PAPER_LIVE_CHAIN)

        # Spy on _broadcast_transaction to ensure it's never called
        original_broadcast = executor._broadcast_transaction
        call_count = [0]

        async def spy_broadcast(tx_request):
            call_count[0] += 1
            return await original_broadcast(tx_request)

        executor._broadcast_transaction = spy_broadcast

        # Execute opportunity
        opp = DexOpportunity(
            id="test1",
            path=["USDC", "WETH"],
            gross_bps=25.0,
            net_bps=5.0,
            gas_bps=18.0,
            slip_bps=2.0,
            size_usd=1000,
            legs=[],
            ts=123456.0,
        )

        await executor.execute(opp)

        # Broadcast should never have been called
        assert call_count[0] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
