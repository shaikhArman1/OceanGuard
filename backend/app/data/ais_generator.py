"""
OceanGuard — Synthetic AIS Data Generator
==========================================
SIH PS 26143 | NTRO

Generates realistic vessel AIS tracks for demo/testing purposes.
The PS explicitly allows synthetic data to demonstrate algorithm functioning.

Features:
  - Realistic great-circle vessel trajectories
  - Ship physics: speed, heading, acceleration limits
  - AIS gap injection (transponder off = suspicious behavior)
  - Speed anomaly injection (sudden slowdown near spill)
  - Multiple vessel types with correct speed profiles

Output: Standard AIS CSV compatible with MarineCadastre format
"""

import random
import math
import csv
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


# ─── VESSEL TYPE DEFINITIONS ─────────────────────────────────────────────────

VESSEL_TYPES = {
    "crude_tanker": {
        "type_code": 80,
        "name_prefix": ["MV", "MT"],
        "speed_range": (8, 16),    # knots
        "dwt_range": (80000, 150000),
        "length_range": (250, 330),
        "suspicion_weight": 0.90,  # More likely to cause oil spills
        "flag_pool": ["India", "Panama", "Liberia", "Marshall Islands", "Greece"]
    },
    "product_tanker": {
        "type_code": 81,
        "name_prefix": ["MT", "MV"],
        "speed_range": (10, 18),
        "dwt_range": (30000, 60000),
        "length_range": (170, 230),
        "suspicion_weight": 0.80,
        "flag_pool": ["India", "Singapore", "Liberia", "Panama"]
    },
    "chemical_tanker": {
        "type_code": 82,
        "name_prefix": ["MT", "MV"],
        "speed_range": (10, 16),
        "dwt_range": (15000, 40000),
        "length_range": (140, 200),
        "suspicion_weight": 0.75,
        "flag_pool": ["Greece", "Norway", "Singapore", "Italy"]
    },
    "bulk_carrier": {
        "type_code": 70,
        "name_prefix": ["MV", "MS"],
        "speed_range": (9, 14),
        "dwt_range": (50000, 120000),
        "length_range": (200, 300),
        "suspicion_weight": 0.55,
        "flag_pool": ["Panama", "Marshall Islands", "Bahamas", "China"]
    },
}

VESSEL_NAMES = [
    "KALPANA CHAWLA", "VIKRANT", "POSEIDON STAR", "OCEAN PIONEER",
    "ATLAS NAVIGATOR", "SEA FALCON", "GULF PRIDE", "INDUS SPIRIT",
    "ARABIAN SEA", "BAY GLORY", "MUMBAI STAR", "CHENNAI QUEEN",
    "EASTERN WIND", "PACIFIC HORIZON", "COASTAL DEFENDER", "DEEP OCEAN"
]

FLAG_CODES = {
    "India": "IN", "Panama": "PA", "Liberia": "LR",
    "Marshall Islands": "MH", "Greece": "GR", "Singapore": "SG",
    "Norway": "NO", "Bahamas": "BS", "Italy": "IT", "China": "CN"
}


# ─── GEOGRAPHY ────────────────────────────────────────────────────────────────

# Indian Ocean shipping lanes (approximate waypoints)
SHIPPING_LANES = {
    "bay_of_bengal": {
        "waypoints": [
            (9.0, 80.5),   # Sri Lanka coast
            (11.0, 80.0),  # Palk Strait
            (13.5, 80.0),  # Chennai
            (15.5, 81.5),  # Visakhapatnam
            (19.5, 86.5),  # Odisha
            (20.5, 87.0),  # Paradip
        ]
    },
    "arabian_sea": {
        "waypoints": [
            (22.5, 69.0),  # Kandla
            (19.1, 72.9),  # Mumbai
            (15.5, 73.9),  # Goa
            (11.9, 75.4),  # Mangalore
            (9.9,  76.2),  # Kochi
            (8.5,  77.0),  # Kerala
        ]
    },
    "indian_ocean": {
        "waypoints": [
            (1.0, 104.0),  # Singapore Strait
            (5.0, 94.0),   # Malacca outbound
            (8.0, 80.0),   # Sri Lanka
            (11.0, 65.0),  # Arabian Sea
            (20.0, 60.0),  # Gulf of Oman
        ]
    }
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Distance between two lat/lon points in km."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2) -> float:
    """Initial bearing from point 1 to point 2 (degrees)."""
    d_lon = math.radians(lon2 - lon1)
    x = math.sin(d_lon) * math.cos(math.radians(lat2))
    y = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(d_lon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def move_point(lat, lon, heading_deg, distance_km) -> tuple:
    """Move a point by distance_km in heading_deg direction."""
    R = 6371.0
    heading = math.radians(heading_deg)
    d_r = distance_km / R
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d_r)
        + math.cos(lat1) * math.sin(d_r) * math.cos(heading)
    )
    lon2 = lon1 + math.atan2(
        math.sin(heading) * math.sin(d_r) * math.cos(lat1),
        math.cos(d_r) - math.sin(lat1) * math.sin(lat2)
    )
    return math.degrees(lat2), math.degrees(lon2)


# ─── TRACK GENERATOR ─────────────────────────────────────────────────────────

def generate_vessel_track(
    start_lat: float, start_lon: float,
    end_lat: float,   end_lon: float,
    start_time: datetime,
    avg_speed_kts: float = 12.0,
    interval_minutes: int = 10,
    inject_ais_gap: bool = False,
    gap_at_fraction: float = 0.5,
    gap_duration_minutes: int = 45,
    inject_speed_drop: bool = False,
    drop_at_fraction: float = 0.5
) -> List[Dict]:
    """
    Generate a realistic AIS track from start to end point.

    Args:
        inject_ais_gap     : Simulate transponder off (suspicious)
        gap_at_fraction    : Position along route to start gap (0-1)
        gap_duration_minutes: How long AIS was silent
        inject_speed_drop  : Simulate vessel slowing down near spill
        drop_at_fraction   : Position along route for slowdown

    Returns:
        List of AIS records (dicts)
    """
    total_dist_km = haversine_km(start_lat, start_lon, end_lat, end_lon)
    speed_ms      = avg_speed_kts * 0.514444              # knots → m/s
    speed_kmh     = speed_ms * 3.6
    total_hours   = total_dist_km / speed_kmh
    total_minutes = total_hours * 60

    records = []
    current_time = start_time
    elapsed_min  = 0.0

    gap_start_min = gap_at_fraction * total_minutes
    gap_end_min   = gap_start_min + gap_duration_minutes
    drop_start_min = drop_at_fraction * total_minutes
    drop_end_min   = drop_start_min + 30  # slowdown lasts 30 minutes

    in_gap = False

    while elapsed_min <= total_minutes:
        fraction = min(elapsed_min / max(total_minutes, 1), 1.0)

        # Interpolate position along great circle (simplified linear)
        lat = start_lat + (end_lat - start_lat) * fraction
        lon = start_lon + (end_lon - start_lon) * fraction

        # Add realistic position noise
        lat += random.gauss(0, 0.001)
        lon += random.gauss(0, 0.001)

        # AIS gap — skip records in this window
        if inject_ais_gap and gap_start_min <= elapsed_min <= gap_end_min:
            elapsed_min += interval_minutes
            current_time += timedelta(minutes=interval_minutes)
            in_gap = True
            continue
        in_gap = False

        # Speed profile
        current_speed = avg_speed_kts
        if inject_speed_drop and drop_start_min <= elapsed_min <= drop_end_min:
            drop_progress = (elapsed_min - drop_start_min) / (drop_end_min - drop_start_min)
            # Slow down, pause, speed back up
            if drop_progress < 0.3:
                current_speed = avg_speed_kts * (1 - drop_progress * 2)
            elif drop_progress < 0.6:
                current_speed = random.uniform(0.1, 0.5)   # Nearly stopped
            else:
                current_speed = avg_speed_kts * (drop_progress - 0.6) * 3

        current_speed = max(0, current_speed + random.gauss(0, 0.3))

        # Heading
        hdg = bearing(start_lat, start_lon, end_lat, end_lon)
        hdg += random.gauss(0, 2)   # ±2° noise
        hdg = hdg % 360

        records.append({
            "timestamp":   current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat":         round(lat, 5),
            "lon":         round(lon, 5),
            "sog":         round(current_speed, 1),
            "cog":         round(hdg, 1),
            "elapsed_min": round(elapsed_min, 1)
        })

        elapsed_min  += interval_minutes
        current_time += timedelta(minutes=interval_minutes)

    return records


# ─── MAIN GENERATOR ──────────────────────────────────────────────────────────

def generate_synthetic_ais_scenario(
    spill_lat: float,
    spill_lon: float,
    spill_timestamp: datetime,
    n_vessels: int = 4,
    n_innocent: int = 2,
    output_dir: Optional[Path] = None
) -> Dict:
    """
    Generate a complete AIS scenario around a known spill event.

    Creates:
      - 1 PRIMARY SUSPECT vessel (high attribution evidence)
      - n_vessels-1 NEARBY vessels (medium/low evidence)
      - n_innocent INNOCENT vessels (passing through, no anomalies)

    Returns dict with vessel metadata and track data.
    """
    random.seed(42)   # Reproducible demo

    vessels  = []
    all_ais  = []
    scenario_start = spill_timestamp - timedelta(hours=8)

    # ── PRIMARY SUSPECT ──────────────────────────────────────────────────────

    vtype_key  = "crude_tanker"
    vtype      = VESSEL_TYPES[vtype_key]
    avg_speed  = random.uniform(*vtype["speed_range"])

    # Start ~200 km before spill, end ~100 km after
    start_lat = spill_lat - 1.8
    start_lon = spill_lon - 2.0
    end_lat   = spill_lat + 1.2
    end_lon   = spill_lon + 1.5

    track = generate_vessel_track(
        start_lat, start_lon, end_lat, end_lon,
        scenario_start, avg_speed,
        inject_ais_gap=True,
        gap_at_fraction=0.55,
        gap_duration_minutes=47,        # 47-minute dark period at spill location
        inject_speed_drop=True,
        drop_at_fraction=0.52
    )

    fleet_name = "KALPANA CHAWLA"
    flag       = "India"
    mmsi       = "419000123"

    suspect = {
        "mmsi": mmsi,
        "imo":  "VS-IMO-9234567",
        "name": f"MV {fleet_name}",
        "type": "Crude Oil Tanker",
        "type_code": vtype["type_code"],
        "flag": flag,
        "flag_code": FLAG_CODES.get(flag, "XX"),
        "dwt": random.randint(*vtype["dwt_range"]),
        "call_sign": "VTAK7",
        "owner": "ONGC Shipping Ltd.",
        "last_port": "Paradip, India",
        "destination": "Haldia, India",
        "is_suspect": True,
        "ais_gap_minutes": 47,
        "track": [[r["lat"], r["lon"]] for r in track],
        "speed_profile": [r["sog"] for r in track[::3]],
        "current_speed": track[-1]["sog"] if track else avg_speed,
        "current_heading": track[-1]["cog"] if track else 47,
        "color": "#ff3a4e"
    }
    vessels.append(suspect)

    for rec in track:
        all_ais.append({**rec, "mmsi": mmsi, "vessel_name": suspect["name"],
                        "vessel_type": vtype["type_code"]})

    # ── NEARBY VESSELS (lower suspicion) ─────────────────────────────────────

    nearby_configs = [
        ("product_tanker", "POSEIDON STAR", "636012345", "Liberia",
         spill_lat - 0.4, spill_lon + 0.6,
         spill_lat + 0.8, spill_lon - 0.5, False, False, "#ff8c00"),
        ("bulk_carrier", "OCEAN PIONEER", "345678901", "Panama",
         spill_lat + 0.5, spill_lon - 1.2,
         spill_lat - 0.3, spill_lon + 0.8, False, True, "#ff8c00"),
    ]

    imo_counter = 8876543
    for (type_key, name, mmsi_n, flag_n, s_lat, s_lon, e_lat, e_lon,
         gap, drop, color) in nearby_configs:

        vt = VESSEL_TYPES[type_key]
        spd = random.uniform(*vt["speed_range"])
        trk = generate_vessel_track(
            s_lat, s_lon, e_lat, e_lon, scenario_start, spd,
            inject_ais_gap=gap, gap_duration_minutes=12,
            inject_speed_drop=drop, drop_at_fraction=0.5
        )

        v = {
            "mmsi": mmsi_n,
            "imo":  f"VS-IMO-{imo_counter}",
            "name": f"MT {name}",
            "type": type_key.replace("_", " ").title(),
            "type_code": vt["type_code"],
            "flag": flag_n,
            "flag_code": FLAG_CODES.get(flag_n, "XX"),
            "dwt": random.randint(*vt["dwt_range"]),
            "call_sign": f"X{random.randint(1000,9999)}",
            "owner": "Global Maritime Corp.",
            "last_port": "Singapore",
            "destination": "Mumbai, India",
            "is_suspect": False,
            "ais_gap_minutes": 12 if gap else 0,
            "track": [[r["lat"], r["lon"]] for r in trk],
            "speed_profile": [r["sog"] for r in trk[::3]],
            "current_speed": trk[-1]["sog"] if trk else spd,
            "current_heading": trk[-1]["cog"] if trk else 180,
            "color": color
        }
        vessels.append(v)
        imo_counter -= 111111

        for rec in trk:
            all_ais.append({**rec, "mmsi": mmsi_n, "vessel_name": v["name"],
                            "vessel_type": vt["type_code"]})

    # ── SAVE AIS CSV ──────────────────────────────────────────────────────────

    scenario = {
        "spill_lat": spill_lat,
        "spill_lon": spill_lon,
        "spill_timestamp": spill_timestamp.isoformat(),
        "vessels": vessels,
        "total_ais_records": len(all_ais)
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # AIS CSV (MarineCadastre-compatible format)
        csv_path = output_dir / "synthetic_ais.csv"
        fieldnames = ["mmsi", "vessel_name", "vessel_type", "timestamp",
                      "lat", "lon", "sog", "cog"]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            all_ais_sorted = sorted(all_ais, key=lambda x: x["timestamp"])
            writer.writerows(all_ais_sorted)

        # Scenario JSON
        json_path = output_dir / "ais_scenario.json"
        with open(json_path, "w") as f:
            json.dump(scenario, f, indent=2, default=str)

        print(f"✅ Synthetic AIS data saved:")
        print(f"   CSV  : {csv_path} ({len(all_ais)} records)")
        print(f"   JSON : {json_path}")

    return scenario


# ─── STANDALONE ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import timezone

    spill_time = datetime(2024, 11, 14, 3, 21, 0, tzinfo=timezone.utc)

    scenario = generate_synthetic_ais_scenario(
        spill_lat=14.5204,
        spill_lon=76.3210,
        spill_timestamp=spill_time,
        output_dir=Path(__file__).parent / "sample_data"
    )
    print(f"\nGenerated {len(scenario['vessels'])} vessels, "
          f"{scenario['total_ais_records']} AIS records")
