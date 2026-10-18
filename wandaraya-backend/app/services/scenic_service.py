import os
import math
import logging
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional
from app.services.transfer_loader import haversine

logger = logging.getLogger(__name__)

class ScenicService:
    """
    Evaluates scenic value along travel routes and identifies nearby scenic places,
    viewpoints, waterfalls, nature reserves, and cultural attractions across Sri Lanka.
    """

    CATEGORY_WEIGHTS = {
        "waterfall": 10.0,
        "mountain / peak": 9.0,
        "nature reserve": 9.0,
        "protected area": 8.0,
        "viewpoint": 8.0,
        "cliff": 7.0,
        "cave": 7.0,
        "beach": 6.5,
        "tourist attraction": 6.0,
        "attractions": 6.0,
    }

    def __init__(self, csv_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.csv_path = csv_path or os.path.join(base_dir, "data", "scenic", "sri_lanka_combined_scenic_places.csv")
        self.places: List[Dict[str, Any]] = []
        self._load_scenic_places()

    def _load_scenic_places(self):
        if not os.path.exists(self.csv_path):
            logger.warning(f"Scenic places CSV not found at: {self.csv_path}")
            return

        try:
            df = pd.read_csv(self.csv_path)
            for _, row in df.iterrows():
                lat = row.get("latitude")
                lon = row.get("longitude")
                name = str(row.get("name", "")).strip()
                cat = str(row.get("category", "")).strip() or "Tourist Attraction"
                district = str(row.get("district", "")).strip() if pd.notna(row.get("district")) else ""
                desc = str(row.get("description", "")).strip() if pd.notna(row.get("description")) else ""

                if name and pd.notna(lat) and pd.notna(lon):
                    self.places.append({
                        "name": name,
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "category": cat,
                        "district": district,
                        "description": desc,
                    })
            logger.info(f"Loaded {len(self.places)} scenic places.")
        except Exception as e:
            logger.error(f"Error loading scenic places: {e}")

    def dense_interpolate_path(
        self,
        coords: List[Tuple[float, float]],
        step_km: float = 2.5
    ) -> List[Tuple[float, float]]:
        """
        Interpolates intermediate sample points between consecutive coordinates
        to form a continuous high-resolution corridor buffer.
        """
        if not coords or len(coords) < 2:
            return coords or []

        dense: List[Tuple[float, float]] = []
        for i in range(len(coords) - 1):
            c1 = coords[i]
            c2 = coords[i + 1]
            d = haversine(c1[0], c1[1], c2[0], c2[1])
            dense.append(c1)
            if d > step_km:
                steps = max(2, int(d / step_km))
                for s in range(1, steps):
                    frac = s / float(steps)
                    lat = c1[0] + frac * (c2[0] - c1[0])
                    lon = c1[1] + frac * (c2[1] - c1[1])
                    dense.append((lat, lon))
        dense.append(coords[-1])
        return dense

    def find_scenic_places_along_nodes(
        self,
        node_coords: List[Tuple[float, float]],
        corridor_radius_km: float = 7.5
    ) -> List[Dict[str, Any]]:
        """
        Finds all scenic places within corridor_radius_km of the continuous path trajectory.
        Automatically performs dense polyline interpolation between consecutive waypoints.
        """
        if not node_coords or not self.places:
            return []

        # Interpolate dense trajectory points along route
        dense_points = self.dense_interpolate_path(node_coords, step_km=2.5)

        matched_places = []
        seen_names = set()

        for sp in self.places:
            sp_lat = sp["latitude"]
            sp_lon = sp["longitude"]
            min_dist = float("inf")
            best_idx = 0

            for idx, (n_lat, n_lon) in enumerate(dense_points):
                d = haversine(sp_lat, sp_lon, n_lat, n_lon)
                if d < min_dist:
                    min_dist = d
                    best_idx = idx

            if min_dist <= corridor_radius_km:
                name_key = sp["name"].lower()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    # Journey progress fraction from 0.0 (origin) to 1.0 (destination)
                    progress = round(best_idx / max(1, len(dense_points) - 1), 2)
                    matched_places.append({
                        "name": sp["name"],
                        "lat": float(sp_lat),
                        "lon": float(sp_lon),
                        "latitude": float(sp_lat),
                        "longitude": float(sp_lon),
                        "category": sp["category"],
                        "district": sp["district"],
                        "distance_km": round(min_dist, 2),
                        "progress": progress,
                        "description": sp["description"]
                    })

        # Sort primarily by journey progress along route, secondarily by proximity
        matched_places.sort(key=lambda x: (x["progress"], x["distance_km"]))
        return matched_places

    def calculate_scenic_score(
        self,
        node_coords: List[Tuple[float, float]],
        total_distance_km: float,
        corridor_radius_km: float = 7.5,
        objective: str = "standard"
    ) -> Dict[str, Any]:
        """
        Calculates normalized scenic score (0-100) and extracts scenic attractions.
        Supports objective-specific factors (e.g. slower/leisure, fastest/express, rail).
        """
        # Objective adjustments
        obj_key = objective.lower().strip()
        radius = corridor_radius_km
        obj_multiplier = 1.0

        if obj_key in ("slower", "scenic"):
            radius = min(8.0, corridor_radius_km * 1.05)
            obj_multiplier = 1.10  # Leisurely journey pace with wide viewing exposure
        elif obj_key == "fastest":
            radius = max(4.5, corridor_radius_km * 0.80)
            obj_multiplier = 0.85  # High-speed bypass corridor with restricted viewing
        elif obj_key == "cheapest":
            obj_multiplier = 0.95
        elif obj_key == "rail":
            radius = min(6.5, corridor_radius_km * 0.90)
            obj_multiplier = 1.15  # Elevated scenic railway observation experience
        else:
            obj_multiplier = 1.00

        nearby = self.find_scenic_places_along_nodes(node_coords, radius)

        if not nearby:
            return {
                "scenic_score": 20,
                "scenic_rating": "Standard Transit Corridor",
                "total_scenic_places": 0,
                "scenic_places": []
            }

        # Calculate weighted attraction points
        raw_points = 0.0
        categories_seen = set()

        for p in nearby:
            cat_key = p["category"].lower()
            weight = self.CATEGORY_WEIGHTS.get(cat_key, 6.0)
            # Distance damping factor (closer attractions get full score)
            damping = max(0.35, 1.0 - (p["distance_km"] / (radius * 1.5)))
            raw_points += (weight * damping)
            categories_seen.add(cat_key)

        # Attraction density per km
        density = raw_points / max(15.0, total_distance_km)

        # Diversity multiplier: up to +18% bonus for broad category diversity
        div_multiplier = 1.0 + min(0.18, len(categories_seen) * 0.03)

        # Smooth saturation curve: maps 0.0 -> 20, 1.0 -> 50, 2.5 -> 70, 5.0 -> 88, 7.0+ -> 95
        base_score = 20.0 + (76.0 * density / (2.0 + density))
        adjusted_score = base_score * div_multiplier * obj_multiplier

        # Normalize score into [20, 96] range
        scenic_score = int(min(96, max(20, round(adjusted_score))))

        # Rating label
        if scenic_score >= 85:
            rating = "Exceptional Scenic Corridor (World-Class Vistas)"
        elif scenic_score >= 70:
            rating = "High Scenic Value (Picturesque Landscapes)"
        elif scenic_score >= 50:
            rating = "Moderate Scenic Value (Pleasant Transit Views)"
        else:
            rating = "Standard Transit Corridor"

        # Select geographically distributed highlights along journey progression
        if len(nearby) <= 12:
            selected_places = nearby
        else:
            # Sample evenly across the route from departure to destination
            step = len(nearby) / 12.0
            selected_places = [nearby[int(i * step)] for i in range(12)]

        return {
            "scenic_score": scenic_score,
            "scenic_rating": rating,
            "total_scenic_places": len(nearby),
            "scenic_places": selected_places
        }

scenic_service = ScenicService()
