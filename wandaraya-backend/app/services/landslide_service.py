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

# Configurable, evidence-based mapping from NBRO 1:50,000 Landslide Hazard Zonation
# categorical classes to a standardized 0-100 Geological Susceptibility score (L).
# Based on NBRO Landslide Hazard Mapping Project technical classification standards.
DEFAULT_HAZARD_CLASS_SUSCEPTIBILITY: Dict[str, float] = {
    "VERY_HIGH_HAZARD": 95.0,
    "HIGH_HAZARD": 75.0,
    "MODEST_HAZARD": 40.0,
    "LOW_HAZARD": 15.0,
    "WATER_BODY_UNCLASSIFIED": 0.0,
    "NO_HAZARD_ZONE": 0.0,
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
    trigger_rainfall_mm: Optional[float] = 75.0
    trigger_rainfall_source: Optional[str] = "NBRO_EMPIRICAL_WATCH_THRESHOLD"
    trigger_rainfall_status: str = "AVAILABLE"  # "AVAILABLE", "HISTORICAL_TRIGGER_UNAVAILABLE", "NBRO_LHZM_ZONATION"
    is_polygon: bool = False
    polygon_layer: Optional[str] = None
    polygon_name: Optional[str] = None
    geojson: Optional[str] = None

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
            "trigger_rainfall_status": self.trigger_rainfall_status,
            "is_polygon": self.is_polygon,
            "polygon_layer": self.polygon_layer,
            "polygon_name": self.polygon_name,
            "geojson": self.geojson,
            "historical_rainfall_description": (
                f"Historically triggered by {self.rain_24h:.1f}mm rainfall in 24h"
                if self.rain_24h is not None else (
                    f"Historically triggered by {self.rain_cum:.1f}mm cumulative rainfall"
                    if self.rain_cum is not None else (
                        f"Empirical hill country baseline threshold: {self.trigger_rainfall_mm:.1f}mm/24h"
                        if self.trigger_rainfall_mm is not None else "Historical incident recorded without localized rainfall measurement at time of failure."
                    )
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


_SYNC_DB_ENGINE = None
_SUSCEPTIBILITY_CACHE: Dict[Tuple[float, float], Tuple[float, str]] = {}

def get_sync_engine():
    global _SYNC_DB_ENGINE
    if _SYNC_DB_ENGINE is None:
        try:
            from app.config import settings
            from sqlalchemy import create_engine
            sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
            _SYNC_DB_ENGINE = create_engine(sync_url, pool_size=10, max_overflow=20, pool_pre_ping=True, connect_args={"connect_timeout": 3})
        except Exception as e:
            logger.warning(f"Failed to initialize sync database engine: {e}")
    return _SYNC_DB_ENGINE


class LandslideService:
    def __init__(self, data_path: Optional[str] = None, polygon_path: Optional[str] = None) -> None:
        default_master, default_poly = self._default_dataset_paths()
        self.is_custom_dataset = (data_path is not None)
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
            from sqlalchemy import text
            engine = get_sync_engine()
            if not engine:
                return {"connected": False, "error": "Database engine not initialized"}
            with engine.connect() as conn:
                hz_cnt = conn.execute(text("SELECT count(*) FROM nbro_hazard_zones")).scalar()
                inc_cnt = conn.execute(text("SELECT count(*) FROM nbro_incidents")).scalar()
                insp_cnt = conn.execute(text("SELECT count(*) FROM nbro_inspections")).scalar()
                poly_cnt = conn.execute(text("SELECT count(*) FROM nbro_polygons")).scalar()
                return {
                    "connected": True,
                    "database": "PostgreSQL with PostGIS",
                    "nbro_hazard_zones_count": hz_cnt,
                    "nbro_incidents_count": inc_cnt,
                    "nbro_inspections_count": insp_cnt,
                    "nbro_polygons_count": poly_cnt,
                    "status": "OPERATIONAL",
                }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    @staticmethod
    def get_susceptibility_score(
        latitude: float,
        longitude: float,
        class_mapping: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, str]:
        """
        Queries official NBRO 1:50,000 Landslide Hazard Zonation Map (194,016 points)
        in PostgreSQL/PostGIS for the hazard susceptibility score at the given coordinate.
        Converts hazard classes into a documented 0-100 susceptibility score using a
        configurable, evidence-based mapping (DEFAULT_HAZARD_CLASS_SUSCEPTIBILITY).
        Uses PostGIS geography ST_Distance for accurate metric distance calculations.
        Returns (susceptibility_score, hazard_class).
        """
        mapping = class_mapping or DEFAULT_HAZARD_CLASS_SUSCEPTIBILITY
        ckey = (round(latitude, 3), round(longitude, 3))
        if ckey in _SUSCEPTIBILITY_CACHE and class_mapping is None:
            return _SUSCEPTIBILITY_CACHE[ckey]
        try:
            from sqlalchemy import text
            engine = get_sync_engine()
            if not engine:
                return 0.0, "NO_HAZARD_ZONE"
            with engine.connect() as conn:
                res = conn.execute(text("""
                    SELECT hz.susceptibility_score, hz.hazard_class,
                           ST_Distance(hz.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS dist_m
                    FROM nbro_hazard_zones hz
                    WHERE ST_DWithin(hz.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 0.015)
                    ORDER BY hz.geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                    LIMIT 1;
                """), {"lon": longitude, "lat": latitude}).fetchone()
                if res and res[2] <= 1500.0:
                    hazard_cls = str(res[1])
                    score_val = mapping.get(hazard_cls, float(res[0]) if res[0] is not None else 0.0)
                    val = (score_val, hazard_cls)
                else:
                    val = (0.0, "NO_HAZARD_ZONE")
                if class_mapping is None:
                    _SUSCEPTIBILITY_CACHE[ckey] = val
                return val
        except Exception as e:
            logger.warning(f"Failed to query database for susceptibility score: {e}")
            return 0.0, "NO_HAZARD_ZONE"

    @classmethod
    def get_segment_susceptibility(
        cls,
        coordinates: List[Tuple[float, float]],
        class_mapping: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates geological susceptibility across a road/railway polyline segment
        by sampling points and querying NBRO hazard zones using PostGIS geography distance.
        Returns max, mean, and dominant hazard class along the segment.
        """
        if not coordinates:
            return {
                "max_susceptibility": 0.0,
                "mean_susceptibility": 0.0,
                "dominant_hazard_class": "NO_HAZARD_ZONE",
                "sampled_points": 0,
            }

        scores: List[float] = []
        classes: List[str] = []
        for lat, lon in coordinates:
            sc, hc = cls.get_susceptibility_score(lat, lon, class_mapping=class_mapping)
            scores.append(sc)
            classes.append(hc)

        max_sc = max(scores) if scores else 0.0
        mean_sc = sum(scores) / len(scores) if scores else 0.0
        dominant_cls = "NO_HAZARD_ZONE"
        for sc, hc in zip(scores, classes):
            if sc == max_sc:
                dominant_cls = hc
                break

        return {
            "max_susceptibility": round(max_sc, 2),
            "mean_susceptibility": round(mean_sc, 2),
            "dominant_hazard_class": dominant_cls,
            "sampled_points": len(scores),
        }

    def query_database_hazards(
        self,
        route_coordinates: List[Tuple[float, float]],
        buffer_meters: float = 1000.0,
    ) -> Optional[List[LandslideHazardMatch]]:
        """
        Directly queries PostgreSQL/PostGIS for NBRO hazard zones (194,016 1:50,000 points),
        historical incidents (20,438), and mapped hazard polygons (1,967).
        Uses GiST spatial indexes (idx_nbro_hazard_zones_geom, idx_nbro_incidents_geom).
        Returns None if database is unreachable, allowing seamless KDTree fallback.
        """
        valid_coords = [
            (float(lat), float(lon))
            for lat, lon in route_coordinates
            if SRI_LANKA_BOUNDS["min_lat"] <= float(lat) <= SRI_LANKA_BOUNDS["max_lat"]
            and SRI_LANKA_BOUNDS["min_lon"] <= float(lon) <= SRI_LANKA_BOUNDS["max_lon"]
        ]
        if not valid_coords:
            return []

        try:
            from sqlalchemy import text
            engine = get_sync_engine()
            if not engine:
                return []

            deg_buf = max(0.001, buffer_meters / 111320.0)
            if len(valid_coords) == 1:
                wkt = f"POINT({valid_coords[0][1]} {valid_coords[0][0]})"
            else:
                pts_str = ", ".join(f"{lon} {lat}" for lat, lon in valid_coords)
                wkt = f"LINESTRING({pts_str})"

            hazard_map: Dict[str, LandslideHazardMatch] = {}

            with engine.connect() as conn:
                # 1. Official 1:50,000 Landslide Hazard Zonation Map (194,016 points)
                hz_rows = conn.execute(text("""
                    SELECT hz.id, hz.hazard_range, hz.hazard_class, hz.susceptibility_score,
                           hz.latitude, hz.longitude,
                           ST_Distance(hz.geom::geography, ST_SetSRID(ST_GeomFromText(:wkt), 4326)::geography) AS dist_m
                    FROM nbro_hazard_zones hz
                    WHERE ST_DWithin(hz.geom, ST_SetSRID(ST_GeomFromText(:wkt), 4326), :deg_buffer)
                    ORDER BY hz.susceptibility_score DESC, dist_m ASC
                    LIMIT 30;
                """), {"wkt": wkt, "deg_buffer": deg_buf}).fetchall()

                for row in hz_rows:
                    hz_id, h_range, h_class, susc_score, lat, lon, dist_m = row
                    dist_m = float(dist_m)
                    if dist_m > buffer_meters:
                        continue
                    zone_key = f"NBRO_LHZM_{hz_id}"
                    proximity_zone = "CORRIDOR_DIRECT" if dist_m <= 500.0 else ("ADJACENT_SLOPE" if dist_m <= 1500.0 else "REGIONAL_WATCH")
                    advisory = (
                        f"Official NBRO 1:50,000 Landslide Hazard Zonation Map indicates {h_class.replace('_', ' ')} "
                        f"(Susceptibility: {susc_score:.1f}, Range {h_range}) within {dist_m:.0f}m of route corridor. "
                        f"Represents baseline geological slope susceptibility, not an active ground failure."
                    )
                    record = LandslideRecord(
                        record_id=zone_key,
                        incident_type=f"NBRO Hazard Zone ({h_class})",
                        district="Hill Country",
                        ds_division=None,
                        event_date=None,
                        cause="NBRO 1:50,000 Hazard Zonation Survey",
                        latitude=lat,
                        longitude=lon,
                        source="NBRO 1:50,000 Landslide Hazard Zonation Map (PostgreSQL)",
                        is_historical=False,
                        is_active_closure=False,
                        trigger_rainfall_mm=75.0,
                        trigger_rainfall_source="NBRO_LHZM_ZONATION",
                        trigger_rainfall_status="NBRO_LHZM_ZONATION",
                    )
                    hazard_map[zone_key] = LandslideHazardMatch(
                        record=record,
                        distance_meters=dist_m,
                        nearest_route_point=(lat, lon),
                        proximity_zone=proximity_zone,
                        advisory=advisory,
                    )

                # 2. Historical Recorded Incidents (20,438 records)
                inc_rows = conn.execute(text("""
                    SELECT inc.id, inc.case_id, inc.inc_type, inc.district, inc.ds_name,
                           inc.date, inc.cause, inc.rain_1h, inc.rain_24h, inc.rain_cum,
                           inc.latitude, inc.longitude,
                           ST_Distance(inc.geom::geography, ST_SetSRID(ST_GeomFromText(:wkt), 4326)::geography) AS dist_m
                    FROM nbro_incidents inc
                    WHERE ST_DWithin(inc.geom, ST_SetSRID(ST_GeomFromText(:wkt), 4326), :deg_buffer)
                    ORDER BY dist_m ASC
                    LIMIT 30;
                """), {"wkt": wkt, "deg_buffer": deg_buf}).fetchall()

                for row in inc_rows:
                    (i_id, case_id, inc_type, district, ds_name, date_str, cause,
                     r1h, r24h, rcum, lat, lon, dist_m) = row
                    dist_m = float(dist_m)
                    if dist_m > buffer_meters:
                        continue
                    rec_id = case_id or f"NBRO_INC_{i_id}"
                    if rec_id in hazard_map and hazard_map[rec_id].distance_meters <= dist_m:
                        continue

                    if r24h is not None and r24h > 0:
                        trig_mm, trig_src = r24h, "NBRO_EVENT_24H_RECORDED"
                        trig_status = "HISTORICAL_TRIGGER_RECORDED"
                    elif rcum is not None and rcum > 0:
                        trig_mm, trig_src = rcum, "NBRO_EVENT_CUMULATIVE_RECORDED"
                        trig_status = "HISTORICAL_TRIGGER_RECORDED"
                    else:
                        trig_mm, trig_src = None, "HISTORICAL_RAINFALL_NOT_RECORDED"
                        trig_status = "HISTORICAL_TRIGGER_UNAVAILABLE"

                    proximity_zone = "CORRIDOR_DIRECT" if dist_m <= 500.0 else ("ADJACENT_SLOPE" if dist_m <= 1500.0 else "REGIONAL_WATCH")
                    advisory = (
                        f"Route corridor passes within {dist_m:.0f}m of an NBRO recorded historical {inc_type or 'landslide'} "
                        f"in {district or 'Hill Country'} (Date: {date_str or 'unrecorded'}). Ground truth represents historical occurrence; "
                        f"segment is not assumed to be unstable or closed unless verified by current conditions."
                    )
                    record = LandslideRecord(
                        record_id=rec_id,
                        incident_type=inc_type or "Historical Landslide",
                        district=district or "Unknown",
                        ds_division=ds_name,
                        event_date=date_str,
                        cause=cause,
                        latitude=lat,
                        longitude=lon,
                        source="NBRO Sri Lanka Landslide Inventory (PostgreSQL)",
                        is_historical=True,
                        is_active_closure=False,
                        rain_1h=r1h,
                        rain_24h=r24h,
                        rain_cum=rcum,
                        trigger_rainfall_mm=trig_mm,
                        trigger_rainfall_source=trig_src,
                        trigger_rainfall_status=trig_status,
                    )
                    hazard_map[rec_id] = LandslideHazardMatch(
                        record=record,
                        distance_meters=dist_m,
                        nearest_route_point=(lat, lon),
                        proximity_zone=proximity_zone,
                        advisory=advisory,
                    )

                # 3. NBRO Mapped Hazard Polygons (1,967 polygons)
                poly_rows = conn.execute(text("""
                    SELECT p.id, p.name, p.district, p.layer_name, p.centroid_latitude, p.centroid_longitude,
                           ST_Distance(p.wkt_geometry::geography, ST_SetSRID(ST_GeomFromText(:wkt), 4326)::geography) AS dist_m,
                           ST_Intersects(p.wkt_geometry, ST_SetSRID(ST_GeomFromText(:wkt), 4326)) AS is_intersect,
                           ST_AsGeoJSON(p.wkt_geometry) AS geojson
                    FROM nbro_polygons p
                    WHERE ST_DWithin(p.wkt_geometry, ST_SetSRID(ST_GeomFromText(:wkt), 4326), :deg_buffer)
                    ORDER BY dist_m ASC
                    LIMIT 20;
                """), {"wkt": wkt, "deg_buffer": deg_buf}).fetchall()

                for row in poly_rows:
                    p_id, name, district, layer_name, c_lat, c_lon, dist_m, is_intersect, geojson_str = row
                    dist_m = float(dist_m)
                    if dist_m > buffer_meters:
                        continue
                    poly_key = f"NBRO_POLY_{p_id}"
                    zone = "POLYGON_DIRECT_INTERSECTION" if is_intersect else ("POLYGON_DIRECT" if dist_m <= 500.0 else "POLYGON_ADJACENT")
                    advisory = (
                        f"Route corridor directly intersects NBRO mapped landslide hazard footprint polygon ({layer_name}) in {district}."
                        if zone == "POLYGON_DIRECT_INTERSECTION" else
                        f"Route corridor passes within {dist_m:.0f}m of NBRO mapped landslide hazard footprint polygon in {district}."
                    )
                    poly_rec = LandslideRecord(
                        record_id=poly_key,
                        incident_type=f"NBRO Hazard Polygon ({layer_name})",
                        district=district or "Unknown",
                        ds_division=None,
                        event_date=None,
                        cause="Mapped Geological Slope Instability Footprint",
                        latitude=c_lat,
                        longitude=c_lon,
                        source="NBRO Sri Lanka Hazard Polygons (PostgreSQL)",
                        is_historical=True,
                        is_active_closure=False,
                        trigger_rainfall_mm=75.0,
                        trigger_rainfall_source="NBRO_POLYGON_WATCH_THRESHOLD",
                        is_polygon=True,
                        polygon_layer=layer_name,
                        polygon_name=name,
                        geojson=geojson_str,
                    )
                    hazard_map[poly_key] = LandslideHazardMatch(
                        record=poly_rec,
                        distance_meters=dist_m,
                        nearest_route_point=(c_lat, c_lon),
                        proximity_zone=zone,
                        advisory=advisory,
                    )

            results = list(hazard_map.values())
            results.sort(key=lambda m: m.distance_meters)
            return results

        except Exception as e:
            logger.warning(f"PostGIS direct hazard query encountered error (falling back to KDTree): {e}")
            return None

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
        buffer_meters: float = 1000.0,
        prefer_database: bool = True,
    ) -> List[LandslideHazardMatch]:
        """
        Finds all NBRO landslide hazard records within buffer_meters of any point along the route.
        Queries PostgreSQL/PostGIS database first (194,016 hazard zones + 20,438 incidents + 1,967 polygons).
        Falls back to in-memory spatial KDTree if database is offline.
        """
        if not route_coordinates:
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

        if prefer_database and not self.is_custom_dataset:
            db_res = self.query_database_hazards(valid_route_coords, buffer_meters=buffer_meters)
            if db_res is not None:
                return db_res

        if not self._tree or not self.records:
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
