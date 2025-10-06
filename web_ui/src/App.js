import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import Dashboard from './components/Dashboard';
import OpportunitiesPanel from './components/OpportunitiesPanel';
import TradeHistory from './components/TradeHistory';
import LogsPanel from './components/LogsPanel';
import SettingsPanel from './components/SettingsPanel';

function App() {
  const [balance, setBalance] = useState({
    total_equity_usd: 0,
    cash_balance: 0,
    asset_balances: {},
    total_trades: 0,
    total_profit_usd: 0
  });

  const [opportunities, setOpportunities] = useState([]);
  const [trades, setTrades] = useState([]);
  const [stats, setStats] = useState({
    uptime_seconds: 0,
    total_scans: 0,
    opportunities_found: 0,
    trades_executed: 0,
    success_rate: 0
  });
  const [logs, setLogs] = useState([]);
  const [botRunning, setBotRunning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [tradingMode, setTradingMode] = useState('paper');
  const [selectedMode, setSelectedMode] = useState('paper');

  // WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:8000/ws`;

    let ws = null;
    let reconnectTimeout = null;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'initial_state') {
          setBalance(data.balance);
          setStats(data.stats);
          setOpportunities(data.opportunities || []);
          setBotRunning(data.bot_running);
          setTradingMode(data.trading_mode || 'paper');
        } else if (data.type === 'update') {
          if (data.balance) setBalance(data.balance);
          if (data.opportunities) setOpportunities(data.opportunities);
        } else if (data.type === 'bot_status') {
          setBotRunning(data.running);
          if (data.mode) setTradingMode(data.mode);
        } else if (data.type === 'log') {
          // Add new log message in real-time
          setLogs(prevLogs => [...prevLogs, data.message].slice(-50));
        }
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setConnected(false);
        // Attempt to reconnect after 3 seconds
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        ws.close();
      };
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  // Fetch data periodically
  const fetchData = useCallback(async () => {
    try {
      const [balanceRes, opportunitiesRes, tradesRes, statsRes, logsRes] = await Promise.all([
        fetch('/api/balance'),
        fetch('/api/opportunities'),
        fetch('/api/trades'),
        fetch('/api/stats'),
        fetch('/api/logs')
      ]);

      if (balanceRes.ok) setBalance(await balanceRes.json());
      if (opportunitiesRes.ok) {
        const data = await opportunitiesRes.json();
        setOpportunities(data.opportunities || []);
      }
      if (tradesRes.ok) {
        const data = await tradesRes.json();
        setTrades(data.trades || []);
      }
      if (statsRes.ok) setStats(await statsRes.json());
      if (logsRes.ok) {
        const data = await logsRes.json();
        setLogs(data.logs || []);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, [fetchData]);

  const startBot = async () => {
    try {
      const response = await fetch(`/api/bot/start?mode=${selectedMode}`, {
        method: 'POST'
      });
      const data = await response.json();

      if (data.status === 'error') {
        alert(data.message);
        return;
      }

      if (response.ok) {
        setBotRunning(true);
        setTradingMode(selectedMode);
      }
    } catch (error) {
      console.error('Error starting bot:', error);
      alert('Failed to start bot. Check console for details.');
    }
  };

  const stopBot = async () => {
    try {
      const response = await fetch('/api/bot/stop', { method: 'POST' });
      if (response.ok) {
        setBotRunning(false);
      }
    } catch (error) {
      console.error('Error stopping bot:', error);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>🔺 Triangular Arbitrage Dashboard</h1>
        <div className="header-controls">
          <div className={`status-indicator ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '🟢 Connected' : '🔴 Disconnected'}
          </div>

          {botRunning && (
            <div className={`mode-indicator ${tradingMode === 'live' ? 'live' : 'paper'}`}>
              {tradingMode === 'paper' ? '📝 Paper Trading' : '💰 Live Trading'}
            </div>
          )}

          {!botRunning && (
            <select
              className="mode-selector"
              value={selectedMode}
              onChange={(e) => setSelectedMode(e.target.value)}
            >
              <option value="paper">📝 Paper Trading</option>
              <option value="live">💰 Live Trading</option>
            </select>
          )}

          <button
            className={`bot-control ${botRunning ? 'stop' : 'start'}`}
            onClick={botRunning ? stopBot : startBot}
          >
            {botRunning ? '⏹ Stop Bot' : '▶️ Start Bot'}
          </button>
        </div>
      </header>

      <main className="App-main">
        <Dashboard balance={balance} stats={stats} />

        <SettingsPanel botRunning={botRunning} />

        <div className="panels-row">
          <OpportunitiesPanel opportunities={opportunities} />
          <TradeHistory trades={trades} />
        </div>

        <LogsPanel logs={logs} />
      </main>
    </div>
  );
}

export default App;
