import React, { useState, useEffect } from 'react';
import Header from './components/Header/Header';
import LeftSidebar from './components/LeftSidebar/LeftSidebar';
import MapView from './components/Map/MapView';
import RightSidebar from './components/RightSidebar/RightSidebar';
import AnalyticsModal from './components/Analytics/AnalyticsModal';
import { SPILLS, VESSELS, ALERTS, SYSTEM_STATS } from './data/mockData';
import {
  checkBackendHealth,
  triggerSARAnalysis,
  fetchVesselAttribution,
  subscribeAlertWebSocket
} from './api/client';
import './index.css';

export default function App() {
  const [selectedSpill, setSelectedSpill] = useState(SPILLS[0]);
  const [selectedVessel, setSelectedVessel] = useState(null);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [alerts, setAlerts] = useState(ALERTS);
  const [processingState, setProcessingState] = useState(null);
  const [mapLayer, setMapLayer] = useState('dark');
  const [liveMode, setLiveMode] = useState(true);
  const [backendStatus, setBackendStatus] = useState('connecting');
  const [vesselList, setVesselList] = useState(VESSELS);
  const [spillList, setSpillList] = useState(SPILLS);

  // Initial Backend Health Check & WebSocket setup
  useEffect(() => {
    checkBackendHealth().then(status => {
      setBackendStatus(status.status);
    });

    const ws = subscribeAlertWebSocket(
      (newAlert) => {
        if (liveMode) {
          setAlerts(prev => [newAlert, ...prev.slice(0, 19)]);
        }
      },
      (initialAlerts) => {
        if (initialAlerts && initialAlerts.length > 0) {
          setAlerts(initialAlerts);
        }
      }
    );

    return () => {
      if (ws) ws.close();
    };
  }, [liveMode]);

  const handleSARUpload = async (file) => {
    setProcessingState('uploading');
    const t1 = setTimeout(() => setProcessingState('preprocessing'), 800);
    const t2 = setTimeout(() => setProcessingState('inference'), 1800);
    const t3 = setTimeout(() => setProcessingState('correlating'), 3000);

    try {
      const res = await triggerSARAnalysis(file);
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);

      if (res.success && res.spill) {
        setSpillList(prev => [res.spill, ...prev]);
        setSelectedSpill(res.spill);

        // Fetch attribution for newly detected spill
        try {
          const vessels = await fetchVesselAttribution(
            res.spill.id,
            res.spill.center[0],
            res.spill.center[1],
            res.spill.timestamp
          );
          if (vessels && vessels.length > 0) {
            setVesselList(prev => [...vessels, ...prev]);
          }
        } catch (e) {
          console.warn('Attribution fetch error:', e);
        }
      }
    } catch (err) {
      console.warn('Analysis error:', err);
    } finally {
      setProcessingState('complete');
    }
  };

  const handleSpillSelect = (spill) => {
    setSelectedSpill(spill);
    setSelectedVessel(null);
  };

  const handleVesselSelect = (vessel) => {
    setSelectedVessel(vessel);
  };

  const getSpillVessels = (spill) => {
    if (!spill) return [];
    return vesselList.filter(v => v.spill_id === spill.id)
      .sort((a, b) => b.attribution_score - a.attribution_score);
  };

  return (
    <div className="app-layout">
      <Header
        stats={SYSTEM_STATS}
        liveMode={liveMode}
        onToggleLive={() => setLiveMode(p => !p)}
        onAnalytics={() => setShowAnalytics(true)}
        alerts={alerts}
      />

      <LeftSidebar
        spills={spillList}
        selectedSpill={selectedSpill}
        onSpillSelect={handleSpillSelect}
        processingState={processingState}
        onSARUpload={handleSARUpload}
      />

      <MapView
        spills={spillList}
        vessels={vesselList}
        selectedSpill={selectedSpill}
        selectedVessel={selectedVessel}
        onSpillSelect={handleSpillSelect}
        onVesselSelect={handleVesselSelect}
        mapLayer={mapLayer}
        onMapLayerChange={setMapLayer}
      />

      <RightSidebar
        vessels={getSpillVessels(selectedSpill)}
        selectedVessel={selectedVessel}
        selectedSpill={selectedSpill}
        alerts={alerts}
        onVesselSelect={handleVesselSelect}
        onAlertAck={(id) =>
          setAlerts(prev =>
            prev.map(a => a.id === id ? { ...a, acknowledged: true } : a)
          )
        }
      />

      {showAnalytics && (
        <AnalyticsModal onClose={() => setShowAnalytics(false)} />
      )}
    </div>
  );
}
