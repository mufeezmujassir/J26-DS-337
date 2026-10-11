"""Map Tourism Knowledge Base activity names to weather scoring profiles."""

from __future__ import annotations

import re

from app.weather_model.suitability.activity_profiles import ACTIVITY_PROFILES


ACTIVITY_ALIASES = {
    "agricultural experience": "agricultural_outdoor",
    "ayurvedic treatment": "wellness",
    "beach relaxation": "beach",
    "bird watching": "wildlife_safari",
    "boating": "water_activities",
    "camping": "outdoor_recreation",
    "caving": "outdoor_recreation",
    "cooking class": "indoor_leisure",
    "cultural experience": "cultural_outdoor",
    "cycling": "outdoor_recreation",
    "dolphin watching": "marine_activities",
    "educational visit": "indoor_museum",
    "event participation": "event_outdoor",
    "family recreation": "outdoor_recreation",
    "festival participation": "event_outdoor",
    "food tasting": "indoor_leisure",
    "handicraft experience": "indoor_leisure",
    "heritage exploration": "cultural_outdoor",
    "hiking": "hiking",
    "historical exploration": "cultural_outdoor",
    "kayaking": "water_activities",
    "local food experience": "indoor_leisure",
    "local market visit": "cultural_outdoor",
    "meditation": "wellness",
    "museum visit": "indoor_museum",
    "nightlife": "indoor_leisure",
    "photography": "photography_outdoor",
    "plantation tour": "agricultural_outdoor",
    "river rafting": "water_activities",
    "rock climbing": "hiking",
    "scenic viewpoint": "photography_outdoor",
    "scuba diving": "marine_activities",
    "shopping": "indoor_leisure",
    "sightseeing": "cultural_outdoor",
    "snorkeling": "water_activities",
    "spa and wellness": "wellness",
    "stargazing": "photography_outdoor",
    "sunrise viewing": "photography_outdoor",
    "sunset viewing": "photography_outdoor",
    "surfing": "marine_activities",
    "swimming": "water_activities",
    "tea factory visit": "indoor_museum",
    "tea tasting": "indoor_leisure",
    "temple visit": "cultural_outdoor",
    "train journey": "indoor_leisure",
    "trekking": "hiking",
    "waterfall visit": "photography_outdoor",
    "whale watching": "marine_activities",
    "wildlife safari": "wildlife_safari",
    "yoga": "wellness",
    # Compatibility aliases outside the 50-name KB vocabulary.
    "nature walking": "hiking",
    "mountain hiking": "hiking",
    "beach": "beach",
    "beach relaxation": "beach",
    "sunbathing": "beach",
    "safari": "wildlife_safari",
    "wildlife watching": "wildlife_safari",
    "heritage walk": "cultural_outdoor",
    "cultural sightseeing": "cultural_outdoor",
    "historical sightseeing": "cultural_outdoor",
    "boat riding": "water_activities",
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
