import React, { useState, useEffect } from 'react';
import './DexMevDashboard.css';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

function DexMevDashboard() {
  const [status, setStatus] = useState({
    mode: 'off',
    paper: true,
    chain_id: 1,
    scan_interval_sec: 10,
    pools_loaded: 0,
    last_scan_ts: 0,
    best_gross_bps: 0.0,
    best_net_bps: 0.0,
    config: {
      size_usd: 1000,
      min_profit_threshold_bps: 0,
      slippage_mode: 'dynamic',
      slippage_floor_bps: 5,
      expected_maker_legs: 2,
      gas_model: 'fast'
    }
  });

  const [opportunities, setOpportunities] = useState([]);
  const [fills, setFills] = useState([]);
  const [equity, setEquity] = useState([]);
  const [logs, setLogs] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [running, setRunning] = useState(false);
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [sortField, setSortField] = useState('net_bps');
  const [sortDesc, setSortDesc] = useState(true);

  // Config form state
  const [config, setConfig] = useState({
    size_usd: 1000,
    min_profit_threshold_bps: 0,
    slippage_floor_bps: 5,
    expected_maker_legs: 2,
    gas_model: 'fast',
    mode: 'paper_live_chain',  // paper_live_chain or live
    chain_id: 1
  });

  // WebSocket connection with reconnect and backoff
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/dex`;

    let ws = null;
    let reconnectTimeout = null;
    let reconnectAttempts = 0;
    const maxReconnectDelay = 30000; // 30 seconds max
    const baseDelay = 1000; // 1 second base

    // Recent message buffer (max 200)
    const messageBuffer = [];
    const maxBufferSize = 200;

    const fetchSnapshot = async () => {
      try {
        const [statusRes, oppsRes, fillsRes, equityRes, logsRes, decisionsRes] = await Promise.all([
          fetch('/api/dex/status'),
          fetch('/api/dex/opportunities'),
          fetch('/api/dex/fills'),
          fetch('/api/dex/equity'),
          fetch('/api/dex/logs'),
          fetch('/api/dex/decisions')
        ]);

        if (statusRes.ok) {
          const data = await statusRes.json();
          setStatus(data.status);
          setRunning(data.status.running || false);
        }
        if (oppsRes.ok) {
          const data = await oppsRes.json();
          setOpportunities(data.opportunities || []);
        }
        if (fillsRes.ok) {
          const data = await fillsRes.json();
          setFills(data.fills || []);
        }
        if (equityRes.ok) {
          const data = await equityRes.json();
          // Map "points" to equity chart format
          const points = data.points || [];
          setEquity(points);
        }
        if (logsRes.ok) {
          const data = await logsRes.json();
          setLogs(data.logs || []);
        }
        if (decisionsRes.ok) {
          const data = await decisionsRes.json();
          setDecisions(data.decisions || []);
        }
      } catch (error) {
        console.error('Error fetching snapshot:', error);
      }
    };

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onopen = async () => {
        console.log('DEX WebSocket connected');
        reconnectAttempts = 0;

        // Fetch recent snapshot on connect
        await fetchSnapshot();

        // Merge any buffered messages
        messageBuffer.forEach(msg => {
          if (msg.type === 'opportunity') {
            setOpportunities(prev => {
              const exists = prev.some(o => o.id === msg.data.id);
              if (!exists) {
                return [msg.data, ...prev].slice(0, 50);
              }
              return prev;
            });
          } else if (msg.type === 'fill') {
            setFills(prev => {
              const exists = prev.some(f => f.id === msg.data.id);
              if (!exists) {
                return [msg.data, ...prev].slice(0, 100);
              }
              return prev;
            });
          }
        });
        messageBuffer.length = 0;
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // Buffer message
        if (messageBuffer.length < maxBufferSize) {
          messageBuffer.push(data);
        } else {
          messageBuffer.shift();
          messageBuffer.push(data);
        }

        if (data.type === 'status') {
          setStatus(data.data);
          setRunning(data.data.running || false);
        } else if (data.type === 'opportunity') {
          setOpportunities(prev => {
            const exists = prev.some(o => o.id === data.data.id);
            if (!exists) {
              return [data.data, ...prev].slice(0, 50);
            }
            return prev;
          });
        } else if (data.type === 'fill') {
          setFills(prev => {
            const exists = prev.some(f => f.id === data.data.id);
            if (!exists) {
              return [data.data, ...prev].slice(0, 100);
            }
            return prev;
          });
        } else if (data.type === 'equity') {
          setEquity(prev => [...prev, data.data].slice(-1000));
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.message].slice(-100));
        }
      };

      ws.onclose = () => {
        console.log('DEX WebSocket disconnected, reconnecting...');
        reconnectAttempts++;
        const delay = Math.min(baseDelay * Math.pow(2, reconnectAttempts), maxReconnectDelay);
        reconnectTimeout = setTimeout(connect, delay);
      };

      ws.onerror = (error) => {
        console.error('DEX WebSocket error:', error);
        ws.close();
      };
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  const handleStart = async () => {
    try {
      const response = await fetch('/api/dex/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'start',
          mode: config.mode,
          config: {
            size_usd: parseFloat(config.size_usd),
            min_profit_threshold_bps: parseFloat(config.min_profit_threshold_bps),
            slippage_floor_bps: parseFloat(config.slippage_floor_bps),
            expected_maker_legs: parseInt(config.expected_maker_legs),
            gas_model: config.gas_model
          }
        })
      });

      if (response.ok) {
        const data = await response.json();
        setRunning(data.running || true);
        // Refresh status
        const statusRes = await fetch('/api/dex/status');
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setStatus(statusData.status);
        }
      }
    } catch (error) {
      console.error('Error starting DEX:', error);
    }
  };

  const handleStop = async () => {
    try {
      const response = await fetch('/api/dex/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });

      if (response.ok) {
        const data = await response.json();
        setRunning(data.running || false);
        // Refresh status
        const statusRes = await fetch('/api/dex/status');
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setStatus(statusData.status);
        }
      }
    } catch (error) {
      console.error('Error stopping DEX:', error);
    }
  };

  const formatBps = (bps) => {
    return bps >= 0 ? `+${bps.toFixed(2)}` : bps.toFixed(2);
  };

  const formatUSD = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  };

  const formatTimestamp = (ts) => {
    return new Date(ts * 1000).toLocaleTimeString();
  };

  const sortOpportunities = (opps) => {
    return [...opps].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      return sortDesc ? bVal - aVal : aVal - bVal;
    });
  };

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortDesc(!sortDesc);
    } else {
      setSortField(field);
      setSortDesc(true);
    }
  };

  const chainName = status.chain_id === 1 ? 'Ethereum' : `Chain ${status.chain_id}`;

  return (
    <div className="dex-dashboard">
      {/* Control Panel */}
      <div className="dex-panel control-panel">
        <h2>Control Panel</h2>
        <div className="control-grid">
          <div className="control-section">
            <label>Mode</label>
            <select
              value={config.mode}
              onChange={(e) => setConfig({...config, mode: e.target.value})}
              disabled={running}
            >
              <option value="paper_live_chain">Paper (Live Chain)</option>
              <option value="live">Live Trading</option>
            </select>
          </div>

          <div className="control-section">
            <label>Chain</label>
            <select
              value={config.chain_id}
              onChange={(e) => setConfig({...config, chain_id: parseInt(e.target.value)})}
              disabled={running}
            >
              <option value="1">Ethereum (1)</option>
              <option value="137">Polygon (137)</option>
              <option value="42161">Arbitrum (42161)</option>
            </select>
          </div>

          <div className="control-section">
            <label>Size (USD)</label>
            <input
              type="number"
              value={config.size_usd}
              onChange={(e) => setConfig({...config, size_usd: parseFloat(e.target.value)})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label>Min Profit (bps)</label>
            <input
              type="number"
              value={config.min_profit_threshold_bps}
              onChange={(e) => setConfig({...config, min_profit_threshold_bps: parseFloat(e.target.value)})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label>Slippage Floor (bps)</label>
            <input
              type="number"
              value={config.slippage_floor_bps}
              onChange={(e) => setConfig({...config, slippage_floor_bps: parseFloat(e.target.value)})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label>Expected Maker Legs</label>
            <input
              type="number"
              value={config.expected_maker_legs}
              onChange={(e) => setConfig({...config, expected_maker_legs: parseInt(e.target.value)})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label>Gas Model</label>
            <select
              value={config.gas_model}
              onChange={(e) => setConfig({...config, gas_model: e.target.value})}
              disabled={running}
            >
              <option value="slow">Slow</option>
              <option value="standard">Standard</option>
              <option value="fast">Fast</option>
              <option value="instant">Instant</option>
            </select>
          </div>

          <div className="control-section control-buttons">
            {!running ? (
              <button className="btn-start" onClick={handleStart}>
                Start Scanner
              </button>
            ) : (
              <button className="btn-stop" onClick={handleStop}>
                Stop Scanner
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Status Panel */}
      <div className="dex-panel status-panel">
        <h2>Status</h2>
        <div className="status-grid">
          <div className="status-item">
            <span className="status-label">Mode:</span>
            <span className={`status-value ${status.paper ? 'paper' : 'live'}`}>
              {status.mode === 'paper_live_chain' ? 'Paper (Live Chain)' :
               status.mode === 'live' ? 'Live' : 'Off'}
            </span>
          </div>
          <div className="status-item">
            <span className="status-label">Chain:</span>
            <span className="status-value">{chainName}</span>
          </div>
          <div className="status-item">
            <span className="status-label">Pools Loaded:</span>
            <span className="status-value">{status.pools_loaded}</span>
          </div>
          <div className="status-item">
            <span className="status-label">Scan Interval:</span>
            <span className="status-value">{status.scan_interval_sec}s</span>
          </div>
          <div className="status-item">
            <span className="status-label">Best Gross:</span>
            <span className="status-value positive">{formatBps(status.best_gross_bps)} bps</span>
          </div>
          <div className="status-item">
            <span className="status-label">Best Net:</span>
            <span className="status-value positive">{formatBps(status.best_net_bps)} bps</span>
          </div>
          <div className="status-item">
            <span className="status-label">Last Scan:</span>
            <span className="status-value">
              {status.last_scan_ts > 0 ? formatTimestamp(status.last_scan_ts) : 'Never'}
            </span>
          </div>
        </div>
      </div>

      {/* Decision Trace Panel */}
      <div className="dex-panel decision-trace-panel">
        <h2>Decision Trace (Last 5)</h2>
        <div className="decision-trace-container">
          {decisions.length > 0 ? (
            <table className="decision-trace-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Reasons</th>
                  <th>Gross</th>
                  <th>Net</th>
                  <th>Breakeven</th>
                  <th>Size</th>
                </tr>
              </thead>
              <tbody>
                {decisions.slice(0, 5).map((decision, idx) => (
                  <tr key={idx} className={decision.action === 'EXECUTE' ? 'execute-row' : 'skip-row'}>
                    <td>{decision.timestamp}</td>
                    <td>
                      <span className={`decision-badge ${decision.action === 'EXECUTE' ? 'execute' : 'skip'}`}>
                        {decision.action}
                      </span>
                    </td>
                    <td className="reasons-cell">
                      {decision.reasons.length > 0 ? (
                        <div className="reasons-list">
                          {decision.reasons.map((reason, ridx) => (
                            <div key={ridx} className="reason-item">{reason}</div>
                          ))}
                        </div>
                      ) : (
                        <span className="no-reasons">-</span>
                      )}
                    </td>
                    <td className="positive">{decision.metrics.gross_pct?.toFixed(2)}%</td>
                    <td className={decision.metrics.net_pct >= 0 ? 'positive' : 'negative'}>
                      {decision.metrics.net_pct?.toFixed(2)}%
                    </td>
                    <td>{decision.metrics.breakeven_gross_pct?.toFixed(2)}%</td>
                    <td>{formatUSD(decision.metrics.size_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">No decisions yet</div>
          )}
        </div>
      </div>

      {/* Opportunities Table */}
      <div className="dex-panel opps-panel">
        <h2>Opportunities ({opportunities.length})</h2>
        <div className="opps-table-container">
          <table className="opps-table">
            <thead>
              <tr>
                <th>Path</th>
                <th onClick={() => toggleSort('gross_bps')} style={{cursor: 'pointer'}}>
                  Gross {sortField === 'gross_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th onClick={() => toggleSort('net_bps')} style={{cursor: 'pointer'}}>
                  Net {sortField === 'net_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th onClick={() => toggleSort('gas_bps')} style={{cursor: 'pointer'}}>
                  Gas {sortField === 'gas_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th onClick={() => toggleSort('slip_bps')} style={{cursor: 'pointer'}}>
                  Slip {sortField === 'slip_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th>Size</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {sortOpportunities(opportunities).map((opp) => (
                <tr
                  key={opp.id}
                  onClick={() => setSelectedOpp(opp)}
                  className={selectedOpp?.id === opp.id ? 'selected' : ''}
                >
                  <td className="path-cell">{opp.path.join(' → ')}</td>
                  <td className="positive">{formatBps(opp.gross_bps)} bps</td>
                  <td className={opp.net_bps >= 0 ? 'positive' : 'negative'}>
                    {formatBps(opp.net_bps)} bps
                  </td>
                  <td>{formatBps(opp.gas_bps)} bps</td>
                  <td>{formatBps(opp.slip_bps)} bps</td>
                  <td>{formatUSD(opp.size_usd)}</td>
                  <td>{formatTimestamp(opp.ts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {opportunities.length === 0 && (
            <div className="empty-state">No opportunities detected yet</div>
          )}
        </div>
      </div>

      {/* Opportunity Details Drawer */}
      {selectedOpp && (
        <div className="opp-drawer">
          <div className="drawer-header">
            <h3>Opportunity Details</h3>
            <button onClick={() => setSelectedOpp(null)}>✕</button>
          </div>
          <div className="drawer-content">
            <div className="drawer-section">
              <strong>Path:</strong> {selectedOpp.path.join(' → ')}
            </div>
            <div className="drawer-section">
              <strong>Gross Profit:</strong> <span className="positive">{formatBps(selectedOpp.gross_bps)} bps</span>
            </div>
            <div className="drawer-section">
              <strong>Net Profit:</strong>
              <span className={selectedOpp.net_bps >= 0 ? 'positive' : 'negative'}>
                {formatBps(selectedOpp.net_bps)} bps
              </span>
            </div>
            <div className="drawer-section">
              <strong>Gas Cost:</strong> {formatBps(selectedOpp.gas_bps)} bps
            </div>
            <div className="drawer-section">
              <strong>Slippage:</strong> {formatBps(selectedOpp.slip_bps)} bps
            </div>
            <div className="drawer-section">
              <strong>Size:</strong> {formatUSD(selectedOpp.size_usd)}
            </div>
            <div className="drawer-section legs-section">
              <strong>Legs:</strong>
              {selectedOpp.legs.map((leg, idx) => (
                <div key={idx} className="leg-detail">
                  <div><strong>{leg.pair}</strong> ({leg.side})</div>
                  <div>Price: {leg.price.toFixed(2)}</div>
                  <div>Liquidity: {formatUSD(leg.liq_usd)}</div>
                  <div>Est. Slippage: {formatBps(leg.slip_bps_est)} bps</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Equity Chart and Fills */}
      <div className="dex-bottom-row">
        <div className="dex-panel equity-panel">
          <h2>Equity Curve</h2>
          {equity.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={equity}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3f5f" />
                <XAxis
                  dataKey="ts"
                  tickFormatter={formatTimestamp}
                  stroke="#8892a6"
                />
                <YAxis stroke="#8892a6" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a1f3a', border: '1px solid #00d4ff' }}
                  labelFormatter={formatTimestamp}
                />
                <Line
                  type="monotone"
                  dataKey="equity_usd"
                  stroke="#00ff88"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">No equity data yet</div>
          )}
        </div>

        <div className="dex-panel fills-panel">
          <h2>Recent Fills ({fills.length})</h2>
          <div className="fills-table-container">
            <table className="fills-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Mode</th>
                  <th>Net (bps)</th>
                  <th>P&L</th>
                  <th>TX</th>
                </tr>
              </thead>
              <tbody>
                {fills.slice(0, 10).map((fill) => (
                  <tr key={fill.id}>
                    <td>{formatTimestamp(fill.ts)}</td>
                    <td>
                      <span className={`mode-badge ${fill.paper ? 'paper' : 'live'}`}>
                        {fill.paper ? 'Paper' : 'Live'}
                      </span>
                    </td>
                    <td className={fill.net_bps >= 0 ? 'positive' : 'negative'}>
                      {formatBps(fill.net_bps)} bps
                    </td>
                    <td className={fill.pnl_usd >= 0 ? 'positive' : 'negative'}>
                      {formatUSD(fill.pnl_usd)}
                    </td>
                    <td>
                      {fill.tx_hash ? (
                        <a
                          href={`https://etherscan.io/tx/${fill.tx_hash}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="tx-link"
                        >
                          View
                        </a>
                      ) : (
                        <span className="no-tx">N/A</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
            {fills.length === 0 && (
              <div className="empty-state">No fills yet</div>
            )}
          </div>
        </div>
      </div>

      {/* System Logs */}
      <div className="dex-panel logs-panel">
        <h2>System Logs</h2>
        <div className="logs-container">
          {logs.length > 0 ? (
            logs.map((log, idx) => (
              <div key={idx} className="log-entry">{log}</div>
            ))
          ) : (
            <div className="empty-state">No logs yet</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default DexMevDashboard;
