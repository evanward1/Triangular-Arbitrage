import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis
} from 'recharts';
import './SlippageHeatmap.css';

// Colour palette — one per exchange, matches the dark palette used elsewhere.
const EXCHANGE_COLORS = {
  binance:  '#f0b90b',
  bybit:    '#58a6ff',
  coinbase: '#3fb950',
  kraken:   '#db6d28',
  okx:      '#c77dff',
};

function getColor(exchange) {
  return EXCHANGE_COLORS[exchange] || '#8892a6';
}

function SlippageHeatmap() {
  const [data, setData]           = useState(null);   // null = not yet fetched
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [selectedExchange, setSelectedExchange] = useState('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/analysis/slippage');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── derived views ──────────────────────────────────────────────────────────

  const exchanges = useMemo(() => data?.exchanges || [], [data]);

  // Scatter: optionally filter by exchange
  const scatterByExchange = useCallback(() => {
    if (!data) return {};
    const map = {};
    for (const ex of exchanges) {
      if (selectedExchange !== 'all' && selectedExchange !== ex) continue;
      map[ex] = data.scatter.filter(d => d.exchange === ex);
    }
    return map;
  }, [data, exchanges, selectedExchange]);

  // ── render helpers ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="slippage-container">
        <div className="slippage-loading">
          <div className="slippage-spinner" />
          <span>Loading slippage data…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="slippage-container">
        <div className="slippage-error">
          <span>Failed to load slippage data: {error}</span>
          <button className="slippage-retry" onClick={fetchData}>Retry</button>
        </div>
      </div>
    );
  }

  if (!data || data.meta.total_trades === 0) {
    return (
      <div className="slippage-container">
        <div className="slippage-empty">No slippage data available — cycle CSV files may be missing or empty.</div>
      </div>
    );
  }

  const scatterGroups = scatterByExchange();

  return (
    <div className="slippage-container">
      {/* Header row: title + exchange filter */}
      <div className="slippage-header">
        <div>
          <h2>Slippage Analysis</h2>
          <p className="slippage-subtitle">
            {data.meta.total_trades} trades across {exchanges.length} exchange{exchanges.length !== 1 ? 'es' : ''} &middot; last 24 h
          </p>
        </div>
        <div className="slippage-filter">
          <label htmlFor="slippage-exchange-filter">Exchange</label>
          <select
            id="slippage-exchange-filter"
            value={selectedExchange}
            onChange={e => setSelectedExchange(e.target.value)}
          >
            <option value="all">All</option>
            {exchanges.map(ex => (
              <option key={ex} value={ex}>{ex.charAt(0).toUpperCase() + ex.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Time-Series: Slippage Spread over 24 h ── */}
      <div className="slippage-panel">
        <h3>Slippage Spread by Hour</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data.time_series} margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
            <XAxis dataKey="label" stroke="#7d8590" tick={{ fontSize: 12 }} />
            <YAxis
              stroke="#7d8590"
              tick={{ fontSize: 12 }}
              label={{ value: 'bps', angle: -90, position: 'insideLeft', style: { fill: '#7d8590', fontSize: 12 } }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#c9d1d9' }}
              labelStyle={{ color: '#f0f6fc', fontWeight: 600 }}
              formatter={(value, name) => [typeof value === 'number' ? value.toFixed(2) + ' bps' : value, name.charAt(0).toUpperCase() + name.slice(1)]}
            />
            <Legend wrapperStyle={{ color: '#c9d1d9', fontSize: 13 }} />
            {exchanges.map(ex => (
              <Line
                key={ex}
                type="monotone"
                dataKey={ex}
                stroke={getColor(ex)}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                name={ex}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* ── Scatter: Trade Size vs Slippage % ── */}
      <div className="slippage-panel">
        <h3>Trade Size vs Slippage %</h3>
        <ResponsiveContainer width="100%" height={280}>
          <ScatterChart margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
            <XAxis
              type="number"
              dataKey="trade_size_usd"
              name="Trade Size"
              stroke="#7d8590"
              tick={{ fontSize: 12 }}
              label={{ value: 'Trade Size (USD)', position: 'insideBottom', offset: -2, style: { fill: '#7d8590', fontSize: 12 } }}
              tickFormatter={v => `$${v}`}
            />
            <YAxis
              type="number"
              dataKey="slippage_pct"
              name="Slippage %"
              stroke="#7d8590"
              tick={{ fontSize: 12 }}
              label={{ value: 'Slippage %', angle: -90, position: 'insideLeft', style: { fill: '#7d8590', fontSize: 12 } }}
              tickFormatter={v => `${v}%`}
            />
            <ZAxis range={[30, 30]} />
            <Tooltip
              contentStyle={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#c9d1d9' }}
              formatter={(value, name) => {
                if (name === 'Trade Size') return [`$${Number(value).toFixed(2)}`, name];
                if (name === 'Slippage %') return [`${Number(value).toFixed(2)}%`, name];
                return [value, name];
              }}
              labelFormatter={() => ''}
            />
            <Legend wrapperStyle={{ color: '#c9d1d9', fontSize: 13 }} />
            {Object.entries(scatterGroups).map(([ex, points]) => (
              <Scatter key={ex} name={ex.charAt(0).toUpperCase() + ex.slice(1)} data={points} fill={getColor(ex)} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default SlippageHeatmap;
