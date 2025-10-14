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
    expected_maker_legs: 0,  // DEX default is 0 (maker legs are a CEX concept)
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
        } else if (data.type === 'decision') {
          setDecisions(prev => [data.data, ...prev].slice(0, 100));
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
            gas_model: config.gas_model,
            chain_id: parseInt(config.chain_id)
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

  // Helper to convert bps to percent
  const bpsToPercent = (bps) => (bps / 100).toFixed(2);

  const formatPercent = (bps) => {
    const pct = bps / 100;
    return pct >= 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`;
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

  // Map chain IDs to network names
  const getChainName = (chainId) => {
    const chainMap = {
      1: 'Ethereum',
      137: 'Polygon',
      42161: 'Arbitrum'
    };
    return chainMap[chainId] || `Chain ${chainId}`;
  };

  const chainName = getChainName(status.chain_id);

  // Helper to get profit color class
  const getProfitColorClass = (netBps) => {
    if (netBps >= config.min_profit_threshold_bps) return 'profit-good';
    if (netBps >= 0) return 'profit-marginal';
    return 'profit-loss';
  };

  // Helper to create idempotency key for deduplication
  const getOpportunityKey = (opp) => {
    // Create key from: path (sorted) + timestamp rounded to nearest 30 seconds
    const sortedPath = [...opp.path].sort().join('-');
    const timeBlock = Math.floor(opp.ts / 30) * 30;  // Round to 30-second blocks
    return `${sortedPath}-${timeBlock}`;
  };

  // Deduplicate opportunities - keep only the most recent per key
  const deduplicateOpportunities = (opps) => {
    const keyMap = new Map();
    opps.forEach(opp => {
      const key = getOpportunityKey(opp);
      const existing = keyMap.get(key);
      if (!existing || opp.ts > existing.ts) {
        keyMap.set(key, opp);
      }
    });
    return Array.from(keyMap.values());
  };

  return (
    <div className="dex-dashboard">
      {/* Summary Banner */}
      {running && (
        <div className="dex-summary-banner">
          <div className="summary-content">
            <span className="summary-text">
              Currently watching <strong>{status.pools_loaded} markets</strong>
              {opportunities.length > 0 && (
                <> — Last opportunity: <strong className={getProfitColorClass(opportunities[0].net_bps)}>
                  {formatPercent(opportunities[0].net_bps)}
                </strong> potential gain</>
              )}
            </span>
          </div>
        </div>
      )}

      {/* Control Panel */}
      <div className="dex-panel control-panel">
        <h2>Settings</h2>
        <div className="control-grid">
          <div className="control-section">
            <label title="Run in test mode (no real trades) or run live (real trades)">
              Simulation Mode
            </label>
            <select
              value={config.mode}
              onChange={(e) => setConfig({...config, mode: e.target.value})}
              disabled={running}
            >
              <option value="paper_live_chain">Test Mode (Live Data)</option>
              <option value="live">Live Trading</option>
            </select>
          </div>

          <div className="control-section">
            <label title="Choose which blockchain network to scan for opportunities">
              Network
            </label>
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
            <label title="How much money to simulate per trade">
              Trade Amount (USD)
            </label>
            <input
              type="number"
              value={config.size_usd}
              onChange={(e) => setConfig({...config, size_usd: parseFloat(e.target.value)})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label title="Smallest gain worth trading - only consider opportunities above this profit threshold">
              Minimum Target Profit (%)
            </label>
            <input
              type="number"
              step="0.01"
              value={(config.min_profit_threshold_bps / 100).toFixed(2)}
              onChange={(e) => setConfig({...config, min_profit_threshold_bps: parseFloat(e.target.value) * 100})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label title="Safety margin for price movements during trade execution - applied once to entire route">
              Price Safety Margin (%)
            </label>
            <input
              type="number"
              step="0.01"
              value={(config.slippage_floor_bps / 100).toFixed(2)}
              onChange={(e) => setConfig({...config, slippage_floor_bps: parseFloat(e.target.value) * 100})}
              disabled={running}
              placeholder="e.g., 0.01 for 0.01%"
            />
          </div>

          <div className="control-section" style={{display: 'none'}}>
            {/* Hidden for DEX mode - maker legs are a CEX concept */}
            <label>Expected Maker Legs</label>
            <input
              type="number"
              value={config.expected_maker_legs}
              onChange={(e) => setConfig({...config, expected_maker_legs: parseInt(e.target.value)})}
              disabled={running}
            />
          </div>

          <div className="control-section">
            <label title="Network speed - fast = higher fee but faster confirmation">
              Network Speed
            </label>
            <select
              value={config.gas_model}
              onChange={(e) => setConfig({...config, gas_model: e.target.value})}
              disabled={running}
            >
              <option value="slow">Slow (Cheaper)</option>
              <option value="standard">Standard</option>
              <option value="fast">Fast (Recommended)</option>
              <option value="instant">Instant (Most Expensive)</option>
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
        <h2>Current Status</h2>
        <div className="status-grid">
          <div className="status-item">
            <span className="status-label" title="Whether the scanner is running in test mode or live trading mode">
              Running Mode:
            </span>
            <span className={`status-value ${status.paper ? 'paper' : 'live'}`}>
              {status.mode === 'paper_live_chain' ? 'Test Mode (Live Data)' :
               status.mode === 'live' ? 'Live Trading' : 'Stopped'}
            </span>
          </div>
          <div className="status-item">
            <span className="status-label" title="Which blockchain network is being scanned">
              Network:
            </span>
            <span className="status-value">{chainName}</span>
          </div>
          <div className="status-item">
            <span className="status-label" title="Number of trading markets being monitored for opportunities">
              Markets Scanned:
            </span>
            <span className="status-value">{status.pools_loaded}</span>
          </div>
          <div className="status-item">
            <span className="status-label" title="How often the scanner checks for new opportunities">
              Check Frequency:
            </span>
            <span className="status-value">Every {status.scan_interval_sec}s</span>
          </div>
          <div className="status-item">
            <span className="status-label" title="Highest price difference found (before accounting for trading costs)">
              Best Price Difference:
            </span>
            <span className="status-value positive">
              {formatPercent(status.best_gross_bps)}
            </span>
          </div>
          <div className="status-item">
            <span className="status-label" title="Highest expected gain found after all costs (fees, network costs, price changes)">
              Best Expected Gain:
            </span>
            <span className="status-value positive">
              {formatPercent(status.best_net_bps)}
            </span>
          </div>
          <div className="status-item">
            <span className="status-label" title="Time of the most recent market scan">
              Last Check:
            </span>
            <span className="status-value">
              {status.last_scan_ts > 0 ? formatTimestamp(status.last_scan_ts) : 'Never'}
            </span>
          </div>
        </div>
      </div>

      {/* Decision Trace Panel */}
      <div className="dex-panel decision-trace-panel">
        <h2>Recent Decisions (Last 5)</h2>
        <div className="decision-trace-container">
          {decisions.length > 0 ? (
            <table className="decision-trace-table">
              <thead>
                <tr>
                  <th title="When this opportunity was evaluated">Time</th>
                  <th title="Whether the trade was simulated or skipped">Decision</th>
                  <th title="Why this decision was made">Explanation</th>
                  <th title="Expected gain before costs">Before Costs</th>
                  <th title="Expected gain after all costs">After Costs</th>
                  <th title="Minimum profit needed to break even">Breakeven Target</th>
                  <th title="Trade amount being evaluated">Amount</th>
                </tr>
              </thead>
              <tbody>
                {decisions.slice(0, 5).map((decision, idx) => (
                  <tr key={idx} className={decision.action === 'EXECUTE' ? 'execute-row' : 'skip-row'}>
                    <td>{decision.timestamp}</td>
                    <td>
                      <span className={`decision-badge ${decision.action === 'EXECUTE' ? 'execute' : 'skip'}`}>
                        {decision.action === 'EXECUTE' ? 'Trade Simulated' : 'Trade Skipped'}
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
                        <span className="no-reasons">All conditions met</span>
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
        <h2>Trading Opportunities ({opportunities.length})</h2>
        <div className="opps-table-container">
          <table className="opps-table">
            <thead>
              <tr>
                <th title="The sequence of tokens involved in this trade route">Trade Route</th>
                <th
                  onClick={() => toggleSort('gross_bps')}
                  style={{cursor: 'pointer'}}
                  title="Expected gain before costs - this is the price difference found in the market"
                >
                  Expected Gain (before costs) {sortField === 'gross_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th title="Trading fees = what exchanges charge">Trading Fees</th>
                <th
                  onClick={() => toggleSort('slip_bps')}
                  style={{cursor: 'pointer'}}
                  title="Safety margin = extra room for small price moves"
                >
                  Safety Margin {sortField === 'slip_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th
                  onClick={() => toggleSort('gas_bps')}
                  style={{cursor: 'pointer'}}
                  title="Blockchain fee = the cost to submit the trade"
                >
                  Blockchain Fee {sortField === 'gas_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th
                  onClick={() => toggleSort('net_bps')}
                  style={{cursor: 'pointer'}}
                  title="Your expected profit = price difference minus all costs"
                >
                  Your Expected Profit {sortField === 'net_bps' && (sortDesc ? '▼' : '▲')}
                </th>
                <th title="Amount of money being traded">Trade Amount</th>
                <th title="When this opportunity was detected">Detected At</th>
              </tr>
            </thead>
            <tbody>
              {sortOpportunities(deduplicateOpportunities(opportunities)).map((opp) => {
                return (
                  <tr
                    key={opp.id}
                    onClick={() => setSelectedOpp(opp)}
                    className={`${selectedOpp?.id === opp.id ? 'selected' : ''} ${getProfitColorClass(opp.net_bps)}`}
                  >
                    <td className="path-cell">{opp.path.join(' → ')}</td>
                    <td className="positive" title={`${opp.gross_bps.toFixed(1)} bps`}>
                      {formatPercent(opp.gross_bps)}
                    </td>
                    <td title={`${opp.fee_bps.toFixed(1)} bps`}>
                      {formatPercent(opp.fee_bps)}
                    </td>
                    <td title={`${opp.slip_bps.toFixed(1)} bps`}>
                      {formatPercent(opp.slip_bps)}
                    </td>
                    <td title={`${opp.gas_bps.toFixed(1)} bps = ${formatUSD(opp.gas_bps * opp.size_usd / 10000)}`}>
                      {formatPercent(opp.gas_bps)} ({formatUSD(opp.gas_bps * opp.size_usd / 10000)})
                    </td>
                    <td
                      className={opp.net_bps >= 0 ? 'positive' : 'negative'}
                      title={`${opp.net_bps.toFixed(1)} bps`}
                    >
                      <strong>{formatPercent(opp.net_bps)}</strong>
                    </td>
                    <td>{formatUSD(opp.size_usd)}</td>
                    <td>{formatTimestamp(opp.ts)}</td>
                  </tr>
                );
              })}
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
            <h3>Cost Breakdown</h3>
            <button onClick={() => setSelectedOpp(null)}>✕</button>
          </div>
          <div className="drawer-content">
            <div className="drawer-section highlight">
              <strong>Trade Route:</strong>
              <div className="route-display">{selectedOpp.path.join(' → ')}</div>
            </div>

            <div className="drawer-section">
              <h4>Profit Calculation</h4>
              <div className="cost-breakdown">
                <div className="cost-line">
                  <span className="cost-label">Starting with:</span>
                  <span className="cost-value">{formatUSD(selectedOpp.size_usd)}</span>
                </div>
                <div className="cost-line highlight">
                  <span className="cost-label">Expected gain (before costs):</span>
                  <span className="cost-value positive">
                    {formatPercent(selectedOpp.gross_bps)}
                    <span className="usd-equiv">({formatUSD(selectedOpp.gross_bps * selectedOpp.size_usd / 10000)})</span>
                  </span>
                </div>
                <div className="cost-separator">Minus costs:</div>
                <div className="cost-line indent">
                  <span className="cost-label">Trading fees:</span>
                  <span className="cost-value negative">
                    {formatPercent(selectedOpp.fee_bps)}
                    <span className="usd-equiv">({formatUSD(selectedOpp.fee_bps * selectedOpp.size_usd / 10000)})</span>
                  </span>
                </div>
                <div className="cost-line indent">
                  <span className="cost-label">Safety margin:</span>
                  <span className="cost-value negative">
                    {formatPercent(selectedOpp.slip_bps)}
                    <span className="usd-equiv">({formatUSD(selectedOpp.slip_bps * selectedOpp.size_usd / 10000)})</span>
                  </span>
                </div>
                <div className="cost-line indent">
                  <span className="cost-label">Blockchain fee:</span>
                  <span className="cost-value negative">
                    {formatPercent(selectedOpp.gas_bps)}
                    <span className="usd-equiv">({formatUSD(selectedOpp.gas_bps * selectedOpp.size_usd / 10000)})</span>
                  </span>
                </div>
                <div className="cost-separator"></div>
                <div className="cost-line total">
                  <span className="cost-label"><strong>Final expected gain:</strong></span>
                  <span className={`cost-value ${selectedOpp.net_bps >= 0 ? 'positive' : 'negative'}`}>
                    <strong>{formatPercent(selectedOpp.net_bps)}</strong>
                    <span className="usd-equiv"><strong>({formatUSD(selectedOpp.net_bps * selectedOpp.size_usd / 10000)})</strong></span>
                  </span>
                </div>
              </div>
            </div>

            {selectedOpp.legs && selectedOpp.legs.length > 0 && (
              <div className="drawer-section">
                <h4>Trade Steps</h4>
                {selectedOpp.legs.map((leg, idx) => (
                  <div key={idx} className="leg-detail">
                    <div className="leg-header"><strong>Step {idx + 1}: {leg.pair}</strong> ({leg.side})</div>
                    <div className="leg-info">
                      <div>Price: {leg.price.toFixed(2)}</div>
                      <div>Available Liquidity: {formatUSD(leg.liq_usd)}</div>
                      <div>Estimated Price Impact: {formatPercent(leg.slip_bps_est || 0)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Performance Chart and Recent Trades */}
      <div className="dex-bottom-row">
        <div className="dex-panel equity-panel">
          <h2>Performance Over Time</h2>
          {equity.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={equity}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3f5f" />
                <XAxis
                  dataKey="ts"
                  tickFormatter={formatTimestamp}
                  stroke="#8892a6"
                />
                <YAxis
                  stroke="#8892a6"
                  label={{ value: 'USD', angle: -90, position: 'insideLeft', style: { fill: '#8892a6' } }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a1f3a', border: '1px solid #00d4ff' }}
                  labelFormatter={formatTimestamp}
                  formatter={(value) => [formatUSD(value), 'Cumulative Profit']}
                />
                <Line
                  type="monotone"
                  dataKey="cumulative_pnl_usd"
                  stroke="#00ff88"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">No performance data yet</div>
          )}
        </div>

        <div className="dex-panel fills-panel">
          <h2>Recent Trades ({fills.length})</h2>
          <div className="fills-table-container">
            <table className="fills-table">
              <thead>
                <tr>
                  <th title="When this trade was executed">Time</th>
                  <th title="Whether this was a test trade or live trade">Mode</th>
                  <th title="Final profit percentage after all costs">Profit %</th>
                  <th title="Profit or loss in dollars">Gain/Loss</th>
                  <th title="Blockchain transaction details">Transaction</th>
                </tr>
              </thead>
              <tbody>
                {fills.slice(0, 10).map((fill) => (
                  <tr key={fill.id}>
                    <td>{formatTimestamp(fill.ts)}</td>
                    <td>
                      <span className={`mode-badge ${fill.paper ? 'paper' : 'live'}`}>
                        {fill.paper ? 'Test' : 'Live'}
                      </span>
                    </td>
                    <td className={fill.net_bps >= 0 ? 'positive' : 'negative'}>
                      {formatPercent(fill.net_bps)}
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
                          title="View on Etherscan"
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
              <div className="empty-state">No trades executed yet</div>
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
