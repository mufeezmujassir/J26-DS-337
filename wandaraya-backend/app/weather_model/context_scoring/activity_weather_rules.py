"""Activity exposure profiles for the separate weather context dimension."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityWeatherRule:
    ideal_min_c: float
    ideal_max_c: float
    rain_weight: float
    probability_weight: float
    temperature_weight: float


RULES = {
    "hiking": ActivityWeatherRule(18, 30, 0.70, 0.60, 0.40),
    "beach": ActivityWeatherRule(24, 33, 0.65, 0.55, 0.35),
    "wildlife_safari": ActivityWeatherRule(20, 32, 0.60, 0.50, 0.30),
    "heritage_site": ActivityWeatherRule(20, 33, 0.35, 0.30, 0.25),
    "water_activities": ActivityWeatherRule(24, 32, 0.75, 0.65, 0.30),
    "indoor_attraction": ActivityWeatherRule(18, 35, 0.05, 0.05, 0.10),
}

ALIASES = {
    "trekking": "hiking",
    "beaches": "beach",
    "safari": "wildlife_safari",
    "heritage": "heritage_site",
    "cultural_outdoor": "heritage_site",
    "museum": "indoor_attraction",
    "indoor_museum": "indoor_attraction",
    "water_activity": "water_activities",
}


def get_rule(activity: str) -> tuple[str, ActivityWeatherRule]:
    normalized = activity.strip().lower().replace("-", "_").replace(" ", "_")
    canonical = ALIASES.get(normalized, normalized)
    try:
        return canonical, RULES[canonical]
    except KeyError as exc:
        raise ValueError(f"Unsupported weather activity: {activity}") from exc
