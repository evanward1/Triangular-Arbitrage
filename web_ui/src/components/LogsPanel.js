import React, { useEffect, useRef } from 'react';
import './LogsPanel.css';

function LogsPanel({ logs }) {
  const logsEndRef = useRef(null);

  const scrollToBottom = () => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [logs]);

  return (
    <div className="panel logs-panel">
      <h2>📝 System Logs</h2>

      {logs.length === 0 ? (
        <div className="empty-state">
          <p>No logs available</p>
          <span className="empty-icon">📄</span>
        </div>
      ) : (
        <div className="logs-container">
          {logs.map((log, index) => (
            <div key={index} className="log-entry">
              {log}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      )}
    </div>
  );
}

export default LogsPanel;
