"""
OceanGuard — Pydantic Schemas
================================
SIH PS 26143 | NTRO
Request/Response models for all API endpoints.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ─── SPILL SCHEMAS ────────────────────────────────────────────────────────────

class SpillDetectionRequest(BaseModel):
    """Request body for manual SAR analysis trigger."""
    region: Optional[str] = "Bay of Bengal"
    timestamp: Optional[str] = None          # ISO8601, defaults to now
    demo_mode: bool = False                   # Use pre-baked demo data


class SpillPolygon(BaseModel):
    coordinates: List[List[float]]            # [[lat, lon], ...]
    type: str = "Polygon"


class SpillDetection(BaseModel):
    id: str
    timestamp: str
    confidence: float = Field(..., ge=0, le=100)
    area_km2: float
    severity: str                             # critical | high | medium | low
    status: str                               # active | monitoring | resolved
    center: List[float]                       # [lat, lon]
    polygon: List[List[float]]
    sar_image_id: str
    region: str
    oil_type_estimate: str
    thickness_estimate: str
    drift_direction: str
    wind_speed_ms: float
    suspects: List[str] = []
    top_vessel_confidence: float = 0.0
    processing_time_ms: Optional[float] = None


class DetectionResponse(BaseModel):
    success: bool
    spill: Optional[SpillDetection] = None
    message: str = ""
    processing_steps: List[str] = []


# ─── VESSEL / AIS SCHEMAS ────────────────────────────────────────────────────

class EvidenceBreakdown(BaseModel):
    proximity_score: float      # 0-100
    speed_anomaly: float        # 0-100
    heading_deviation: float    # 0-100
    ais_gap_minutes: float      # minutes of AIS silence
    vessel_type_weight: float   # 0-100


class VesselAttribution(BaseModel):
    mmsi: str
    imo: str
    name: str
    type: str
    flag: str
    flag_code: str
    dwt: int
    call_sign: str
    owner: str
    last_port: str
    destination: str
    attribution_score: float    # 0-100 final weighted score
    suspicion_level: str        # critical | high | medium | low
    evidence: EvidenceBreakdown
    track: List[List[float]]    # AIS track [[lat, lon], ...]
    speed_profile: List[float]
    current_speed: float
    current_heading: float
    spill_id: str
    color: str


class AttributionResponse(BaseModel):
    spill_id: str
    vessels: List[VesselAttribution]
    algorithm_version: str = "1.0"
    total_candidates_evaluated: int = 0
    processing_time_ms: float = 0.0


# ─── AIS SCHEMAS ─────────────────────────────────────────────────────────────

class AISRecord(BaseModel):
    mmsi: str
    timestamp: str
    lat: float
    lon: float
    sog: float                  # Speed over ground (knots)
    cog: float                  # Course over ground (degrees)
    vessel_type: Optional[int] = None
    vessel_name: Optional[str] = None
    length: Optional[float] = None


class AISQueryParams(BaseModel):
    lat: float
    lon: float
    radius_km: float = 50.0
    hours_before: float = 6.0
    hours_after: float = 1.0
    spill_timestamp: Optional[str] = None


# ─── ALERT SCHEMAS ────────────────────────────────────────────────────────────

class Alert(BaseModel):
    id: str
    type: str                   # critical | high | medium | info
    title: str
    message: str
    timestamp: str
    spill_id: Optional[str] = None
    vessel_id: Optional[str] = None
    acknowledged: bool = False


class AlertAckRequest(BaseModel):
    alert_ids: List[str]


# ─── PIPELINE SCHEMAS ─────────────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    """Full end-to-end: SAR + AIS → Attribution Report"""
    demo_mode: bool = True
    region: str = "Bay of Bengal"
    spill_timestamp: Optional[str] = None


class PipelineResponse(BaseModel):
    success: bool
    spill: Optional[SpillDetection] = None
    attribution: Optional[AttributionResponse] = None
    alerts_generated: int = 0
    total_time_ms: float = 0.0
    message: str = ""


# ─── HEALTH SCHEMA ────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    ais_records_indexed: int
    active_spills: int
    version: str = "1.0.0"
    uptime_seconds: float
