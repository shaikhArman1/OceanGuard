/**
 * OceanGuard — Frontend API Client
 * SIH PS 26143 | NTRO
 * 
 * Interacts with FastAPI backend (http://localhost:8000/api)
 * Automatically falls back to synthetic mock data if backend is offline.
 */

import axios from 'axios';
import { SPILLS, VESSELS, ALERTS, SYSTEM_STATS } from '../data/mockData';

const API_BASE = 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function checkBackendHealth() {
  try {
    const res = await api.get('/health');
    return res.data;
  } catch (err) {
    console.warn('⚠️ Backend offline or unreachable. Using standalone mock data mode.');
    return { status: 'mock_mode', model_loaded: false, active_spills: 3 };
  }
}

export async function triggerSARAnalysis(file = null, lat = 14.5204, lon = 76.3210) {
  try {
    const formData = new FormData();
    if (file) {
      formData.append('file', file);
      formData.append('demo_mode', 'false');
    } else {
      formData.append('demo_mode', 'true');
    }
    formData.append('lat', lat);
    formData.append('lon', lon);

    const res = await axios.post(`${API_BASE}/detect`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
    return res.data;
  } catch (err) {
    console.warn('Fallback to local mock detection:', err.message);
    return {
      success: true,
      spill: SPILLS[0],
      message: 'Demo detection (Offline mode)',
      processing_steps: [
        'Ingested SAR C-Band Scene',
        'Lee Speckle Filter (7x7)',
        'Sigma-nought dB Normalization',
        'U-Net Segmentation Pass',
        'Polygon Georeferencing'
      ]
    };
  }
}

export async function fetchVesselAttribution(spillId, lat, lon, timestamp) {
  try {
    const res = await api.get(`/attribution/${spillId}`, {
      params: { lat, lon, timestamp }
    });
    return res.data.vessels;
  } catch (err) {
    console.warn('Fallback to local mock attribution:', err.message);
    return VESSELS;
  }
}

export async function fetchSystemAlerts() {
  try {
    const res = await api.get('/alerts');
    return res.data;
  } catch (err) {
    return ALERTS;
  }
}

export async function acknowledgeAlerts(alertIds) {
  try {
    const res = await api.post('/alerts/ack', { alert_ids: alertIds });
    return res.data;
  } catch (err) {
    return { success: true, acknowledged_count: alertIds.length };
  }
}

export function subscribeAlertWebSocket(onNewAlert, onInit) {
  try {
    const ws = new WebSocket('ws://localhost:8000/ws/alerts');

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'INIT' && onInit) {
          onInit(data.alerts);
        } else if (data.event === 'NEW_ALERT' && onNewAlert) {
          onNewAlert(data.alert);
        }
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };

    ws.onerror = (err) => {
      console.warn('WebSocket connection error (mock ticker active):', err);
    };

    return ws;
  } catch (err) {
    return null;
  }
}
