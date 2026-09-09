import React, { useState } from 'react';
import { FaShip, FaExclamationTriangle, FaBell, FaCheckCircle } from 'react-icons/fa';
import { MdAnchor, MdSpeed, MdRadar, MdLocationOff } from 'react-icons/md';

// Vessel Card
function VesselCard({ vessel, selected, onClick, spill }) {
  const scoreColor = vessel.attribution_score > 80 ? 'var(--critical)'
                   : vessel.attribution_score > 60 ? 'var(--high)'
                   : 'var(--medium)';

  const suspicionClass = vessel.suspicion_level;

  return (
    <div
      className={`vessel-card ${selected ? 'selected' : ''}`}
      onClick={onClick}
      style={{ border: selected ? '1px solid var(--cyan)' : undefined }}
      role="button"
      tabIndex={0}
    >
      <div className="vessel-card-header">
        <div>
          <div className="vessel-name">{vessel.name}</div>
          <div className="vessel-type">{vessel.flag} · {vessel.type}</div>
        </div>
        <div className="attribution-score">
          <div className="score-value" style={{ color: scoreColor }}>
            {vessel.attribution_score.toFixed(1)}%
          </div>
          <div className="score-label">Attribution</div>
        </div>
      </div>

      {/* Rank badge */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 9, fontWeight: 700, padding: '2px 8px',
          borderRadius: 10, textTransform: 'uppercase',
          background: vessel.suspicion_level === 'critical' ? 'var(--critical-dim)' :
                      vessel.suspicion_level === 'high' ? 'var(--high-dim)' : 'var(--medium-dim)',
          color: vessel.suspicion_level === 'critical' ? 'var(--critical)' :
                 vessel.suspicion_level === 'high' ? 'var(--high)' : 'var(--medium)',
          border: `1px solid ${vessel.suspicion_level === 'critical' ? 'rgba(255,58,78,0.3)' :
                                vessel.suspicion_level === 'high' ? 'rgba(255,140,0,0.3)' : 'rgba(245,200,66,0.3)'}`
        }}>
          ⚠ {vessel.suspicion_level} suspect
        </span>
        <span style={{
          fontSize: 9, padding: '2px 8px', borderRadius: 10,
          background: 'var(--bg-elevated)', color: 'var(--text-muted)',
          border: '1px solid var(--border-dim)'
        }}>
          MMSI: {vessel.mmsi}
        </span>
      </div>

      {/* Evidence bars */}
      <div className="evidence-bars">
        {[
          { label: 'Proximity to Spill', value: vessel.evidence.proximity_score },
          { label: 'Speed Anomaly', value: vessel.evidence.speed_anomaly },
          { label: 'Heading Deviation', value: vessel.evidence.heading_deviation },
          { label: 'Vessel Type Weight', value: vessel.evidence.vessel_type_weight },
        ].map(item => (
          <div key={item.label} className="evidence-row">
            <span className="evidence-label">{item.label}</span>
            <div className="evidence-bar-track">
              <div className="evidence-bar-fill" style={{ width: `${item.value}%` }} />
            </div>
            <span className="evidence-pct">{item.value}</span>
          </div>
        ))}
      </div>

      {/* AIS Gap Warning */}
      {vessel.evidence.ais_gap_minutes > 0 && (
        <div className="ais-gap-warning">
          <MdLocationOff size={12} />
          AIS transponder DARK for {vessel.evidence.ais_gap_minutes} min near spill origin
        </div>
      )}

      {/* Info row */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', marginTop: 10,
        padding: '6px 0', borderTop: '1px solid var(--border-subtle)'
      }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          <MdSpeed size={10} style={{ marginRight: 3 }} />
          {vessel.current_speed} kts
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          HDG {vessel.current_heading}°
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          DWT: {vessel.dwt.toLocaleString()} t
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {vessel.call_sign}
        </span>
      </div>

      {/* Owner */}
      <div style={{ fontSize: 10, color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: 6 }}>
        <span style={{ color: 'var(--text-secondary)' }}>Owner: </span>
        {vessel.owner}
      </div>
    </div>
  );
}

// Alert Item Component
function AlertItem({ alert, onAck }) {
  const icons = {
    critical: { icon: '🔴', bg: 'var(--critical-dim)' },
    high:     { icon: '🟠', bg: 'var(--high-dim)' },
    medium:   { icon: '🟡', bg: 'var(--medium-dim)' },
    info:     { icon: 'ℹ️', bg: 'var(--info-dim)' }
  };

  const meta = icons[alert.type] || icons.info;
  const timeAgo = getTimeAgo(alert.timestamp);

  return (
    <div
      className={`alert-item ${!alert.acknowledged ? 'unread' : ''}`}
      onClick={() => !alert.acknowledged && onAck(alert.id)}
    >
      <div className={`alert-icon ${alert.type}`} style={{ background: meta.bg }}>
        {meta.icon}
      </div>
      <div className="alert-content">
        <div className="alert-title">
          {alert.title}
          {!alert.acknowledged && (
            <span style={{
              marginLeft: 6, display: 'inline-block',
              width: 6, height: 6, borderRadius: '50%',
              background: 'var(--cyan)', verticalAlign: 'middle'
            }} />
          )}
        </div>
        <div className="alert-message" title={alert.message}>{alert.message}</div>
        <div className="alert-time">{timeAgo}</div>
      </div>
    </div>
  );
}

function getTimeAgo(ts) {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function RightSidebar({
  vessels, selectedVessel, selectedSpill, alerts, onVesselSelect, onAlertAck
}) {
  const [tab, setTab] = useState('vessels');
  const unreadCount = alerts.filter(a => !a.acknowledged).length;

  return (
    <aside className="right-sidebar">
      {/* Tab selector */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--border-subtle)',
        position: 'sticky',
        top: 0,
        background: 'var(--bg-surface)',
        zIndex: 10
      }}>
        {[
          { id: 'vessels', label: 'Attribution', icon: <FaShip size={10} /> },
          { id: 'alerts',  label: `Alerts${unreadCount > 0 ? ` (${unreadCount})` : ''}`, icon: <FaBell size={10} /> }
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              flex: 1,
              padding: '12px 8px',
              background: 'none',
              border: 'none',
              borderBottom: tab === t.id ? '2px solid var(--cyan)' : '2px solid transparent',
              color: tab === t.id ? 'var(--cyan)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 5,
              transition: 'all 0.15s ease',
              fontFamily: 'var(--font-sans)'
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === 'vessels' && (
        <>
          {/* Spill context */}
          {selectedSpill && (
            <div className="sidebar-section">
              <div style={{
                background: 'var(--bg-card)',
                border: `1px solid ${selectedSpill.severity === 'critical' ? 'rgba(255,58,78,0.3)' : 'var(--border-dim)'}`,
                borderRadius: 'var(--radius-md)',
                padding: '10px 12px'
              }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.8px' }}>
                  Attribution Target
                </div>
                <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>
                  {selectedSpill.id}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                  {selectedSpill.region} · {selectedSpill.area_km2} km² · {selectedSpill.oil_type_estimate}
                </div>
              </div>
            </div>
          )}

          <div className="sidebar-section">
            <div className="section-label">
              <MdRadar size={9} />
              Suspect Vessels ({vessels.length})
            </div>

            {vessels.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                Select a spill to see vessel attribution
              </div>
            ) : (
              vessels.map((vessel, i) => (
                <div key={vessel.mmsi}>
                  {i === 0 && (
                    <div style={{
                      fontSize: 9, fontWeight: 700,
                      color: 'var(--critical)', textTransform: 'uppercase',
                      letterSpacing: '1px', marginBottom: 6,
                      display: 'flex', alignItems: 'center', gap: 4
                    }}>
                      <FaExclamationTriangle size={8} /> Primary Suspect
                    </div>
                  )}
                  {i === 1 && vessels.length > 1 && (
                    <div style={{
                      fontSize: 9, fontWeight: 700,
                      color: 'var(--text-muted)', textTransform: 'uppercase',
                      letterSpacing: '1px', margin: '10px 0 6px',
                    }}>
                      Other Vessels Nearby
                    </div>
                  )}
                  <VesselCard
                    vessel={vessel}
                    selected={selectedVessel?.mmsi === vessel.mmsi}
                    onClick={() => onVesselSelect(vessel)}
                    spill={selectedSpill}
                  />
                </div>
              ))
            )}
          </div>

          {/* Dispatch action */}
          {vessels.length > 0 && (
            <div className="sidebar-section">
              <button className="btn btn-danger" style={{ width: '100%', justifyContent: 'center', padding: '10px' }}>
                <FaExclamationTriangle size={11} />
                Dispatch Alert to Indian Coast Guard
              </button>
              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '10px', marginTop: 6 }}>
                📄 Generate Attribution Report
              </button>
            </div>
          )}
        </>
      )}

      {tab === 'alerts' && (
        <>
          <div style={{
            padding: '10px 12px',
            fontSize: 10,
            color: 'var(--text-muted)',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <span>{unreadCount} unread · Click to acknowledge</span>
            <button
              style={{ background: 'none', border: 'none', color: 'var(--cyan)', cursor: 'pointer', fontSize: 10 }}
              onClick={() => alerts.forEach(a => onAlertAck(a.id))}
            >
              Ack All
            </button>
          </div>
          {alerts.map(alert => (
            <AlertItem key={alert.id} alert={alert} onAck={onAlertAck} />
          ))}
        </>
      )}
    </aside>
  );
}
