import React from 'react';
import './Dashboard.css';

function Dashboard({ balance, stats }) {
  const formatUSD = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatTime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours}h ${minutes}m ${secs}s`;
  };

  const profitClass = balance.total_profit_usd >= 0 ? 'positive' : 'negative';

  return (
    <div className="dashboard">
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Equity</div>
          <div className="stat-value">{formatUSD(balance.total_equity_usd)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Cash Balance</div>
          <div className="stat-value">{formatUSD(balance.cash_balance)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Total Profit</div>
          <div className={`stat-value ${profitClass}`}>
            {formatUSD(balance.total_profit_usd)}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Total Trades</div>
          <div className="stat-value">{balance.total_trades}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Uptime</div>
          <div className="stat-value">{formatTime(stats.uptime_seconds)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Success Rate</div>
          <div className="stat-value">{stats.success_rate.toFixed(1)}%</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Total Scans</div>
          <div className="stat-value">{stats.total_scans}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Opportunities Found</div>
          <div className="stat-value">{stats.opportunities_found}</div>
        </div>
      </div>

      {Object.keys(balance.asset_balances || {}).length > 0 && (
        <div className="asset-balances">
          <h3>Asset Holdings</h3>
          <div className="assets-grid">
            {Object.entries(balance.asset_balances).map(([asset, amount]) => (
              <div key={asset} className="asset-item">
                <span className="asset-symbol">{asset}</span>
                <span className="asset-amount">{amount.toFixed(8)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
