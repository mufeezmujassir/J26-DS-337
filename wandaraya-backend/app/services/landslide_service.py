"""
Landslide Data Integration Service for WANDARAYA Component 2.
============================================================
Connects NBRO (National Building Research Organisation) historical landslide
inventory data to multimodal route risk assessment.

Key Principles:
- Validates WGS-84 coordinates within Sri Lanka geographic envelope.
- Handles missing, malformed, or out-of-bounds coordinates safely.
- Performs sub-millisecond geodesic proximity queries along route coordinates.
- Classifies incidents strictly as HISTORICAL/RECORDED hazard zones;
  NEVER fabricates or assumes active road closures.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6371008.8  # WGS-84 mean radius in meters
SRI_LANKA_BOUNDS = {
    "min_lat": 5.90,
    "max_lat": 9.90,
    "min_lon": 79.50,
    "max_lon": 82.00,
}


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two points in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


@dataclass
class LandslideRecord:
    record_id: str
    incident_type: str
    district: str
    ds_division: Optional[str]
    event_date: Optional[str]
    cause: Optional[str]
    latitude: float
    longitude: float
    source: str = "NBRO Sri Lanka Landslide Inventory"
    is_historical: bool = True
    is_active_closure: bool = False  # Ground truth records are historical; never assume active closure
    rain_1h: Optional[float] = None
    rain_24h: Optional[float] = None
    rain_cum: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "incident_type": self.incident_type,
            "district": self.district,
            "ds_division": self.ds_division,
            "event_date": self.event_date,
            "cause": self.cause,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "is_historical": self.is_historical,
            "is_active_closure": self.is_active_closure,
            "rain_1h_mm": self.rain_1h,
            "rain_24h_mm": self.rain_24h,
            "rain_cum_mm": self.rain_cum,
        }


@dataclass
class LandslideHazardMatch:
    record: LandslideRecord
    distance_meters: float
    nearest_route_point: Tuple[float, float]
    proximity_zone: str  # "CORRIDOR_DIRECT" (< 500m), "ADJACENT_SLOPE" (< 1500m), "REGIONAL_WATCH" (< 3000m)
    advisory: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record": self.record.to_dict(),
            "distance_meters": round(self.distance_meters, 1),
            "nearest_route_point": list(self.nearest_route_point),
            "proximity_zone": self.proximity_zone,
            "advisory": self.advisory,
        }


class LandslideService:
    def __init__(self, data_path: Optional[str] = None) -> None:
        self.data_path = data_path or self._default_dataset_path()
        self.records: List[LandslideRecord] = []
        self._tree: Optional[cKDTree] = None
        self._coords_rad: Optional[np.ndarray] = None
        self._load_and_index()

    @staticmethod
    def _default_dataset_path() -> str:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(base_dir, "data", "NBRO_DATA", "All_Sri_Lanka_Landslide.csv")

    def _load_and_index(self) -> None:
        """Loads and validates NBRO records, constructing spatial KDTree."""
        if not os.path.exists(self.data_path):
            logger.warning(f"NBRO landslide data file not found at {self.data_path}. Service initializing empty.")
            return

        try:
            df = pd.read_csv(self.data_path, low_memory=False)
            self.records = self._parse_and_validate_dataframe(df)
            if self.records:
                coords = np.array([[r.latitude, r.longitude] for r in self.records])
                self._coords_rad = np.radians(coords)
                self._tree = cKDTree(self._coords_rad)
                logger.info(f"Loaded and indexed {len(self.records)} valid NBRO landslide hazard records.")
        except Exception as e:
            logger.error(f"Failed to load NBRO landslide dataset: {e}", exc_info=True)

    @classmethod
    def _parse_and_validate_dataframe(cls, df: pd.DataFrame) -> List[LandslideRecord]:
        """Validates columns, coordinates, and filters out invalid geometries/duplicates."""
        records: List[LandslideRecord] = []
        seen_ids = set()

        # Resolve coordinate column names
        lat_col = next((c for c in df.columns if c.lower() in ("latitude", "lat")), None)
        lon_col = next((c for c in df.columns if c.lower() in ("longitude", "lon", "long")), None)
        if not lat_col or not lon_col:
            logger.error(f"Cannot find latitude and longitude columns in DataFrame: {df.columns.tolist()}")
            return []

        for idx, row in df.iterrows():
            try:
                raw_lat = row[lat_col]
                raw_lon = row[lon_col]
                if pd.isna(raw_lat) or pd.isna(raw_lon):
                    continue

                lat = float(raw_lat)
                lon = float(raw_lon)

                # Geographic bounds validation for Sri Lanka
                if not (SRI_LANKA_BOUNDS["min_lat"] <= lat <= SRI_LANKA_BOUNDS["max_lat"] and
                        SRI_LANKA_BOUNDS["min_lon"] <= lon <= SRI_LANKA_BOUNDS["max_lon"]):
                    continue

                # Unique record identification
                case_id = str(row.get("Case_ID", "")).strip()
                req_no = str(row.get("Request_No", "")).strip()
                record_id = case_id if case_id and case_id != "nan" else (
                    req_no if req_no and req_no != "nan" else f"NBRO_REC_{idx}"
                )

                if record_id in seen_ids:
                    continue
                seen_ids.add(record_id)

                inc_type = str(row.get("Inc_Type", "Landslide")).strip()
                district = str(row.get("District", "Unknown")).strip()
                ds_name = str(row.get("DS_Name", "")).strip() or None
                event_date = str(row.get("Date", row.get("Inc_Date", ""))).strip() or None
                if event_date in ("nan", "None", ""):
                    event_date = None
                cause = str(row.get("Cause", "")).strip() or None
                if cause in ("nan", "None", ""):
                    cause = None

                def safe_float(val: Any) -> Optional[float]:
                    try:
                        v = float(val)
                        return v if not math.isnan(v) else None
                    except (ValueError, TypeError):
                        return None

                records.append(LandslideRecord(
                    record_id=record_id,
                    incident_type=inc_type,
                    district=district,
                    ds_division=ds_name,
                    event_date=event_date,
                    cause=cause,
                    latitude=lat,
                    longitude=lon,
                    source="NBRO Sri Lanka Landslide Inventory",
                    is_historical=True,
                    is_active_closure=False,
                    rain_1h=safe_float(row.get("Rain_1h")),
                    rain_24h=safe_float(row.get("Rain_24h")),
                    rain_cum=safe_float(row.get("Rain_Cum")),
                ))
            except Exception:
                continue

        return records

    def find_hazards_near_route(
        self,
        route_coordinates: List[Tuple[float, float]],
        buffer_meters: float = 1000.0
    ) -> List[LandslideHazardMatch]:
        """
        Finds all NBRO landslide hazard records within buffer_meters of any point along the route.
        Returns deduplicated matches sorted by proximity to route corridor.
        """
        if not self._tree or not self.records or not route_coordinates:
            return []

        # Validate and clean route coordinates
        valid_route_coords = [
            (float(lat), float(lon))
            for lat, lon in route_coordinates
            if SRI_LANKA_BOUNDS["min_lat"] <= float(lat) <= SRI_LANKA_BOUNDS["max_lat"]
            and SRI_LANKA_BOUNDS["min_lon"] <= float(lon) <= SRI_LANKA_BOUNDS["max_lon"]
        ]
        if not valid_route_coords:
            return []

        # Dense sampling if sparse to avoid missing hazards between vertices
        sampled_coords: List[Tuple[float, float]] = []
        for i in range(len(valid_route_coords)):
            p1 = valid_route_coords[i]
            sampled_coords.append(p1)
            if i < len(valid_route_coords) - 1:
                p2 = valid_route_coords[i + 1]
                dist_m = haversine_distance_m(p1[0], p1[1], p2[0], p2[1])
                # If vertices are far apart, interpolate sample points every 500m
                if dist_m > 500.0:
                    steps = max(1, int(dist_m / 500.0))
                    for step in range(1, steps):
                        frac = step / steps
                        sampled_coords.append((
                            p1[0] + (p2[0] - p1[0]) * frac,
                            p1[1] + (p2[1] - p1[1]) * frac,
                        ))

        query_rad = np.radians(np.array(sampled_coords))
        radius_rad = buffer_meters / EARTH_RADIUS_M

        matched_indices_by_point = self._tree.query_ball_point(query_rad, r=radius_rad)

        hazard_map: Dict[str, LandslideHazardMatch] = {}

        for pt_idx, record_indices in enumerate(matched_indices_by_point):
            if not record_indices:
                continue
            pt_lat, pt_lon = sampled_coords[pt_idx]

            for rec_idx in record_indices:
                rec = self.records[rec_idx]
                dist_m = haversine_distance_m(pt_lat, pt_lon, rec.latitude, rec.longitude)
                if dist_m > buffer_meters:
                    continue

                if rec.record_id not in hazard_map or dist_m < hazard_map[rec.record_id].distance_meters:
                    if dist_m <= 500.0:
                        zone = "CORRIDOR_DIRECT"
                        advisory = (
                            f"Corridor intersects within {dist_m:.0f}m of an NBRO recorded historical {rec.incident_type} "
                            f"in {rec.district}. Caution advised during sustained monsoonal rainfall; road is not confirmed closed."
                        )
                    elif dist_m <= 1500.0:
                        zone = "ADJACENT_SLOPE"
                        advisory = (
                            f"Route passes {dist_m:.0f}m from a documented slope instability zone in {rec.district}. "
                            f"Monitoring advised under active meteorological alerts."
                        )
                    else:
                        zone = "REGIONAL_WATCH"
                        advisory = (
                            f"Regional slope hazard documented {dist_m:.0f}m away in {rec.district}. "
                            f"Low direct corridor impact under standard conditions."
                        )

                    hazard_map[rec.record_id] = LandslideHazardMatch(
                        record=rec,
                        distance_meters=dist_m,
                        nearest_route_point=(pt_lat, pt_lon),
                        proximity_zone=zone,
                        advisory=advisory,
                    )

        results = list(hazard_map.values())
        results.sort(key=lambda m: m.distance_meters)
        return results

    def assess_route_summary(
        self,
        route_coordinates: List[Tuple[float, float]],
        buffer_meters: float = 1000.0
    ) -> Dict[str, Any]:
        """
        Produces a standardized assessment summary for the landslide dimension.
        """
        if not self.records:
            return {
                "status": "RISK_DATA_UNAVAILABLE",
                "hazard_count": 0,
                "closest_hazard_distance_m": None,
                "hazards": [],
                "note": "NBRO landslide database could not be loaded or is empty.",
            }

        hazards = self.find_hazards_near_route(route_coordinates, buffer_meters=buffer_meters)

        if not hazards:
            return {
                "status": "NO_RISK_DETECTED",
                "hazard_count": 0,
                "closest_hazard_distance_m": None,
                "hazards": [],
                "note": f"No NBRO recorded landslide hazard zones found within {buffer_meters:.0f}m of the route.",
            }

        direct_hits = [h for h in hazards if h.proximity_zone == "CORRIDOR_DIRECT"]
        status = "RISK_DETECTED" if direct_hits or any(h.distance_meters <= 1000.0 for h in hazards) else "NO_RISK_DETECTED"

        return {
            "status": status,
            "hazard_count": len(hazards),
            "closest_hazard_distance_m": round(hazards[0].distance_meters, 1) if hazards else None,
            "hazards": [h.to_dict() for h in hazards[:15]],  # Top 15 closest
            "note": (
                f"Identified {len(hazards)} recorded NBRO slope/landslide hazard points within {buffer_meters:.0f}m buffer. "
                "These represent recorded historical occurrences, not confirmed active road closures."
            ),
        }


# Singleton service instance initialized on default NBRO dataset
landslide_service = LandslideService()
