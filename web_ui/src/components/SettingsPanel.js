import React, { useState, useEffect } from 'react';
import './SettingsPanel.css';

function SettingsPanel({ botRunning }) {
  const [config, setConfig] = useState({
    min_profit_threshold: -0.50,
    topn: 10
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await fetch('/api/config');
      const data = await response.json();
      setConfig(data);
    } catch (error) {
      console.error('Error fetching config:', error);
    }
  };

  const handleUpdate = async () => {
    setLoading(true);
    setMessage('');

    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': process.env.REACT_APP_WEB_API_KEY || ''
        },
        body: JSON.stringify(config),
      });

      const data = await response.json();

      if (data.status === 'updated') {
        setMessage('✅ ' + data.note);
        setTimeout(() => setMessage(''), 5000);
      }
    } catch (error) {
      setMessage('❌ Error updating configuration');
      console.error('Error updating config:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-panel">
      <h3>⚙️ Bot Settings</h3>

      <div className="setting-group">
        <label htmlFor="threshold">
          Min Profit Threshold (%)
          <span className="help-text">Minimum net profit % to execute trades. Use negative values to see all opportunities.</span>
        </label>
        <input
          id="threshold"
          type="number"
          step="0.01"
          value={config.min_profit_threshold}
          onChange={(e) => setConfig({...config, min_profit_threshold: parseFloat(e.target.value)})}
          disabled={botRunning}
        />
      </div>

      <div className="setting-group">
        <label htmlFor="topn">
          Top N Opportunities
          <span className="help-text">Number of top opportunities to display</span>
        </label>
        <input
          id="topn"
          type="number"
          min="1"
          max="50"
          value={config.topn}
          onChange={(e) => setConfig({...config, topn: parseInt(e.target.value)})}
          disabled={botRunning}
        />
      </div>

      <button
        className="update-button"
        onClick={handleUpdate}
        disabled={loading || botRunning}
      >
        {loading ? 'Updating...' : 'Update Settings'}
      </button>

      {botRunning && (
        <div className="warning-message">
          ⚠️ Stop the bot to change settings
        </div>
      )}

      {message && (
        <div className={`status-message ${message.includes('✅') ? 'success' : 'error'}`}>
          {message}
        </div>
      )}
    </div>
  );
}

export default SettingsPanel;
