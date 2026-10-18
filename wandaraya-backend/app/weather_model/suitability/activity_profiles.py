"""Initial, reviewable weather-sensitivity profiles for tourism activities."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityWeatherProfile:
    """Baseline engineering assumptions, pending domain-expert validation."""

    activity_type: str
    rain_sensitivity: float
    temperature_sensitivity: float
    ideal_temp_min_c: float
    ideal_temp_max_c: float


ACTIVITY_PROFILES = {
    "hiking": ActivityWeatherProfile("hiking", 1.0, 0.8, 18.0, 28.0),
    "beach": ActivityWeatherProfile("beach", 0.9, 0.7, 25.0, 33.0),
    "wildlife_safari": ActivityWeatherProfile(
        "wildlife_safari", 0.8, 0.7, 20.0, 32.0
    ),
    "cultural_outdoor": ActivityWeatherProfile(
        "cultural_outdoor", 0.7, 0.6, 20.0, 32.0
    ),
    "water_activities": ActivityWeatherProfile(
        "water_activities", 0.9, 0.5, 25.0, 33.0
    ),
    "indoor_museum": ActivityWeatherProfile(
        "indoor_museum", 0.1, 0.1, 20.0, 34.0
    ),
    "photography_outdoor": ActivityWeatherProfile(
        "photography_outdoor", 0.7, 0.5, 20.0, 32.0
    ),
    "outdoor_recreation": ActivityWeatherProfile(
        "outdoor_recreation", 0.8, 0.7, 20.0, 31.0
    ),
    "agricultural_outdoor": ActivityWeatherProfile(
        "agricultural_outdoor", 0.7, 0.6, 20.0, 32.0
    ),
    "indoor_leisure": ActivityWeatherProfile(
        "indoor_leisure", 0.1, 0.1, 20.0, 34.0
    ),
    "wellness": ActivityWeatherProfile("wellness", 0.3, 0.3, 22.0, 32.0),
    "marine_activities": ActivityWeatherProfile(
        "marine_activities", 0.9, 0.6, 24.0, 33.0
    ),
    "event_outdoor": ActivityWeatherProfile(
        "event_outdoor", 0.7, 0.6, 20.0, 33.0
    ),
}
