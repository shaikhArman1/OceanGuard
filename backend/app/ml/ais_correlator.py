"""
OceanGuard — AIS Correlation & Vessel Attribution Engine
==========================================================
SIH PS 26143 | NTRO

THE NOVEL ALGORITHM — This is what makes OceanGuard unique.

Given a detected oil spill (location + timestamp from SAR),
this engine identifies and scores ALL vessels that were in
the vicinity at the time of the spill, ranking them by
probability of being responsible.

Attribution Score Formula:
─────────────────────────────────────────────────────────
  score(vessel, spill) =
      w1 × proximity_score        (35%)
    + w2 × speed_anomaly_score    (25%)
    + w3 × ais_gap_score          (20%)
    + w4 × heading_deviation_score(15%)
    + w5 × vessel_type_weight     (5%)

All component scores ∈ [0, 100].
Final score ∈ [0, 100].

Why these weights?
  - Proximity (35%): Nearest vessel is most likely responsible
  - Speed anomaly (25%): Stopping to discharge is a strong signal
  - AIS gap (20%): Going dark is extremely suspicious
  - Heading deviation (15%): Abrupt course change = evasion
  - Vessel type (5%): Tankers carry oil; bulk carriers less so
─────────────────────────────────────────────────────────
"""

import math
import json
import csv
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


# ─── WEIGHTS (tunable) ───────────────────────────────────────────────────────

WEIGHTS = {
    "proximity":   0.35,
    "speed":       0.25,
    "ais_gap":     0.20,
    "heading":     0.15,
    "vessel_type": 0.05,
}

# Vessel type suspicion weights (0-100)
# IMO vessel type codes → base suspicion weight
VESSEL_TYPE_WEIGHTS = {
    80: 90,   # Crude Oil Tanker
    81: 85,   # Petroleum/Products Tanker
    82: 80,   # Chemical/Oil Tanker
    83: 75,   # Combination Carrier
    84: 70,   # Other Tanker
    70: 55,   # Bulk Carrier
    71: 50,   # Bulk Carrier (Hazmat)
    72: 45,   # Bulk Carrier
    60: 30,   # Passenger Ship
    30: 20,   # Fishing Vessel
    0: 40,    # Unknown
}

# Search parameters
SEARCH_RADIUS_KM  = 75.0     # Search radius around spill centroid
HOURS_BEFORE_SPILL = 6.0     # How far before SAR acquisition to look
HOURS_AFTER_SPILL  = 1.0     # How far after (uncertainty buffer)
MIN_SCORE_TO_REPORT = 20.0   # Don't report vessels with score below this


# ─── DATA CLASSES ────────────────────────────────────────────────────────────

@dataclass
class AISPoint:
    """Single AIS position fix."""
    mmsi: str
    timestamp: datetime
    lat: float
    lon: float
    sog: float           # Speed over ground (knots)
    cog: float           # Course over ground (degrees)
    vessel_type: int = 0
    vessel_name: str = ""


@dataclass
class VesselTrack:
    """Complete AIS track for one vessel."""
    mmsi: str
    vessel_name: str
    vessel_type: int
    points: List[AISPoint] = field(default_factory=list)

    def speed_at_time(self, t: datetime) -> Optional[float]:
        """Interpolate speed at a given time."""
        if not self.points:
            return None
        closest = min(self.points, key=lambda p: abs((p.timestamp - t).total_seconds()))
        return closest.sog

    def position_at_time(self, t: datetime) -> Optional[Tuple[float, float]]:
        """Interpolate position at a given time."""
        if not self.points:
            return None
        before = [p for p in self.points if p.timestamp <= t]
        after  = [p for p in self.points if p.timestamp > t]
        if before and after:
            p0, p1 = before[-1], after[0]
            total  = (p1.timestamp - p0.timestamp).total_seconds()
            frac   = (t - p0.timestamp).total_seconds() / max(total, 1)
            lat = p0.lat + (p1.lat - p0.lat) * frac
            lon = p0.lon + (p1.lon - p0.lon) * frac
            return lat, lon
        if before:
            return before[-1].lat, before[-1].lon
        return after[0].lat, after[0].lon

    def ais_gap_minutes(self, spill_time: datetime,
                        window_hours: float = 3.0) -> float:
        """
        Find the longest AIS silence gap within a time window around the spill.
        A large gap near the spill = high suspicion.
        """
        window_start = spill_time - timedelta(hours=window_hours)
        window_end   = spill_time + timedelta(hours=1)

        pts_in_window = sorted(
            [p for p in self.points if window_start <= p.timestamp <= window_end],
            key=lambda p: p.timestamp
        )

        if len(pts_in_window) < 2:
            return 0.0

        max_gap = 0.0
        for i in range(len(pts_in_window) - 1):
            gap = (pts_in_window[i+1].timestamp - pts_in_window[i].timestamp).total_seconds() / 60
            max_gap = max(max_gap, gap)

        # Normal AIS reporting interval is 2-10 minutes for moving vessels
        expected_interval = 10.0
        suspicious_gap    = max(0.0, max_gap - expected_interval)
        return round(suspicious_gap, 1)

    def speed_anomaly_score_near(self, spill_lat: float, spill_lon: float,
                                  spill_time: datetime, radius_km: float = 20) -> float:
        """
        Detect speed drop anomaly within radius_km of spill.
        Ships often slow to near-stop when discharging illegally.

        Score 0-100: 100 = stopped exactly at spill location
        """
        nearby_pts = [
            p for p in self.points
            if haversine_km(p.lat, p.lon, spill_lat, spill_lon) <= radius_km
        ]
        if not nearby_pts:
            return 0.0

        speeds = [p.sog for p in nearby_pts]
        if not speeds:
            return 0.0

        min_speed = min(speeds)
        avg_speed = sum(speeds) / len(speeds)

        # Get vessel's normal cruising speed (average outside radius)
        far_pts   = [
            p for p in self.points
            if haversine_km(p.lat, p.lon, spill_lat, spill_lon) > radius_km
        ]
        normal_speed = sum(p.sog for p in far_pts) / max(len(far_pts), 1) if far_pts else 10.0

        # Anomaly = how much vessel slowed relative to normal
        if normal_speed < 0.5:
            return 0.0  # Vessel was always slow

        slowdown_ratio = 1.0 - (min_speed / normal_speed)  # 0-1
        score = min(100.0, slowdown_ratio * 120)
        return round(score, 1)

    def heading_deviation_near(self, spill_lat: float, spill_lon: float,
                                radius_km: float = 30) -> float:
        """
        Detect abrupt heading change near spill area.
        Evasive maneuvers after illegal discharge = high deviation score.

        Score 0-100.
        """
        nearby_pts = sorted(
            [p for p in self.points
             if haversine_km(p.lat, p.lon, spill_lat, spill_lon) <= radius_km],
            key=lambda p: p.timestamp
        )

        if len(nearby_pts) < 3:
            return 0.0

        max_deviation = 0.0
        for i in range(1, len(nearby_pts) - 1):
            prev_hdg = nearby_pts[i-1].cog
            curr_hdg = nearby_pts[i].cog
            diff     = abs(curr_hdg - prev_hdg)
            if diff > 180:
                diff = 360 - diff
            max_deviation = max(max_deviation, diff)

        # Normalize: deviation > 45° is very suspicious, > 90° = extreme
        score = min(100.0, (max_deviation / 90.0) * 80)
        return round(score, 1)


# ─── HAVERSINE ───────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0, a)))


# ─── AIS PARSER ──────────────────────────────────────────────────────────────

def parse_ais_csv(csv_path: Path) -> Dict[str, VesselTrack]:
    """
    Parse AIS CSV data (MarineCadastre format) into VesselTrack objects.
    Supports both real MarineCadastre and our synthetic AIS format.
    """
    tracks: Dict[str, VesselTrack] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers_lower = {h.lower(): h for h in reader.fieldnames or []}

        def get(row, *keys):
            for k in keys:
                v = row.get(headers_lower.get(k, k), "")
                if v not in ("", None):
                    return v
            return ""

        for row in reader:
            mmsi = str(get(row, "mmsi", "MMSI")).strip()
            if not mmsi:
                continue

            try:
                raw_ts = get(row, "timestamp", "BaseDateTime", "time")
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                lat = float(get(row, "lat", "LAT", "Latitude"))
                lon = float(get(row, "lon", "LON", "Longitude"))
                sog = float(get(row, "sog", "SOG") or 0)
                cog = float(get(row, "cog", "COG") or 0)

                vtype_raw = get(row, "vessel_type", "VesselType", "type_code")
                vtype = int(float(vtype_raw)) if vtype_raw else 0

                vname = get(row, "vessel_name", "VesselName", "Name", "name")

            except (ValueError, KeyError):
                continue

            if mmsi not in tracks:
                tracks[mmsi] = VesselTrack(mmsi=mmsi, vessel_name=vname,
                                           vessel_type=vtype)

            tracks[mmsi].points.append(AISPoint(
                mmsi=mmsi, timestamp=ts,
                lat=lat, lon=lon,
                sog=sog, cog=cog,
                vessel_type=vtype, vessel_name=vname
            ))

    # Sort each track by time
    for track in tracks.values():
        track.points.sort(key=lambda p: p.timestamp)

    return tracks


def parse_ais_json(json_path: Path) -> Dict[str, VesselTrack]:
    """Parse our synthetic AIS scenario JSON."""
    with open(json_path) as f:
        scenario = json.load(f)

    tracks: Dict[str, VesselTrack] = {}

    for vessel in scenario.get("vessels", []):
        mmsi  = vessel["mmsi"]
        vtype = vessel.get("type_code", 0)
        vname = vessel.get("name", "")

        track = VesselTrack(mmsi=mmsi, vessel_name=vname, vessel_type=vtype)

        track_coords = vessel.get("track", [])
        speed_profile = vessel.get("speed_profile", [])

        for i, (lat, lon) in enumerate(track_coords):
            # Estimate timestamp from track index
            ts = datetime.fromisoformat(
                scenario["spill_timestamp"].replace("Z", "+00:00")
            ) - timedelta(hours=8) + timedelta(minutes=i * 15)

            spd = speed_profile[i] if i < len(speed_profile) else 10.0
            track.points.append(AISPoint(
                mmsi=mmsi, timestamp=ts,
                lat=lat, lon=lon,
                sog=spd, cog=45.0,
                vessel_type=vtype, vessel_name=vname
            ))

        tracks[mmsi] = track

    return tracks


# ─── ATTRIBUTION ENGINE ──────────────────────────────────────────────────────

class AISCorrelator:
    """
    Core vessel attribution engine.

    Uses a weighted multi-factor scoring algorithm to identify
    which vessel(s) are most likely responsible for a detected oil spill.
    """

    def __init__(self):
        self.tracks: Dict[str, VesselTrack] = {}
        self.vessel_meta: Dict[str, Dict] = {}
        self.indexed = False

    def load_ais_data(self, data_path: Path):
        """Load AIS data from CSV or JSON file."""
        data_path = Path(data_path)
        if not data_path.exists():
            raise FileNotFoundError(f"AIS data not found: {data_path}")

        if data_path.suffix == ".csv":
            self.tracks = parse_ais_csv(data_path)
        elif data_path.suffix == ".json":
            self.tracks = parse_ais_json(data_path)
        else:
            raise ValueError(f"Unsupported AIS format: {data_path.suffix}")

        self.indexed = True
        print(f"✅ Loaded {len(self.tracks)} vessel tracks ({sum(len(t.points) for t in self.tracks.values())} AIS records)")

    def load_vessel_metadata(self, meta_path: Path):
        """Load vessel registry metadata (owner, DWT, flag, etc.)."""
        if Path(meta_path).exists():
            with open(meta_path) as f:
                self.vessel_meta = json.load(f)

    def _get_vessels_in_radius(self,
                                spill_lat: float, spill_lon: float,
                                spill_time: datetime,
                                radius_km: float = SEARCH_RADIUS_KM,
                                hours_before: float = HOURS_BEFORE_SPILL,
                                hours_after: float = HOURS_AFTER_SPILL
                                ) -> List[Tuple[str, VesselTrack, float]]:
        """
        Find all vessels within radius_km of the spill within the time window.

        Returns: list of (mmsi, track, min_distance_km)
        """
        window_start = spill_time - timedelta(hours=hours_before)
        window_end   = spill_time + timedelta(hours=hours_after)
        candidates   = []

        for mmsi, track in self.tracks.items():
            # Filter points in time window
            window_pts = [
                p for p in track.points
                if window_start <= p.timestamp <= window_end
            ]
            if not window_pts:
                continue

            # Find minimum distance to spill during window
            min_dist = min(
                haversine_km(p.lat, p.lon, spill_lat, spill_lon)
                for p in window_pts
            )
            if min_dist <= radius_km:
                candidates.append((mmsi, track, min_dist))

        # Sort by proximity (closest first)
        candidates.sort(key=lambda x: x[2])
        return candidates

    def _proximity_score(self, min_dist_km: float,
                          radius_km: float = SEARCH_RADIUS_KM) -> float:
        """
        Score based on minimum distance to spill.
        Exponential decay: distance 0 → score 100, distance=radius → score ~5.
        """
        if min_dist_km <= 0:
            return 100.0
        score = 100.0 * math.exp(-3.5 * min_dist_km / radius_km)
        return round(max(0, score), 1)

    def _ais_gap_score(self, gap_minutes: float) -> float:
        """
        Score AIS transponder silence gap.
        Normal variation (< 10 min): score 0
        Suspicious (30+ min): score climbs to 95
        """
        if gap_minutes <= 10:
            return 0.0
        # Logarithmic scale: 30 min → ~60, 60 min → ~80, 120+ min → ~95
        score = min(95.0, 60.0 * math.log(gap_minutes / 10.0 + 1) / math.log(13))
        return round(score, 1)

    def attribute(self,
                  spill_lat: float,
                  spill_lon: float,
                  spill_time: datetime,
                  spill_id: str,
                  radius_km: float = SEARCH_RADIUS_KM) -> List[Dict]:
        """
        Run full attribution algorithm for a detected spill.

        Returns:
            Ranked list of vessel attribution dicts with scores and evidence.
        """
        if not self.indexed or not self.tracks:
            return []

        # Step 1: Find candidate vessels in radius + time window
        candidates = self._get_vessels_in_radius(
            spill_lat, spill_lon, spill_time, radius_km
        )

        if not candidates:
            return []

        results = []

        for mmsi, track, min_dist_km in candidates:
            meta = self.vessel_meta.get(mmsi, {})

            # ── Component Scores ────────────────────────────────────────────

            # 1. Proximity score
            prox_score = self._proximity_score(min_dist_km, radius_km)

            # 2. Speed anomaly score
            speed_score = track.speed_anomaly_score_near(
                spill_lat, spill_lon, spill_time, radius_km=min(radius_km, 25)
            )

            # 3. AIS gap score
            gap_minutes = track.ais_gap_minutes(spill_time, window_hours=4.0)
            gap_score   = self._ais_gap_score(gap_minutes)

            # 4. Heading deviation score
            hdg_score = track.heading_deviation_near(
                spill_lat, spill_lon, radius_km=min(radius_km, 30)
            )

            # 5. Vessel type weight
            vtype_code   = track.vessel_type
            vtype_weight = VESSEL_TYPE_WEIGHTS.get(vtype_code, 40)

            # ── Final Weighted Score ─────────────────────────────────────────
            final_score = (
                WEIGHTS["proximity"]   * prox_score
              + WEIGHTS["speed"]       * speed_score
              + WEIGHTS["ais_gap"]     * gap_score
              + WEIGHTS["heading"]     * hdg_score
              + WEIGHTS["vessel_type"] * vtype_weight
            )
            final_score = round(min(100.0, final_score), 1)

            if final_score < MIN_SCORE_TO_REPORT:
                continue

            # ── Suspicion Level ──────────────────────────────────────────────
            if final_score >= 80:
                suspicion = "critical"
            elif final_score >= 60:
                suspicion = "high"
            elif final_score >= 40:
                suspicion = "medium"
            else:
                suspicion = "low"

            # ── Get last known position ──────────────────────────────────────
            last_pt = track.points[-1] if track.points else None
            current_speed   = last_pt.sog if last_pt else 0
            current_heading = last_pt.cog if last_pt else 0

            # ── Build result dict ────────────────────────────────────────────
            results.append({
                "mmsi":              mmsi,
                "imo":               meta.get("imo", f"VS-{mmsi}"),
                "name":              track.vessel_name or meta.get("name", f"VESSEL-{mmsi}"),
                "type":              meta.get("type", "Unknown Vessel"),
                "flag":              meta.get("flag", "Unknown"),
                "flag_code":         meta.get("flag_code", "XX"),
                "dwt":               meta.get("dwt", 0),
                "call_sign":         meta.get("call_sign", ""),
                "owner":             meta.get("owner", "Unknown"),
                "last_port":         meta.get("last_port", "Unknown"),
                "destination":       meta.get("destination", "Unknown"),
                "attribution_score": final_score,
                "suspicion_level":   suspicion,
                "evidence": {
                    "proximity_score":   prox_score,
                    "speed_anomaly":     speed_score,
                    "heading_deviation": hdg_score,
                    "ais_gap_minutes":   gap_minutes,
                    "vessel_type_weight": vtype_weight
                },
                "track":           [[p.lat, p.lon] for p in track.points],
                "speed_profile":   [p.sog for p in track.points[::3]],
                "current_speed":   round(current_speed, 1),
                "current_heading": round(current_heading, 1),
                "spill_id":        spill_id,
                "color": "#ff3a4e" if suspicion == "critical" else "#ff8c00"
            })

        # Sort by attribution score descending
        results.sort(key=lambda x: x["attribution_score"], reverse=True)
        return results
