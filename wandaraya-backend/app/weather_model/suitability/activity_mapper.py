"""Map Tourism Knowledge Base activity names to weather scoring profiles."""

from __future__ import annotations

import re

from app.weather_model.suitability.activity_profiles import ACTIVITY_PROFILES


ACTIVITY_ALIASES = {
    "hiking": "hiking",
    "trekking": "hiking",
    "nature walking": "hiking",
    "mountain hiking": "hiking",
    "beach": "beach",
    "beach relaxation": "beach",
    "sunbathing": "beach",
    "safari": "wildlife_safari",
    "wildlife safari": "wildlife_safari",
    "wildlife watching": "wildlife_safari",
    "sightseeing": "cultural_outdoor",
    "heritage walk": "cultural_outdoor",
    "cultural sightseeing": "cultural_outdoor",
    "historical sightseeing": "cultural_outdoor",
    "swimming": "water_activities",
    "snorkeling": "water_activities",
    "surfing": "water_activities",
    "boat riding": "water_activities",
    "museum visit": "indoor_museum",
    "museum": "indoor_museum",
    "indoor museum": "indoor_museum",
}


def normalize_activity_name(name: str) -> str:
    value = name.strip().lower()
    value = re.sub(r"[_-]+", " ", value)
    return re.sub(r"\s+", " ", value)


def map_activity_to_weather_profile(activity_name: str) -> str | None:
    """Return a known profile key; leave unknown KB vocabulary unmapped."""
    normalized = normalize_activity_name(activity_name)
    if normalized in ACTIVITY_ALIASES:
        return ACTIVITY_ALIASES[normalized]

    profile_key = normalized.replace(" ", "_")
    return profile_key if profile_key in ACTIVITY_PROFILES else None
