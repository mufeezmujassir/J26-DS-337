from app.weather_model.suitability.activity_mapper import (
    map_activity_to_weather_profile,
)


def test_hiking_alias():
    assert map_activity_to_weather_profile("Trekking") == "hiking"


def test_safari_alias():
    assert map_activity_to_weather_profile("Wildlife Safari") == "wildlife_safari"


def test_water_activity_alias():
    assert map_activity_to_weather_profile("Snorkeling") == "water_activities"


def test_unknown_activity_is_not_guessed():
    assert map_activity_to_weather_profile("Unknown Experimental Activity") is None
