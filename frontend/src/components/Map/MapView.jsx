import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Polygon, Polyline, CircleMarker, Popup, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { FaLayerGroup, FaExpand, FaCompass, FaShip } from 'react-icons/fa';
import { MdSatelliteAlt } from 'react-icons/md';

const TILE_LAYERS = {
  dark: {
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    tileSize: 256,
    style: 'dark'
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '&copy; <a href="https://www.esri.com/">Esri</a>',
    tileSize: 256
  }
};

// Animated spill popup content
function SpillPopup({ spill }) {
  return (
    <div style={{ fontFamily: 'var(--font-sans)', minWidth: 200 }}>
      <div style={{
        fontSize: 12,
        fontWeight: 700,
        color: spill.severity === 'critical' ? 'var(--critical)'
             : spill.severity === 'high' ? 'var(--high)' : 'var(--medium)',
        marginBottom: 8
      }}>
        🛢️ {spill.id}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: 11 }}>
        <span style={{ color: 'var(--text-muted)' }}>Area</span>
        <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{spill.area_km2} km²</span>
        <span style={{ color: 'var(--text-muted)' }}>Confidence</span>
        <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)' }}>{spill.confidence}%</span>
        <span style={{ color: 'var(--text-muted)' }}>Oil Type</span>
        <span style={{ color: 'var(--text-primary)', fontSize: 10 }}>{spill.oil_type_estimate}</span>
        <span style={{ color: 'var(--text-muted)' }}>Suspects</span>
        <span style={{ color: 'var(--critical)', fontFamily: 'var(--font-mono)' }}>{spill.suspects.length} vessel(s)</span>
      </div>
    </div>
  );
}

function VesselPopup({ vessel }) {
  return (
    <div style={{ fontFamily: 'var(--font-sans)', minWidth: 190 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
        🚢 {vessel.name}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 10px', fontSize: 11 }}>
        <span style={{ color: 'var(--text-muted)' }}>Type</span>
        <span style={{ color: 'var(--text-secondary)' }}>{vessel.type}</span>
        <span style={{ color: 'var(--text-muted)' }}>Flag</span>
        <span style={{ color: 'var(--text-secondary)' }}>{vessel.flag}</span>
        <span style={{ color: 'var(--text-muted)' }}>Speed</span>
        <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)' }}>{vessel.current_speed} kts</span>
        <span style={{ color: 'var(--text-muted)' }}>Attribution</span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          color: vessel.attribution_score > 80 ? 'var(--critical)'
               : vessel.attribution_score > 60 ? 'var(--high)' : 'var(--medium)'
        }}>
          {vessel.attribution_score.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

function MapLayerControl({ mapLayer, onMapLayerChange }) {
  return (
    <div className="map-controls">
      <button
        className={`map-ctrl-btn ${mapLayer === 'dark' ? 'active' : ''}`}
        onClick={() => onMapLayerChange('dark')}
        title="Dark Map"
      >
        <FaLayerGroup size={12} />
      </button>
      <button
        className={`map-ctrl-btn ${mapLayer === 'satellite' ? 'active' : ''}`}
        onClick={() => onMapLayerChange('satellite')}
        title="Satellite Imagery"
      >
        <MdSatelliteAlt size={14} />
      </button>
    </div>
  );
}

function FlyToSpill({ spill }) {
  const map = useMap();
  useEffect(() => {
    if (spill?.center) {
      map.flyTo(spill.center, 9, { duration: 1.2 });
    }
  }, [spill, map]);
  return null;
}

export default function MapView({
  spills, vessels, selectedSpill, selectedVessel,
  onSpillSelect, onVesselSelect, mapLayer, onMapLayerChange
}) {
  const spillColors = { critical: '#ff3a4e', high: '#ff8c00', medium: '#f5c842' };
  const spillFill   = { critical: 'rgba(255,58,78,0.18)', high: 'rgba(255,140,0,0.15)', medium: 'rgba(245,200,66,0.12)' };

  return (
    <div className="map-container">
      <MapContainer
        center={[15, 76]}
        zoom={6}
        style={{ width: '100%', height: '100%' }}
        zoomControl={true}
      >
        <TileLayer
          key={mapLayer}
          url={TILE_LAYERS[mapLayer].url}
          attribution={TILE_LAYERS[mapLayer].attribution}
          maxZoom={18}
        />

        <FlyToSpill spill={selectedSpill} />

        {/* Oil Spill Polygons */}
        {spills.map(spill => (
          <React.Fragment key={spill.id}>
            {/* Glow / outer ring */}
            <Polygon
              positions={spill.polygon}
              pathOptions={{
                color: spillColors[spill.severity],
                weight: 0,
                fillColor: spillColors[spill.severity],
                fillOpacity: spill.status === 'active' ? 0.06 : 0.02,
              }}
            />
            {/* Main spill polygon */}
            <Polygon
              positions={spill.polygon}
              pathOptions={{
                color: spillColors[spill.severity],
                weight: selectedSpill?.id === spill.id ? 2.5 : 1.5,
                opacity: 0.85,
                fillColor: spillFill[spill.severity],
                fillOpacity: 1,
                dashArray: spill.status === 'monitoring' ? '6,4' : null
              }}
              eventHandlers={{ click: () => onSpillSelect(spill) }}
            >
              <Popup>
                <SpillPopup spill={spill} />
              </Popup>
            </Polygon>

            {/* Spill center pulse */}
            <CircleMarker
              center={spill.center}
              radius={spill.status === 'active' ? 8 : 5}
              pathOptions={{
                color: spillColors[spill.severity],
                weight: 2,
                fillColor: spillColors[spill.severity],
                fillOpacity: 0.9
              }}
              eventHandlers={{ click: () => onSpillSelect(spill) }}
            />

            {/* Outer pulse ring */}
            {spill.status === 'active' && (
              <CircleMarker
                center={spill.center}
                radius={20}
                pathOptions={{
                  color: spillColors[spill.severity],
                  weight: 1,
                  fillOpacity: 0,
                  opacity: 0.3,
                  dashArray: '4,4'
                }}
              />
            )}
          </React.Fragment>
        ))}

        {/* Vessel AIS Tracks */}
        {vessels.map(vessel => (
          <React.Fragment key={vessel.mmsi}>
            {/* Track line */}
            <Polyline
              positions={vessel.track}
              pathOptions={{
                color: vessel.color,
                weight: selectedVessel?.mmsi === vessel.mmsi ? 2.5 : 1.5,
                opacity: 0.7,
                dashArray: '8,4'
              }}
            />

            {/* Current position marker */}
            <CircleMarker
              center={vessel.track[vessel.track.length - 1]}
              radius={selectedVessel?.mmsi === vessel.mmsi ? 9 : 6}
              pathOptions={{
                color: vessel.color,
                weight: 2,
                fillColor: vessel.color,
                fillOpacity: 0.9
              }}
              eventHandlers={{ click: () => onVesselSelect(vessel) }}
            >
              <Popup>
                <VesselPopup vessel={vessel} />
              </Popup>
            </CircleMarker>
          </React.Fragment>
        ))}
      </MapContainer>

      {/* Legend */}
      <div className="map-legend">
        <div className="legend-title">Legend</div>
        <div className="legend-item">
          <div className="legend-dot" style={{ background: 'var(--critical)' }} />
          Critical Spill (Active)
        </div>
        <div className="legend-item">
          <div className="legend-dot" style={{ background: 'var(--high)' }} />
          High Severity Spill
        </div>
        <div className="legend-item">
          <div className="legend-dot" style={{ background: 'var(--medium)' }} />
          Medium Severity
        </div>
        <div className="legend-item" style={{ marginTop: 4 }}>
          <div style={{ width: 24, height: 2, background: 'var(--critical)', opacity: 0.7, borderTop: '2px dashed' }} />
          Suspect Vessel Track
        </div>
        <div className="legend-item">
          <div style={{ width: 24, height: 2, background: 'var(--high)', opacity: 0.7, borderTop: '2px dashed' }} />
          Low-suspicion Track
        </div>
      </div>

      {/* Layer Controls */}
      <MapLayerControl mapLayer={mapLayer} onMapLayerChange={onMapLayerChange} />

      {/* Satellite band info overlay */}
      <div style={{
        position: 'absolute',
        top: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 1000,
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-dim)',
        borderRadius: 'var(--radius-md)',
        padding: '5px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        backdropFilter: 'blur(12px)',
        fontSize: 10,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)'
      }}>
        <span style={{ color: 'var(--cyan)' }}>⬡</span>
        Sentinel-1A · SAR C-Band · VV+VH · 10m Resolution · IW Mode
        <span style={{ color: 'var(--success)' }}>● ACTIVE</span>
      </div>
    </div>
  );
}
