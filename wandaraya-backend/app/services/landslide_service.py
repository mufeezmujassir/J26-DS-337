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
class NBROPolygon:
    polygon_id: str
    name: str
    district: str
    layer_name: str
    centroid_lat: float
    centroid_lon: float
    wkt_geometry: Optional[str] = None
    shapely_geom: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "polygon_id": self.polygon_id,
            "name": self.name,
            "district": self.district,
            "layer_name": self.layer_name,
            "centroid_latitude": self.centroid_lat,
            "centroid_longitude": self.centroid_lon,
            "has_polygon_geometry": self.shapely_geom is not None,
        }


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
    trigger_rainfall_mm: float = 75.0
    trigger_rainfall_source: str = "NBRO_EMPIRICAL_WATCH_THRESHOLD"
    is_polygon: bool = False
    polygon_layer: Optional[str] = None
    polygon_name: Optional[str] = None

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
            "trigger_rainfall_mm": self.trigger_rainfall_mm,
            "trigger_rainfall_source": self.trigger_rainfall_source,
            "is_polygon": self.is_polygon,
            "polygon_layer": self.polygon_layer,
            "historical_rainfall_description": (
                f"Historically triggered by {self.rain_24h:.1f}mm rainfall in 24h"
                if self.rain_24h is not None else (
                    f"Historically triggered by {self.rain_cum:.1f}mm cumulative rainfall"
                    if self.rain_cum is not None else f"NBRO hill country baseline threshold: {self.trigger_rainfall_mm:.1f}mm/24h"
                )
            ),
        }


@dataclass
class LandslideHazardMatch:
    record: LandslideRecord
    distance_meters: float
    nearest_route_point: Tuple[float, float]
    proximity_zone: str  # "CORRIDOR_DIRECT", "ADJACENT_SLOPE", "REGIONAL_WATCH", "POLYGON_DIRECT_INTERSECTION", "POLYGON_DIRECT", "POLYGON_ADJACENT"
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
    def __init__(self, data_path: Optional[str] = None, polygon_path: Optional[str] = None) -> None:
        default_master, default_poly = self._default_dataset_paths()
        self.data_path = data_path or default_master
        self.polygon_path = polygon_path or (default_poly if data_path is None else None)
        self.records: List[LandslideRecord] = []
        self.polygons: List[NBROPolygon] = []
        self._tree: Optional[cKDTree] = None
        self._poly_tree: Optional[cKDTree] = None
        self._coords_rad: Optional[np.ndarray] = None
        self._load_and_index()

    @staticmethod
    def _default_dataset_paths() -> Tuple[str, str]:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        master_path = os.path.join(base_dir, "data", "NBRO_DATA", "All_Sri_Lanka_Master.csv")
        poly_path = os.path.join(base_dir, "data", "NBRO_DATA", "All_Sri_Lanka_Polygons.csv")
        if not os.path.exists(master_path):
            master_path = os.path.join(base_dir, "data", "NBRO_DATA", "All_Sri_Lanka_Landslide.csv")
        return master_path, poly_path

    @staticmethod
    def get_database_status() -> Dict[str, Any]:
        """Queries PostgreSQL database for NBRO tables row counts and health."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                return {"connected": False, "reason": "DATABASE_URL not configured"}
            from sqlalchemy import create_engine, text
            sync_url = db_url.replace("+asyncpg", "").replace("+psycopg", "")
            engine = create_engine(sync_url, connect_args={"connect_timeout": 3})
            with engine.connect() as conn:
                inc_cnt = conn.execute(text("SELECT count(*) FROM nbro_incidents")).scalar()
                insp_cnt = conn.execute(text("SELECT count(*) FROM nbro_inspections")).scalar()
                poly_cnt = conn.execute(text("SELECT count(*) FROM nbro_polygons")).scalar()
                return {
                    "connected": True,
                    "database": "PostgreSQL with PostGIS",
                    "nbro_incidents_count": inc_cnt,
                    "nbro_inspections_count": insp_cnt,
                    "nbro_polygons_count": poly_cnt,
                    "status": "OPERATIONAL",
                }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def _load_and_index(self) -> None:
        """Loads and validates NBRO master records and hazard polygons, constructing spatial KDTrees."""
        # 1. Load Point Incidents (Master Dataset)
        if os.path.exists(self.data_path):
            try:
                df = pd.read_csv(self.data_path, low_memory=False)
                self.records = self._parse_and_validate_dataframe(df)
                if self.records:
                    coords = np.array([[r.latitude, r.longitude] for r in self.records])
                    self._coords_rad = np.radians(coords)
                    self._tree = cKDTree(self._coords_rad)
                    logger.info(f"Loaded and indexed {len(self.records)} valid NBRO landslide hazard records from {self.data_path}.")
            except Exception as e:
                logger.error(f"Failed to load NBRO landslide dataset: {e}", exc_info=True)
        else:
            logger.warning(f"NBRO landslide data file not found at {self.data_path}. Service initializing empty.")

        # 2. Load Spatial Hazard Polygons
        if self.polygon_path and os.path.exists(self.polygon_path):
            try:
                df_p = pd.read_csv(self.polygon_path, low_memory=False)
                self.polygons = self._parse_and_validate_polygons(df_p)
                if self.polygons:
                    p_coords = np.array([[p.centroid_lat, p.centroid_lon] for p in self.polygons])
                    self._poly_tree = cKDTree(np.radians(p_coords))
                    logger.info(f"Loaded and indexed {len(self.polygons)} NBRO hazard footprint polygons from {self.polygon_path}.")
            except Exception as e:
                logger.error(f"Failed to load NBRO hazard polygons: {e}", exc_info=True)

    @classmethod
    def _parse_and_validate_polygons(cls, df: pd.DataFrame) -> List[NBROPolygon]:
        """Parses and validates NBRO hazard footprint polygons with shapely geometries."""
        polys: List[NBROPolygon] = []
        has_shapely = False
        try:
            from shapely import wkt
            has_shapely = True
        except ImportError:
            pass

        for idx, row in df.iterrows():
            try:
                c_lat = float(row.get("Centroid_Latitude", 0))
                c_lon = float(row.get("Centroid_Longitude", 0))
                if not (SRI_LANKA_BOUNDS["min_lat"] <= c_lat <= SRI_LANKA_BOUNDS["max_lat"] and
                        SRI_LANKA_BOUNDS["min_lon"] <= c_lon <= SRI_LANKA_BOUNDS["max_lon"]):
                    continue

                wkt_str = str(row.get("WKT_Geometry", "")).strip() if pd.notna(row.get("WKT_Geometry")) else None
                geom = None
                if wkt_str and has_shapely:
                    try:
                        from shapely import wkt
                        geom = wkt.loads(wkt_str)
                    except Exception:
                        geom = None

                polys.append(NBROPolygon(
                    polygon_id=f"NBRO_POLY_{idx + 1}",
                    name=str(row.get("Name", "")).strip() or f"Footprint_{idx + 1}",
                    district=str(row.get("District", "Unknown")).strip(),
                    layer_name=str(row.get("Layer_Name", "Landslide_Footprint")).strip(),
                    centroid_lat=c_lat,
                    centroid_lon=c_lon,
                    wkt_geometry=wkt_str,
                    shapely_geom=geom,
                ))
            except Exception:
                continue
        return polys

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
                    if val is None or pd.isna(val):
                        return None
                    s = str(val).strip().lower().replace("mm", "").replace("-", "").strip()
                    if not s or s in ("nan", "none"):
                        return None
                    try:
                        v = float(s)
                        return v if math.isfinite(v) and v >= 0.0 else None
                    except (ValueError, TypeError):
                        return None

                r_1h = safe_float(row.get("Rain_1h"))
                r_24h = safe_float(row.get("Rain_24h"))
                r_cum = safe_float(row.get("Rain_Cum"))

                if r_24h is not None and r_24h > 0.0:
                    trigger_mm = r_24h
                    trigger_src = "NBRO_EVENT_24H_RECORDED"
                elif r_cum is not None and r_cum > 0.0:
                    trigger_mm = r_cum
                    trigger_src = "NBRO_EVENT_CUMULATIVE_RECORDED"
                elif r_1h is not None and r_1h > 0.0:
                    trigger_mm = r_1h * 4.0
                    trigger_src = "NBRO_EVENT_1H_EXTRAPOLATED"
                else:
                    trigger_mm = 75.0  # NBRO Sri Lanka standard Level 1 Watch rainfall threshold
                    trigger_src = "NBRO_EMPIRICAL_WATCH_THRESHOLD"

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
                    rain_1h=r_1h,
                    rain_24h=r_24h,
                    rain_cum=r_cum,
                    trigger_rainfall_mm=trigger_mm,
                    trigger_rainfall_source=trigger_src,
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

        matched_indices_by_point = self._tree.query_ball_point(query_rad, r=radius_rad) if self._tree else []

        hazard_map: Dict[str, LandslideHazardMatch] = {}

        # 1. Match Point Hazards (Master Incidents Dataset)
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

        # 2. Match NBRO Landslide Footprint Polygons (Spatial Geometry Dataset)
        if self._poly_tree and self.polygons:
            poly_query_rad = (buffer_meters + 2500.0) / EARTH_RADIUS_M
            matched_poly_by_point = self._poly_tree.query_ball_point(query_rad, r=poly_query_rad)

            for pt_idx, poly_indices in enumerate(matched_poly_by_point):
                if not poly_indices:
                    continue
                pt_lat, pt_lon = sampled_coords[pt_idx]

                for p_idx in poly_indices:
                    poly = self.polygons[p_idx]
                    dist_m = 0.0
                    zone = "POLYGON_DIRECT"

                    if poly.shapely_geom:
                        try:
                            from shapely.geometry import Point
                            p = Point(pt_lon, pt_lat)
                            if poly.shapely_geom.contains(p) or poly.shapely_geom.intersects(p):
                                dist_m = 0.0
                                zone = "POLYGON_DIRECT_INTERSECTION"
                            else:
                                d_deg = poly.shapely_geom.distance(p)
                                dist_m = d_deg * 111000.0
                        except Exception:
                            dist_m = haversine_distance_m(pt_lat, pt_lon, poly.centroid_lat, poly.centroid_lon)
                    else:
                        dist_m = haversine_distance_m(pt_lat, pt_lon, poly.centroid_lat, poly.centroid_lon)

                    if dist_m > buffer_meters:
                        continue

                    if poly.polygon_id not in hazard_map or dist_m < hazard_map[poly.polygon_id].distance_meters:
                        if zone != "POLYGON_DIRECT_INTERSECTION":
                            zone = "POLYGON_DIRECT" if dist_m <= 500.0 else "POLYGON_ADJACENT"

                        advisory = (
                            f"Route corridor directly intersects NBRO mapped landslide hazard footprint polygon ({poly.layer_name}) "
                            f"in {poly.district}." if zone == "POLYGON_DIRECT_INTERSECTION" else
                            f"Route corridor passes within {dist_m:.0f}m of NBRO mapped landslide hazard footprint polygon in {poly.district}."
                        )

                        poly_rec = LandslideRecord(
                            record_id=poly.polygon_id,
                            incident_type=f"NBRO Hazard Polygon ({poly.layer_name})",
                            district=poly.district,
                            ds_division=None,
                            event_date=None,
                            cause="Mapped Geological Slope Instability Footprint",
                            latitude=poly.centroid_lat,
                            longitude=poly.centroid_lon,
                            source="NBRO Sri Lanka Hazard Polygons",
                            is_historical=True,
                            is_active_closure=False,
                            rain_1h=None,
                            rain_24h=None,
                            rain_cum=None,
                            trigger_rainfall_mm=75.0,
                            trigger_rainfall_source="NBRO_POLYGON_WATCH_THRESHOLD",
                            is_polygon=True,
                            polygon_layer=poly.layer_name,
                            polygon_name=poly.name,
                        )

                        hazard_map[poly.polygon_id] = LandslideHazardMatch(
                            record=poly_rec,
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
        Produces a standardized assessment summary for the landslide dimension,
        incorporating both NBRO master incidents and mapped footprint polygons.
        """
        if not self.records and not self.polygons:
            return {
                "status": "RISK_DATA_UNAVAILABLE",
                "hazard_count": 0,
                "polygon_count": 0,
                "incident_count": 0,
                "closest_hazard_distance_m": None,
                "closest_polygon_distance_m": None,
                "hazards": [],
                "note": "NBRO landslide database could not be loaded or is empty.",
                "database_status": self.get_database_status(),
            }

        hazards = self.find_hazards_near_route(route_coordinates, buffer_meters=buffer_meters)

        if not hazards:
            return {
                "status": "NO_RISK_DETECTED",
                "hazard_count": 0,
                "polygon_count": 0,
                "incident_count": 0,
                "closest_hazard_distance_m": None,
                "closest_polygon_distance_m": None,
                "hazards": [],
                "note": f"No NBRO recorded landslide hazard points or polygons found within {buffer_meters:.0f}m of the route.",
                "database_status": self.get_database_status(),
            }

        poly_hits = [h for h in hazards if h.record.is_polygon]
        incident_hits = [h for h in hazards if not h.record.is_polygon]
        direct_hits = [h for h in hazards if h.proximity_zone in ("CORRIDOR_DIRECT", "POLYGON_DIRECT_INTERSECTION", "POLYGON_DIRECT")]
        status = "RISK_DETECTED" if direct_hits or any(h.distance_meters <= 1000.0 for h in hazards) else "NO_RISK_DETECTED"

        return {
            "status": status,
            "hazard_count": len(hazards),
            "polygon_count": len(poly_hits),
            "incident_count": len(incident_hits),
            "closest_hazard_distance_m": round(hazards[0].distance_meters, 1) if hazards else None,
            "closest_polygon_distance_m": round(poly_hits[0].distance_meters, 1) if poly_hits else None,
            "hazards": [h.to_dict() for h in hazards[:20]],
            "database_source": "NBRO Sri Lanka Master + Polygons (20,438 Incidents, 1,967 Polygons)",
            "database_status": self.get_database_status(),
            "note": (
                f"Identified {len(hazards)} recorded NBRO slope hazard features ({len(poly_hits)} polygons, {len(incident_hits)} incidents) "
                f"within {buffer_meters:.0f}m buffer. Ground truth records represent recorded geological vulnerability, not active road closures."
            ),
        }


# Singleton service instance initialized on default NBRO dataset
landslide_service = LandslideService()
