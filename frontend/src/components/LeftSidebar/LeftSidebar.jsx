import React, { useCallback } from 'react';
import { FaUpload, FaCheckCircle, FaSpinner, FaCog, FaSatellite } from 'react-icons/fa';
import { MdRadar, MdAnchor, MdWaves } from 'react-icons/md';

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2 };

function SpillCard({ spill, selected, onClick }) {
  const ts = new Date(spill.timestamp);
  const timeStr = ts.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    + ' ' + ts.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC';

  return (
    <div
      className={`spill-card ${spill.severity} ${selected ? 'selected' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
    >
      <div className="spill-card-header">
        <span className="spill-id">{spill.id}</span>
        <div style={{ display: 'flex', gap: 4 }}>
          <span className={`spill-badge ${spill.status}`}>{spill.status}</span>
          <span className={`spill-badge ${spill.severity}`}>{spill.severity}</span>
        </div>
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
        <MdWaves size={11} />
        {spill.region}
      </div>

      <div className="spill-meta">
        <div className="spill-meta-item">
          <span className="meta-label">Area</span>
          <span className="meta-value">{spill.area_km2} km²</span>
        </div>
        <div className="spill-meta-item">
          <span className="meta-label">Confidence</span>
          <span className="meta-value">{spill.confidence}%</span>
        </div>
        <div className="spill-meta-item">
          <span className="meta-label">Detected</span>
          <span className="meta-value" style={{ fontSize: 10 }}>{timeStr}</span>
        </div>
        <div className="spill-meta-item">
          <span className="meta-label">Oil Type</span>
          <span className="meta-value" style={{ fontSize: 10 }}>{spill.oil_type_estimate}</span>
        </div>
      </div>

      <div className="confidence-bar" style={{ marginTop: 10 }}>
        <div
          className={`confidence-fill ${spill.severity}`}
          style={{ width: `${spill.confidence}%` }}
        />
      </div>

      <div style={{
        marginTop: 6,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
          {spill.suspects.length} suspect vessel{spill.suspects.length !== 1 ? 's' : ''}
        </span>
        <span style={{ fontSize: 9, color: 'var(--cyan)', fontFamily: 'var(--font-mono)' }}>
          Top: {spill.top_vessel_confidence}%
        </span>
      </div>
    </div>
  );
}

function ProcessingPanel({ state }) {
  const steps = [
    { id: 'uploading',     label: '① SAR Image Upload',           icon: <FaUpload /> },
    { id: 'preprocessing', label: '② Speckle Filter & Normalize', icon: <FaCog /> },
    { id: 'inference',     label: '③ U-Net Segmentation',         icon: <MdRadar /> },
    { id: 'correlating',   label: '④ AIS Correlation Engine',     icon: <MdAnchor /> },
    { id: 'complete',      label: '⑤ Attribution Report Ready',   icon: <FaCheckCircle /> },
  ];

  const order = steps.map(s => s.id);
  const currentIdx = order.indexOf(state);

  return (
    <div className="processing-status">
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--cyan)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '1px' }}>
        Pipeline Running…
      </div>
      {steps.map((step, i) => {
        let status = 'pending';
        if (i < currentIdx) status = 'complete';
        else if (i === currentIdx) status = 'active';

        return (
          <div key={step.id} className="status-step">
            <div className={`status-dot ${status}`} />
            <span className={`status-text ${status}`} style={{ fontSize: 11 }}>
              {step.label}
            </span>
            {status === 'active' && (
              <FaSpinner
                size={10}
                style={{ color: 'var(--cyan)', marginLeft: 'auto', animation: 'spin 1s linear infinite' }}
              />
            )}
            {status === 'complete' && (
              <FaCheckCircle size={10} style={{ color: 'var(--success)', marginLeft: 'auto' }} />
            )}
          </div>
        );
      })}

      {state === 'complete' && (
        <div style={{
          marginTop: 10,
          padding: '8px 10px',
          background: 'var(--success-dim)',
          border: '1px solid rgba(0,230,118,0.3)',
          borderRadius: 'var(--radius-sm)',
          fontSize: 11,
          color: 'var(--success)',
          fontWeight: 500
        }}>
          ✓ Analysis complete — 1 new spill detected
        </div>
      )}
    </div>
  );
}

export default function LeftSidebar({ spills, selectedSpill, onSpillSelect, processingState, onSARUpload }) {
  const sorted = [...spills].sort((a, b) =>
    (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99)
  );

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files[0];
    if (file) onSARUpload(file);
  }, [onSARUpload]);

  const handleFileChange = useCallback((e) => {
    const file = e.target.files[0];
    if (file) onSARUpload(file);
  }, [onSARUpload]);

  return (
    <aside className="left-sidebar">
      {/* SAR Upload */}
      <div className="sidebar-section">
        <div className="section-label"><FaSatellite size={9} /> SAR Analysis</div>

        {processingState && processingState !== 'complete' ? (
          <ProcessingPanel state={processingState} />
        ) : (
          <label
            className="upload-zone"
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            htmlFor="sar-upload"
            style={{ display: 'block', cursor: 'pointer' }}
          >
            <div className="upload-zone-icon">🛰️</div>
            <div className="upload-zone-title">Drop SAR Image Here</div>
            <div className="upload-zone-sub">Sentinel-1 GeoTIFF · VV/VH · 2048×2048</div>
            <input
              id="sar-upload"
              type="file"
              accept=".tiff,.tif,.geotiff"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
          </label>
        )}

        {processingState === 'complete' && (
          <ProcessingPanel state="complete" />
        )}
      </div>

      {/* Model Status */}
      <div className="sidebar-section">
        <div className="section-label">Model Status</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {[
            { label: 'U-Net Segmentation', status: 'Online', color: 'success' },
            { label: 'AIS Correlator', status: 'Online', color: 'success' },
            { label: 'Alert Engine', status: 'Online', color: 'success' },
            { label: 'Sentinel-1 Feed', status: 'Live', color: 'cyan' },
          ].map(item => (
            <div key={item.label} style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '5px 0'
            }}>
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{item.label}</span>
              <span style={{
                fontSize: 10,
                fontWeight: 600,
                color: item.color === 'cyan' ? 'var(--cyan)' : 'var(--success)',
                fontFamily: 'var(--font-mono)'
              }}>
                ● {item.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Detected Spills List */}
      <div className="sidebar-section">
        <div className="section-label">
          <MdWaves size={9} />
          Detected Spills ({spills.length})
        </div>
        {sorted.map(spill => (
          <SpillCard
            key={spill.id}
            spill={spill}
            selected={selectedSpill?.id === spill.id}
            onClick={() => onSpillSelect(spill)}
          />
        ))}
      </div>

      {/* Quick stats at bottom */}
      <div className="sidebar-section">
        <div className="section-label">Region Coverage</div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Monitoring Zone</span>
            <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>Indian Ocean</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Area Covered</span>
            <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>2.4M km²</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Revisit Frequency</span>
            <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>6 hrs</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>AIS Vessels Tracked</span>
            <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>1,247</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
