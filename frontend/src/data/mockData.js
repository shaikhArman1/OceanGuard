// ============================================================
// MOCK DATA FOR DEMO / PPT PURPOSES
// OceanGuard — SIH PS 26143
// ============================================================

export const SPILLS = [
  {
    id: "SPILL-2024-001",
    timestamp: "2024-11-14T03:21:00Z",
    confidence: 94.7,
    area_km2: 12.4,
    severity: "critical",
    status: "active",
    center: [14.5204, 76.3210],
    polygon: [
      [14.48, 76.28], [14.49, 76.31], [14.51, 76.35],
      [14.54, 76.38], [14.56, 76.36], [14.55, 76.32],
      [14.53, 76.28], [14.50, 76.26], [14.48, 76.28]
    ],
    sar_image_id: "S1A_IW_SLC__1SDV_20241114T032100",
    suspects: ["VS-IMO-9234567", "VS-IMO-8876543"],
    top_vessel_confidence: 89.2,
    region: "Bay of Bengal",
    oil_type_estimate: "Crude Oil",
    thickness_estimate: "0.1-0.5mm",
    drift_direction: "NE",
    wind_speed_ms: 4.2
  },
  {
    id: "SPILL-2024-002",
    timestamp: "2024-11-13T18:45:00Z",
    confidence: 87.3,
    area_km2: 5.8,
    severity: "high",
    status: "monitoring",
    center: [10.8505, 79.8083],
    polygon: [
      [10.82, 79.77], [10.83, 79.80], [10.85, 79.83],
      [10.87, 79.85], [10.88, 79.83], [10.87, 79.80],
      [10.85, 79.78], [10.83, 79.76], [10.82, 79.77]
    ],
    sar_image_id: "S1A_IW_SLC__1SDV_20241113T184500",
    suspects: ["VS-IMO-7543210"],
    top_vessel_confidence: 76.5,
    region: "Palk Strait",
    oil_type_estimate: "Diesel / Bunker Fuel",
    thickness_estimate: "0.01-0.1mm",
    drift_direction: "SW",
    wind_speed_ms: 6.8
  },
  {
    id: "SPILL-2024-003",
    timestamp: "2024-11-12T09:10:00Z",
    confidence: 71.8,
    area_km2: 3.2,
    severity: "medium",
    status: "resolved",
    center: [18.9750, 72.8258],
    polygon: [
      [18.96, 72.80], [18.97, 72.82], [18.98, 72.84],
      [18.99, 72.83], [18.98, 72.81], [18.97, 72.79],
      [18.96, 72.80]
    ],
    sar_image_id: "S1A_IW_SLC__1SDV_20241112T091000",
    suspects: ["VS-IMO-6654321"],
    top_vessel_confidence: 62.1,
    region: "Arabian Sea",
    oil_type_estimate: "Unknown Petroleum",
    thickness_estimate: "0.01-0.05mm",
    drift_direction: "N",
    wind_speed_ms: 8.1
  }
];

export const VESSELS = [
  {
    mmsi: "419000123",
    imo: "VS-IMO-9234567",
    name: "MV KALPANA CHAWLA",
    type: "Crude Oil Tanker",
    flag: "India",
    flag_code: "IN",
    dwt: 105000,
    call_sign: "VTAK7",
    owner: "ONGC Shipping Ltd.",
    last_port: "Paradip, India",
    destination: "Haldia, India",
    attribution_score: 89.2,
    suspicion_level: "critical",
    evidence: {
      proximity_score: 95,
      speed_anomaly: 88,
      heading_deviation: 82,
      ais_gap_minutes: 47,
      vessel_type_weight: 90
    },
    track: [
      [14.42, 76.18], [14.44, 76.21], [14.47, 76.24],
      [14.50, 76.29], [14.52, 76.33],
      [14.51, 76.38], [14.53, 76.42], [14.55, 76.45]
    ],
    speed_profile: [12.4, 11.8, 10.2, 2.1, 0.4, 0.3, 8.2, 11.5],
    current_speed: 11.5,
    current_heading: 47,
    spill_id: "SPILL-2024-001",
    color: "#ff4757"
  },
  {
    mmsi: "636012345",
    imo: "VS-IMO-8876543",
    name: "MT POSEIDON STAR",
    type: "Product Tanker",
    flag: "Liberia",
    flag_code: "LR",
    dwt: 48000,
    call_sign: "A8KL2",
    owner: "Oceanic Freight Corp.",
    last_port: "Colombo, Sri Lanka",
    destination: "Chennai, India",
    attribution_score: 45.6,
    suspicion_level: "medium",
    evidence: {
      proximity_score: 58,
      speed_anomaly: 42,
      heading_deviation: 38,
      ais_gap_minutes: 12,
      vessel_type_weight: 80
    },
    track: [
      [14.38, 76.40], [14.41, 76.39], [14.44, 76.38],
      [14.48, 76.36], [14.52, 76.34],
      [14.55, 76.32], [14.58, 76.31]
    ],
    speed_profile: [14.2, 14.0, 13.8, 13.5, 13.9, 14.1, 14.3, 14.0],
    current_speed: 14.0,
    current_heading: 312,
    spill_id: "SPILL-2024-001",
    color: "#ffa502"
  },
  {
    mmsi: "345678901",
    imo: "VS-IMO-7543210",
    name: "MV OCEAN PIONEER",
    type: "Bulk Carrier",
    flag: "Panama",
    flag_code: "PA",
    dwt: 75000,
    call_sign: "3EBD5",
    owner: "Global Maritime PLC",
    last_port: "Singapore",
    destination: "Tuticorin, India",
    attribution_score: 76.5,
    suspicion_level: "high",
    evidence: {
      proximity_score: 82,
      speed_anomaly: 74,
      heading_deviation: 55,
      ais_gap_minutes: 31,
      vessel_type_weight: 60
    },
    track: [
      [10.78, 79.72], [10.80, 79.75], [10.82, 79.78],
      [10.84, 79.81], [10.85, 79.84],
      [10.87, 79.87], [10.89, 79.90]
    ],
    speed_profile: [10.2, 9.8, 8.5, 1.2, 0.8, 7.5, 10.0, 10.3],
    current_speed: 10.3,
    current_heading: 28,
    spill_id: "SPILL-2024-002",
    color: "#ffa502"
  },
  {
    mmsi: "212456789",
    imo: "VS-IMO-6654321",
    name: "MT ATLAS NAVIGATOR",
    type: "Chemical Tanker",
    flag: "Greece",
    flag_code: "GR",
    dwt: 22000,
    call_sign: "SYQR4",
    owner: "Hellenic Shipping Ltd.",
    last_port: "Dubai, UAE",
    destination: "Mumbai, India",
    attribution_score: 62.1,
    suspicion_level: "high",
    evidence: {
      proximity_score: 70,
      speed_anomaly: 58,
      heading_deviation: 62,
      ais_gap_minutes: 19,
      vessel_type_weight: 75
    },
    track: [
      [18.93, 72.76], [18.95, 72.78], [18.97, 72.80],
      [18.98, 72.82], [18.99, 72.84],
      [19.01, 72.86]
    ],
    speed_profile: [8.5, 8.2, 7.8, 3.2, 1.1, 7.9, 8.4, 8.6],
    current_speed: 8.6,
    current_heading: 195,
    spill_id: "SPILL-2024-003",
    color: "#ffa502"
  }
];

export const ALERTS = [
  {
    id: "ALT-001",
    type: "critical",
    title: "New Oil Spill Detected",
    message: "SAR analysis detected 12.4 km² spill in Bay of Bengal. Vessel MV KALPANA CHAWLA identified as primary suspect (89.2% confidence).",
    timestamp: "2024-11-14T03:24:00Z",
    spill_id: "SPILL-2024-001",
    vessel_id: "VS-IMO-9234567",
    acknowledged: false
  },
  {
    id: "ALT-002",
    type: "high",
    title: "AIS Gap Detected — Suspicious",
    message: "MV KALPANA CHAWLA went AIS dark for 47 minutes at coordinates (14.50°N, 76.29°E) — matching spill origin point.",
    timestamp: "2024-11-14T02:37:00Z",
    spill_id: "SPILL-2024-001",
    vessel_id: "VS-IMO-9234567",
    acknowledged: false
  },
  {
    id: "ALT-003",
    type: "high",
    title: "Palk Strait Spill — Monitoring",
    message: "5.8 km² spill in Palk Strait (87.3% confidence). MV OCEAN PIONEER attribution at 76.5%. Indian Coast Guard notified.",
    timestamp: "2024-11-13T18:47:00Z",
    spill_id: "SPILL-2024-002",
    vessel_id: "VS-IMO-7543210",
    acknowledged: true
  },
  {
    id: "ALT-004",
    type: "medium",
    title: "Spill Resolved — Arabian Sea",
    message: "Arabian Sea spill (SPILL-2024-003) confirmed resolved. Cleanup operations completed. Attribution report filed.",
    timestamp: "2024-11-12T14:30:00Z",
    spill_id: "SPILL-2024-003",
    vessel_id: "VS-IMO-6654321",
    acknowledged: true
  },
  {
    id: "ALT-005",
    type: "info",
    title: "SAR Acquisition Scheduled",
    message: "Sentinel-1A pass over Bay of Bengal scheduled at 03:15 UTC. Auto-processing will begin immediately.",
    timestamp: "2024-11-14T02:15:00Z",
    spill_id: null,
    vessel_id: null,
    acknowledged: true
  }
];

export const MONTHLY_STATS = [
  { month: "Jun", spills: 3, vessels: 3, resolved: 2 },
  { month: "Jul", spills: 5, vessels: 5, resolved: 4 },
  { month: "Aug", spills: 4, vessels: 4, resolved: 3 },
  { month: "Sep", spills: 7, vessels: 6, resolved: 5 },
  { month: "Oct", spills: 6, vessels: 5, resolved: 6 },
  { month: "Nov", spills: 3, vessels: 4, resolved: 1 }
];

export const SYSTEM_STATS = {
  total_spills_detected: 28,
  vessels_identified: 22,
  response_time_avg_min: 18,
  sar_images_processed: 143,
  model_accuracy: 94.7,
  active_spills: 1,
  area_monitored_km2: 2400000,
  region: "Indian Ocean Region"
};
