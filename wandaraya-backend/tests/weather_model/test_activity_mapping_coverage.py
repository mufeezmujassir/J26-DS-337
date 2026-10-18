import pytest

from app.weather_model.suitability.activity_mapper import (
    map_activity_to_weather_profile,
)
from app.weather_model.suitability.activity_profiles import ACTIVITY_PROFILES


DATABASE_ACTIVITIES = [
    "Agricultural Experience", "Ayurvedic Treatment", "Beach Relaxation",
    "Bird Watching", "Boating", "Camping", "Caving", "Cooking Class",
    "Cultural Experience", "Cycling", "Dolphin Watching", "Educational Visit",
    "Event Participation", "Family Recreation", "Festival Participation",
    "Food Tasting", "Handicraft Experience", "Heritage Exploration", "Hiking",
    "Historical Exploration", "Kayaking", "Local Food Experience",
    "Local Market Visit", "Meditation", "Museum Visit", "Nightlife", "Photography",
    "Plantation Tour", "River Rafting", "Rock Climbing", "Scenic Viewpoint",
    "Scuba Diving", "Shopping", "Sightseeing", "Snorkeling", "Spa and Wellness",
    "Stargazing", "Sunrise Viewing", "Sunset Viewing", "Surfing", "Swimming",
    "Tea Factory Visit", "Tea Tasting", "Temple Visit", "Train Journey", "Trekking",
    "Waterfall Visit", "Whale Watching", "Wildlife Safari", "Yoga",
]


@pytest.mark.parametrize("activity_name", DATABASE_ACTIVITIES)
def test_all_database_activities_have_valid_profiles(activity_name):
    mapped_profile = map_activity_to_weather_profile(activity_name)
    assert mapped_profile is not None, f"Unmapped activity: {activity_name}"
    assert mapped_profile in ACTIVITY_PROFILES, f"Missing weather profile: {mapped_profile}"


def test_exactly_50_database_activities():
    assert len(DATABASE_ACTIVITIES) == 50


def test_unknown_activity_is_not_guessed():
    assert map_activity_to_weather_profile("Unknown Future Activity") is None
