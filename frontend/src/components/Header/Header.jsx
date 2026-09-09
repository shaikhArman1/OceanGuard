import React from 'react';
import { FaBell, FaChartBar, FaSatellite } from 'react-icons/fa';
import { MdWaves } from 'react-icons/md';

export default function Header({ stats, liveMode, onToggleLive, onAnalytics, alerts }) {
  const unreadCount = alerts.filter(a => !a.acknowledged).length;

  return (
    <header className="header">
      {/* Brand */}
      <div className="header-brand">
        <div className="header-logo">🌊</div>
        <div>
          <div className="header-title">OceanGuard</div>
          <div className="header-subtitle">SIH PS 26143 · NTRO · Oil Spill Intelligence</div>
        </div>
      </div>

      {/* Live Stats */}
      <div className="header-stats">
        <div className="stat-chip critical">
          <span className="stat-chip-value">{stats.active_spills}</span>
          <span className="stat-chip-label">Active Spills</span>
        </div>
        <div className="stat-chip">
          <span className="stat-chip-value">{stats.sar_images_processed}</span>
          <span className="stat-chip-label">SAR Processed</span>
        </div>
        <div className="stat-chip">
          <span className="stat-chip-value">{stats.vessels_identified}</span>
          <span className="stat-chip-label">Vessels ID'd</span>
        </div>
        <div className="stat-chip success">
          <span className="stat-chip-value">{stats.model_accuracy}%</span>
          <span className="stat-chip-label">Model Accuracy</span>
        </div>
        <div className="stat-chip">
          <span className="stat-chip-value">{stats.response_time_avg_min}m</span>
          <span className="stat-chip-label">Avg. Response</span>
        </div>
      </div>

      {/* Actions */}
      <div className="header-actions">
        <div
          className="live-badge"
          style={{ cursor: 'pointer' }}
          onClick={onToggleLive}
          title="Toggle live mode"
        >
          <span className="live-dot" style={{ background: liveMode ? 'var(--success)' : 'var(--text-muted)' }} />
          {liveMode ? 'LIVE' : 'PAUSED'}
        </div>

        <button className="btn" onClick={onAnalytics}>
          <FaChartBar size={12} />
          Analytics
        </button>

        <button className="btn" style={{ position: 'relative' }}>
          <FaBell size={12} />
          Alerts
          {unreadCount > 0 && (
            <span style={{
              position: 'absolute',
              top: -4,
              right: -4,
              background: 'var(--critical)',
              color: '#fff',
              borderRadius: '50%',
              width: 16,
              height: 16,
              fontSize: 9,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              {unreadCount}
            </span>
          )}
        </button>

        <button className="btn btn-primary">
          <FaSatellite size={12} />
          Request SAR
        </button>
      </div>
    </header>
  );
}
