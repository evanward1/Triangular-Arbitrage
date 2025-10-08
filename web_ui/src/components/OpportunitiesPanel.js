import React from 'react';
import './OpportunitiesPanel.css';

function OpportunitiesPanel({ opportunities }) {
  const formatUSD = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  return (
    <div className="panel opportunities-panel">
      <h2>🎯 Current Opportunities</h2>

      {opportunities.length === 0 ? (
        <div className="empty-state">
          <p>No opportunities detected</p>
          <span className="empty-icon">🔍</span>
        </div>
      ) : (
        <div className="opportunities-list">
          {opportunities.map((opp, index) => (
            <div key={index} className="opportunity-item">
              <div className="opp-header">
                <span className="opp-cycle">
                  {opp.cycle.join(' → ')} → {opp.cycle[0]}
                </span>
                <span className={`opp-profit ${opp.profit_pct >= 0 ? 'positive' : 'negative'}`}>
                  {opp.profit_pct >= 0 ? '+' : ''}{opp.profit_pct.toFixed(3)}%
                </span>
              </div>
              <div className="opp-details">
                <span className="opp-usd">
                  Expected: {formatUSD(opp.expected_profit_usd)}
                </span>
                <span className="opp-time">
                  {new Date(opp.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default OpportunitiesPanel;
