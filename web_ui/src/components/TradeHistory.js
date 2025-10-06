import React from 'react';
import './TradeHistory.css';

function TradeHistory({ trades }) {
  const formatUSD = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return '✅';
      case 'failed':
        return '❌';
      case 'pending':
        return '⏳';
      default:
        return '•';
    }
  };

  return (
    <div className="panel trade-history-panel">
      <h2>📊 Recent Trades</h2>

      {trades.length === 0 ? (
        <div className="empty-state">
          <p>No trades yet</p>
          <span className="empty-icon">📭</span>
        </div>
      ) : (
        <div className="trades-list">
          {trades.map((trade, index) => (
            <div key={index} className={`trade-item status-${trade.status}`}>
              <div className="trade-header">
                <span className="trade-status">
                  {getStatusIcon(trade.status)}
                </span>
                <span className="trade-cycle">{trade.cycle}</span>
                <span className={`trade-profit ${trade.profit_usd >= 0 ? 'positive' : 'negative'}`}>
                  {trade.profit_usd >= 0 ? '+' : ''}{formatUSD(trade.profit_usd)}
                </span>
              </div>
              <div className="trade-details">
                <span className="trade-time">
                  {new Date(trade.timestamp).toLocaleString()}
                </span>
                {trade.profit_pct !== 0 && (
                  <span className={`trade-pct ${trade.profit_pct >= 0 ? 'positive' : 'negative'}`}>
                    {trade.profit_pct >= 0 ? '+' : ''}{trade.profit_pct.toFixed(3)}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default TradeHistory;
