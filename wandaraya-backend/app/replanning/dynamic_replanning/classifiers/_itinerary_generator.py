"""Generate realistic, real-data-backed itineraries for the intent dataset."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.replanning.dynamic_replanning.classifiers import (
    DEFAULT_ACTIVITY_DURATION_MINUTES,
    DEFAULT_OPENING_HOURS,
    DURATION_NAMES,
    DURATION_VALUES,
    DURATION_WEIGHTS,
    HOTEL_COST_PER_NIGHT_USD,
    MIN_ATTRACTIONS_PER_DISTRICT,
    PERSONA_CATEGORIES,
    PERSONA_VIBE,
    PERSONAS,
    PERSONA_TOLERANCE,
    RAW_ATTRACTIONS_FILENAME,
    RAW_DIR,
    REQUIRED_ATTRACTION_FIELDS,
    TOLERANCES,
    TRANSPORT_COST_PER_DAY_USD,
    TRAVEL_BUFFER_MINUTES,
    load_jsonl,
)

LOGGER = logging.getLogger(__name__)

__all__ = [
    "ItineraryGenerator",
    "parse_opening_hours",
]


def parse_opening_hours(hours_str: str) -> tuple[int, int]:
    """Parse ``HH:MM-HH:MM`` into ``(start_minutes, end_minutes)``."""
    if not hours_str:
        return (480, 960)

    try:
        start_str, end_str = hours_str.split("-", 1)
        start_h, start_m = start_str.strip().split(":")
        end_h, end_m = end_str.strip().split(":")
        start_minutes = int(start_h) * 60 + int(start_m)
        end_minutes = int(end_h) * 60 + int(end_m)
    except (ValueError, IndexError, AttributeError):
        LOGGER.debug("Unrecognised opening hours '%s'; using default", hours_str)
        return (480, 960)

    if end_minutes <= start_minutes:
        LOGGER.debug("Opening hours %s have end <= start; clamping", hours_str)
        return (start_minutes, start_minutes + 8 * 60)

    return (start_minutes, end_minutes)


class ItineraryGenerator:
    """Generate realistic itineraries backed by real Sri Lankan attractions."""

    def __init__(self, attractions_path: str | Path, seed: int = 42) -> None:
        self.attractions_path = Path(attractions_path)
        self.seed = seed
        self.rng = import_random()
        self.rng.seed(seed)

        self.attractions: List[Dict[str, Any]] = []
        self.districts: List[str] = []
        self.district_centroids: Dict[str, tuple[float, float]] = {}
        self._load_attractions()

    def _load_attractions(self) -> None:
        if not self.attractions_path.is_file():
            raise FileNotFoundError(
                f"Real attractions file not found: {self.attractions_path}"
            )

        raw_rows = load_jsonl(self.attractions_path)
        validated: List[Dict[str, Any]] = []

        for row in raw_rows:
            missing = [f for f in REQUIRED_ATTRACTION_FIELDS if f not in row]
            if missing:
                LOGGER.debug(
                    "Skipping attraction %s due to missing fields: %s",
                    row.get("attraction_id"),
                    missing,
                )
                continue

            attraction: Dict[str, Any] = {
                "attraction_id": int(row["attraction_id"]),
                "name": str(row["name"]),
                "district": str(row["district"]),
                "district_id": row["district_id"],
                "category": str(row["category"]),
                "lat": float(row["lat"]),
                "lng": float(row["lng"]),
                "opening_hours": str(row.get("opening_hours", DEFAULT_OPENING_HOURS)),
                "entry_fee_usd": float(row.get("entry_fee_usd", 0.0)),
                "is_outdoor": bool(row.get("is_outdoor", False)),
                "duration_minutes": int(
                    row.get("duration_minutes", DEFAULT_ACTIVITY_DURATION_MINUTES)
                ),
            }
            validated.append(attraction)

        self.attractions = validated
        LOGGER.info("Loaded %d validated real attractions", len(self.attractions))

        self._build_district_index()

    def _build_district_index(self) -> None:
        districts_map: Dict[str, List[tuple[float, float]]] = {}

        for a in self.attractions:
            d = a["district"]
            if not d:
                continue
            districts_map.setdefault(d, []).append((a["lat"], a["lng"]))

        self.districts = sorted(districts_map)
        centroids: Dict[str, tuple[float, float]] = {}

        for d, coords in districts_map.items():
            if not coords:
                continue
            avg_lat = sum(c[0] for c in coords) / len(coords)
            avg_lng = sum(c[1] for c in coords) / len(coords)
            centroids[d] = (round(avg_lat, 6), round(avg_lng, 6))

        self.district_centroids = centroids
        LOGGER.debug(
            "Indexed %d districts with centroids", len(self.district_centroids)
        )

    def _district_distance_km(
        self, d1: str, d2: str
    ) -> Optional[float]:
        if d1 == d2:
            return 0.0
        c1 = self.district_centroids.get(d1)
        c2 = self.district_centroids.get(d2)
        if not c1 or not c2:
            return None
        return haversine_distance(c1[0], c1[1], c2[0], c2[1])

    def _get_districts_expanded(self, start_city: str) -> List[str]:
        ordered: List[str] = []
        if start_city in self.district_centroids:
            ordered.append(start_city)

        others: List[tuple[float, str]] = []
        for d in self.district_centroids:
            if d == start_city:
                continue
            dist = self._district_distance_km(start_city, d)
            if dist is None:
                dist = 10000.0
            others.append((dist, d))

        others.sort(key=lambda x: (x[0], x[1]))
        for dist, d in others:
            ordered.append(d)

        if not ordered and self.districts:
            ordered = list(self.districts)

        return ordered

    def _candidates_for_districts(
        self, districts_ordered: List[str], category_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        for d in districts_ordered:
            for a in self.attractions:
                if a["district"] != d:
                    continue
                if category_filter and a["category"] not in category_filter:
                    continue
                candidates.append(a)

        return candidates

    def generate_itinerary(
        self,
        persona: str,
        tolerance: str,
        start_city: str,
        duration_days: int,
    ) -> Dict[str, Any]:
        if persona not in PERSONAS:
            persona = self.rng.choice(PERSONAS)
        if tolerance not in TOLERANCES:
            tolerance = PERSONA_TOLERANCE.get(persona, self.rng.choice(TOLERANCES))

        districts_ordered = self._get_districts_expanded(start_city)
        categories = list(PERSONA_CATEGORIES.get(persona, PERSONAS) or PERSONAS)

        candidates = self._candidates_for_districts(districts_ordered, categories)
        if len(candidates) < MIN_ATTRACTIONS_PER_DISTRICT:
            candidates = self._candidates_for_districts(districts_ordered)
            LOGGER.debug(
                "Fallback to all categories for persona %s (limited pool in %s)",
                persona,
                start_city,
            )

        if not candidates:
            candidates = list(self.attractions)
            LOGGER.warning(
                "No candidates found for %s/%s; falling back to all attractions",
                persona,
                start_city,
            )

        open_start, open_end = parse_opening_hours(DEFAULT_OPENING_HOURS)
        activities_flat: List[Dict[str, Any]] = []
        slot = 0

        for day in range(1, duration_days + 1):
            n_acts = self.rng.randint(2, 4)
            cursor = open_start
            for _ in range(n_acts):
                if not candidates:
                    break
                base = self.rng.choice(candidates)
                duration_min = int(
                    base.get("duration_minutes", DEFAULT_ACTIVITY_DURATION_MINUTES)
                )
                start_min = cursor
                end_min = start_min + duration_min

                act: Dict[str, Any] = {
                    "slot": slot,
                    "day": day,
                    "attraction_id": base["attraction_id"],
                    "name": base["name"],
                    "category": base["category"],
                    "district": base["district"],
                    "lat": float(base["lat"]),
                    "lng": float(base["lng"]),
                    "start_minutes": start_min,
                    "end_minutes": end_min,
                    "time_slot": _format_time_slot(start_min, end_min),
                    "duration_minutes": duration_min,
                    "cost_usd": float(base.get("entry_fee_usd", 0.0)),
                    "is_outdoor": bool(base.get("is_outdoor", False)),
                    "is_must_see": False,
                }
                activities_flat.append(act)
                slot += 1
                cursor = end_min + TRAVEL_BUFFER_MINUTES

        if not activities_flat:
            base = candidates[0] if candidates else self.attractions[0]
            act = {
                "slot": 0,
                "day": 1,
                "attraction_id": base["attraction_id"],
                "name": base["name"],
                "category": base["category"],
                "district": base["district"],
                "lat": float(base["lat"]),
                "lng": float(base["lng"]),
                "start_minutes": open_start,
                "end_minutes": open_start + DEFAULT_ACTIVITY_DURATION_MINUTES,
                "time_slot": _format_time_slot(
                    open_start, open_start + DEFAULT_ACTIVITY_DURATION_MINUTES
                ),
                "duration_minutes": DEFAULT_ACTIVITY_DURATION_MINUTES,
                "cost_usd": float(base.get("entry_fee_usd", 0.0)),
                "is_outdoor": bool(base.get("is_outdoor", False)),
                "is_must_see": False,
            }
            activities_flat.append(act)

        must_see_list = self._select_must_see(activities_flat, categories, count=2)
        for act in activities_flat:
            if act["name"] in must_see_list or act["attraction_id"] in {
                a["attraction_id"] for a in self._find_by_names(activities_flat, must_see_list)
            }:
                act["is_must_see"] = True

        hotel_cost = HOTEL_COST_PER_NIGHT_USD * float(duration_days)
        transport_cost = TRANSPORT_COST_PER_DAY_USD * float(duration_days)
        activity_cost = sum(float(a["cost_usd"]) for a in activities_flat)
        cost_total = activity_cost + hotel_cost + transport_cost

        planned_budget = cost_total * self.rng.uniform(1.05, 1.35)
        planned_budget = round(planned_budget, 2)

        confirmed_bookings = [
            f"hotel_{start_city.replace(' ', '_')}_{self.rng.randint(1, 99):02d}",
            f"transport_{start_city.replace(' ', '_')}_{self.rng.randint(1, 99):02d}",
        ]

        itinerary_id = f"itin_{self.rng.randint(0, 9999):04d}"
        vibe = PERSONA_VIBE.get(persona, "mixed")

        days = _rebuild_days(list(activities_flat))

        return {
            "itinerary_id": itinerary_id,
            "persona": persona,
            "tolerance": tolerance,
            "start_city": start_city,
            "duration_days": int(duration_days),
            "vibe": vibe,
            "budget_total": planned_budget,
            "cost_total": round(cost_total, 2),
            "confirmed_bookings": confirmed_bookings,
            "must_see": list(must_see_list),
            "activities": activities_flat,
            "days": days,
        }

    def _select_must_see(
        self,
        activities_flat: List[Dict[str, Any]],
        categories: List[str],
        count: int = 2,
    ) -> List[str]:
        candidates = [
            a for a in activities_flat if a["category"] in categories
        ] or list(activities_flat)

        if len(candidates) < count:
            count = len(candidates)

        picks = self.rng.sample(candidates, count) if candidates else []
        return [p["name"] for p in picks]

    def _find_by_names(
        self, activities_flat: List[Dict[str, Any]], names: List[str]
    ) -> List[Dict[str, Any]]:
        name_set = set(names)
        return [a for a in activities_flat if a["name"] in name_set]

    def generate_batch(self, n: int) -> List[Dict[str, Any]]:
        itineraries: List[Dict[str, Any]] = []

        for _ in range(n):
            persona = self.rng.choice(PERSONAS)
            tolerance = PERSONA_TOLERANCE.get(persona, self.rng.choice(TOLERANCES))
            if self.districts:
                start_city = self.rng.choice(self.districts)
            else:
                start_city = self.rng.choice([a["district"] for a in self.attractions if a["district"]] or ["Kandy"])
            duration_days = self.rng.choices(
                list(DURATION_VALUES), weights=list(DURATION_WEIGHTS), k=1
            )[0]
            itineraries.append(
                self.generate_itinerary(persona, tolerance, start_city, duration_days)
            )

        return itineraries


def _format_time_slot(start_min: int, end_min: int) -> str:
    def fmt(m: int) -> str:
        h = m // 60
        mm = m % 60
        return f"{h:02d}:{mm:02d}"

    return f"{fmt(start_min)}-{fmt(end_min)}"


def _rebuild_days(activities_flat: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_day: Dict[int, List[Dict[str, Any]]] = {}
    for a in activities_flat:
        by_day.setdefault(a["day"], []).append(dict(a))

    days: List[Dict[str, Any]] = []
    for d in sorted(by_day):
        acts = sorted(by_day[d], key=lambda x: (x["start_minutes"], x["slot"]))
        days.append({"day": d, "activities": acts})
    return days


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in kilometres."""
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
        d_lam / 2
    ) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(radius_km * c, 3)


def import_random():
    import random

    return random.Random()