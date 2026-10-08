"""Tests for the Wandaraya disruption detection module."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest
import requests
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.replanning.disruption_detection import weather_monitor as weather_mod  # noqa: E402
from app.replanning.disruption_detection import places_monitor as places_mod  # noqa: E402
from app.replanning.disruption_detection.complaint_detector import (  # noqa: E402
    ComplaintDetector,
)
from app.replanning.disruption_detection.gps_monitor import GpsMonitor  # noqa: E402
from app.replanning.disruption_detection.places_monitor import (  # noqa: E402
    PlacesMonitor,
)
from app.replanning.disruption_detection.weather_monitor import (  # noqa: E402
    WeatherMonitor,
)
from app.replanning.disruption_detection import utils as dm_utils  # noqa: E402
from app.replanning.disruption_detection import (  # noqa: E402
    AffectedElement,
    Disruption,
    DisruptionBatch,
    DisruptionReason,
)
from app.schemas import disruption as dm_models  # noqa: E402


def make_disruption(**overrides: Any) -> Dict[str, Any]:
    """Build a valid disruption dictionary for model tests."""
    payload: Dict[str, Any] = {
        "disruption_id": "d-001",
        "source": "weather",
        "category": "weather",
        "severity": "step",
        "affected_element": {
            "activity_name": "Sigiriya climb",
            "time_slot": "09:00-11:00",
            "day": "Day 2",
            "location": "Sigiriya",
        },
        "reason": {
            "short": "Heavy rain expected",
            "description": "Rain duration exceeds 3 hour threshold",
            "details": "OpenWeather reports 4.5 rain hours",
        },
        "confidence": 0.82,
        "requires_confirmation": False,
        "detected_at": datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    """Minimal stand-in for a ``requests.Response``."""

    def __init__(self, payload: Any = None, ok: bool = True) -> None:
        self._payload = payload
        self._ok = ok

    def raise_for_status(self) -> None:
        if not self._ok:
            raise requests.RequestException("HTTP 500")

    def json(self) -> Any:
        return self._payload


def weather_payload(
    description: str = "clear sky",
    temperature: float = 28.0,
    rain: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    return {
        "weather": [{"description": description}],
        "main": {"temp": temperature},
        "rain": rain or {},
    }


def places_payload(
    business_status: str = "OPERATIONAL",
    open_now: bool = True,
    total_ratings: int = 0,
) -> Dict[str, Any]:
    return {
        "result": {
            "place_id": "ChIJx",
            "name": "Test Place",
            "business_status": business_status,
            "current_opening_hours": {"open_now": open_now},
            "user_ratings_total": total_ratings,
        }
    }



# Weather monitor

def test_weather_signal_clear_sky(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear sky produces a neutral rain signal without heat warning."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
    with mock.patch.object(
        weather_mod.requests, "get", return_value=FakeResponse(weather_payload())
    ):
        signal = WeatherMonitor().monitor(6.9271, 79.8612)

    assert signal["rain_intensity"] == "none"
    assert signal["rain_duration_hours"] == 0.0
    assert signal["temperature_celsius"] == 28.0
    assert signal["heat_warning"] is False


def test_weather_signal_light_rain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Light rain maps to the light intensity with a 1h duration heuristic."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
    payload = weather_payload(description="light rain", rain={"1h": 1.2})
    with mock.patch.object(
        weather_mod.requests, "get", return_value=FakeResponse(payload)
    ):
        signal = WeatherMonitor().monitor(6.9271, 79.8612)

    assert signal["rain_intensity"] == "light"
    assert signal["rain_duration_hours"] == 1.0


def test_weather_signal_storm_triggers_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """A thunderstorm drives duration over the 3h rule threshold."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
    payload = weather_payload(
        description="thunderstorm with heavy rain",
        temperature=36.0,
        rain={"3h": 12.0},
    )
    with mock.patch.object(
        weather_mod.requests, "get", return_value=FakeResponse(payload)
    ):
        signal = WeatherMonitor().monitor(6.9271, 79.8612)

    assert signal["rain_intensity"] == "storm"
    assert signal["rain_duration_hours"] == 4.0
    assert signal["heat_warning"] is True


def test_weather_heat_warning_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Heat warning flips exactly at the configured 35C threshold."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
    for temperature, expected in ((34.9, False), (35.0, True)):
        payload = weather_payload(temperature=temperature)
        with mock.patch.object(
            weather_mod.requests, "get", return_value=FakeResponse(payload)
        ):
            signal = WeatherMonitor().monitor(6.9271, 79.8612)
        assert signal["heat_warning"] is expected


def test_weather_api_error_returns_neutral_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP errors degrade gracefully instead of raising."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
    with mock.patch.object(
        weather_mod.requests, "get", return_value=FakeResponse(ok=False)
    ):
        signal = WeatherMonitor().monitor(6.9271, 79.8612)

    assert signal == {
        "rain_duration_hours": 0.0,
        "rain_intensity": "none",
        "temperature_celsius": 0.0,
        "heat_warning": False,
    }


def test_weather_missing_api_key_skips_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without an API key the monitor returns neutral and never calls out."""
    monkeypatch.setattr(dm_utils, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    fake_get = mock.Mock()

    with mock.patch.object(weather_mod.requests, "get", fake_get):
        signal = WeatherMonitor().monitor(6.9271, 79.8612)

    assert signal["rain_intensity"] == "none"
    fake_get.assert_not_called()



# Places monitor

def test_places_open_high_crowd(monkeypatch: pytest.MonkeyPatch) -> None:
    """An open, heavily reviewed place reads as high crowd + capacity issue."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    payload = places_payload(total_ratings=2550)

    with mock.patch.object(
        places_mod.requests, "get", return_value=FakeResponse(payload)
    ):
        signal = PlacesMonitor().monitor(place_id="ChIJx")

    assert signal["is_open"] is True
    assert signal["closure_flag"] is False
    assert signal["crowd_level"] == "high"
    assert signal["capacity_issue"] is True


def test_places_closed_temporarily(monkeypatch: pytest.MonkeyPatch) -> None:
    """A temporarily closed place is closed, no capacity issue."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    payload = places_payload(business_status="CLOSED_TEMPORARILY")

    with mock.patch.object(
        places_mod.requests, "get", return_value=FakeResponse(payload)
    ):
        signal = PlacesMonitor().monitor(place_id="ChIJx")

    assert signal["is_open"] is False
    assert signal["closure_flag"] is True
    assert signal["crowd_level"] == "low"
    assert signal["capacity_issue"] is False


def test_places_open_now_false_is_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operational but not currently open still flags a closure."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    payload = places_payload(open_now=False, total_ratings=500)

    with mock.patch.object(
        places_mod.requests, "get", return_value=FakeResponse(payload)
    ):
        signal = PlacesMonitor().monitor(place_id="ChIJx")

    assert signal["is_open"] is False
    assert signal["closure_flag"] is True


def test_places_crowd_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crowd proxy follows the review-volume thresholds."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    for ratings, expected in ((10, "low"), (200, "medium"), (2000, "high")):
        payload = places_payload(total_ratings=ratings)
        with mock.patch.object(
            places_mod.requests, "get", return_value=FakeResponse(payload)
        ):
            signal = PlacesMonitor().monitor(place_id="ChIJx")
        assert signal["crowd_level"] == expected


def test_places_by_name_resolves_then_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A free-text name triggers find-place-then-details (two calls)."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    find_response = FakeResponse({"candidates": [{"place_id": "ChIJy"}]})
    detail_response = FakeResponse(
        places_payload(total_ratings=200)
    )

    with mock.patch.object(
        places_mod.requests,
        "get",
        side_effect=[find_response, detail_response],
    ) as fake_get:
        signal = PlacesMonitor().monitor(place_name="Temple of the Tooth")

    assert fake_get.call_count == 2
    assert signal["is_open"] is True
    assert signal["crowd_level"] == "medium"


def test_places_missing_api_key_skips_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without an API key the monitor returns neutral and never calls out."""
    monkeypatch.setattr(dm_utils, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    fake_get = mock.Mock()

    with mock.patch.object(places_mod.requests, "get", fake_get):
        signal = PlacesMonitor().monitor(place_name="X")

    assert signal["is_open"] is False
    assert signal["closure_flag"] is False
    fake_get.assert_not_called()



# GPS monitor

def test_gps_no_deviation_when_on_route() -> None:
    """Sitting on the planned waypoint yields zero deviation."""
    signal = GpsMonitor().monitor(
        latitude=6.9271,
        longitude=79.8612,
        planned_waypoints=[{"lat": 6.9271, "lon": 79.8612}],
    )

    assert signal["gps_deviation_km"] == 0.0
    assert signal["off_route"] is False


def test_gps_off_route_beyond_threshold() -> None:
    """Deviation beyond 5 km marks the traveller off-route."""
    signal = GpsMonitor().monitor(
        latitude=6.9271,
        longitude=79.8612,
        planned_waypoints=[{"lat": 7.2906, "lon": 80.6337}],
    )

    assert signal["off_route"] is True
    assert signal["gps_deviation_km"] > 5.0


def test_gps_running_late_over_threshold() -> None:
    """A 90 minute delay is flagged as running late."""
    signal = GpsMonitor().monitor(
        latitude=6.9271,
        longitude=79.8612,
        scheduled_at="09:00",
        actual_at="10:30",
    )

    assert signal["time_delay_minutes"] == 90
    assert signal["running_late"] is True


def test_gps_tolerable_delay_not_late() -> None:
    """A 30 minute delay stays under the 60 minute threshold."""
    signal = GpsMonitor().monitor(
        latitude=6.9271,
        longitude=79.8612,
        scheduled_at="09:00",
        actual_at="09:30",
    )

    assert signal["time_delay_minutes"] == 30
    assert signal["running_late"] is False


def test_gps_missing_fix_is_neutral() -> None:
    """No GPS fix degrades to a neutral signal without raising."""
    signal = GpsMonitor().monitor(latitude=None, longitude=None)

    assert signal == {
        "gps_deviation_km": 0.0,
        "time_delay_minutes": 0,
        "off_route": False,
        "running_late": False,
    }


def test_gps_no_waypoints_zero_deviation() -> None:
    """Missing route data does not trigger a false off-route flag."""
    signal = GpsMonitor().monitor(latitude=6.9271, longitude=79.8612)

    assert signal["gps_deviation_km"] == 0.0
    assert signal["off_route"] is False



# Complaint detector

def test_complaint_clean_message_is_neutral() -> None:
    """An innocent message scores zero and falls back to other."""
    signal = ComplaintDetector().monitor("We loved the temple today!")

    assert signal["complaint_score"] == 0.0
    assert signal["keywords_found"] == []
    assert signal["category"] == "other"
    assert signal["change_request"] is False


def test_complaint_attraction_closed() -> None:
    """The museum is closed flags an attraction complaint."""
    signal = ComplaintDetector().monitor("The museum is closed")

    assert signal["keywords_found"] == ["closed"]
    assert signal["complaint_score"] == 0.2
    assert signal["category"] == "attraction"


def test_complaint_transport_late_stuck() -> None:
    """Late + stuck in traffic reads as a transport complaint."""
    signal = ComplaintDetector().monitor("we are late and stuck in traffic")

    assert set(signal["keywords_found"]) == {"late", "stuck"}
    assert signal["complaint_score"] == 0.4
    assert signal["category"] == "transport"


def test_complaint_change_request() -> None:
    """Change phrases raise the change_request flag and score."""
    signal = ComplaintDetector().monitor("let's go elsewhere instead")

    assert signal["change_request"] is True
    assert signal["complaint_score"] == 0.3
    assert signal["category"] == "other"


def test_complaint_score_capped_at_one() -> None:
    """Enough keywords cap the complaint score at 1.0."""
    signal = ComplaintDetector().monitor(
        "closed crowded boring expensive everyone is late and stuck"
    )

    assert signal["complaint_score"] == 1.0


def test_complaint_weather_category_even_without_match() -> None:
    """Category is classified even when no scoring keyword hits."""
    signal = ComplaintDetector().monitor("it is raining and flooded")

    assert signal["category"] == "weather"
    assert signal["complaint_score"] == 0.0


def test_complaint_word_boundary_no_false_positive() -> None:
    """'late' must not match the middle of 'translated'."""
    signal = ComplaintDetector().monitor("please translate this into English")

    assert signal["keywords_found"] == []
    assert signal["complaint_score"] == 0.0


def test_complaint_empty_message_neutral() -> None:
    """An empty message is handled gracefully."""
    signal = ComplaintDetector().monitor()

    assert signal["complaint_score"] == 0.0
    assert signal["keywords_found"] == []
    assert signal["change_request"] is False


# Config
def test_load_config_finds_module_config_yaml() -> None:
    config = dm_utils.load_config("config.yaml")

    assert isinstance(config, dict)
    assert config["weather"]["api_key_env"] == "OPENWEATHER_API_KEY"
    assert config["places"]["api_key_env"] == "GOOGLE_PLACES_API_KEY"


def test_load_config_contains_fusion_weights() -> None:
    config = dm_utils.load_config("config.yaml")

    weights = config["fusion"]["weights"]
    assert weights == {
        "weather": 0.30,
        "places": 0.30,
        "complaint": 0.25,
        "gps": 0.15,
    }
    assert config["fusion"]["confirmation_threshold"] == 0.75


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dm_utils.load_config(str(tmp_path / "nope.yaml"))


def test_load_config_non_mapping_root_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")

    with pytest.raises(ValueError):
        dm_utils.load_config(str(bad))


# Haversine
def test_haversine_zero_distance() -> None:
    assert dm_utils.haversine_distance(6.9271, 79.8612, 6.9271, 79.8612) == 0.0


def test_haversine_one_degree_longitude() -> None:
    distance = dm_utils.haversine_distance(0.0, 0.0, 0.0, 1.0)

    assert distance == pytest.approx(111.195, abs=0.5)


def test_haversine_colombo_to_kandy() -> None:
    distance = dm_utils.haversine_distance(6.9271, 79.8612, 7.2906, 80.6337)

    assert 90.0 <= distance <= 120.0


# Time diff
def test_time_diff_minutes_basic() -> None:
    start = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)

    assert dm_utils.time_diff_minutes(start, end) == 90


def test_time_diff_minutes_string_times() -> None:
    assert dm_utils.time_diff_minutes("09:00", "10:30") == 90


def test_time_diff_minutes_negative_when_reversed() -> None:
    start = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)

    assert dm_utils.time_diff_minutes(start, end) == -60


def test_time_diff_minutes_invalid_string_raises() -> None:
    with pytest.raises(ValueError):
        dm_utils.time_diff_minutes("not-a-time", "10:00")


# Env keys
def test_get_env_api_key_returns_existing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key-123")

    assert dm_utils.get_env_api_key("OPENWEATHER_API_KEY") == "test-key-123"


def test_get_env_api_key_missing_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(dm_utils, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)

    assert dm_utils.get_env_api_key("OPENWEATHER_API_KEY") == ""


def test_get_env_api_key_reads_repo_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pytest.importorskip("dotenv")
    (tmp_path / ".env").write_text(
        "OPENWEATHER_API_KEY=from-dotenv-file\n", encoding="utf-8"
    )
    monkeypatch.setattr(dm_utils, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)

    assert dm_utils.get_env_api_key("OPENWEATHER_API_KEY") == "from-dotenv-file"


def test_no_new_env_variables_introduced() -> None:
    config = dm_utils.load_config("config.yaml")

    assert config["weather"]["api_key_env"] == "OPENWEATHER_API_KEY"
    assert config["places"]["api_key_env"] == "GOOGLE_PLACES_API_KEY"
    assert "api_key" not in config["weather"]
    assert "api_key" not in config["places"]


# Log formatting
def test_format_disruption_log_contains_key_fields() -> None:
    disruption = make_disruption()
    line = dm_utils.format_disruption_log(disruption)

    assert "d-001" in line
    assert "step" in line
    assert "weather" in line
    assert "conf=0.82" in line
    assert "Heavy rain expected" in line


def test_format_disruption_log_tolerates_reason_object() -> None:
    reason = DisruptionReason(
        short="Closed",
        description="Attraction closed",
        details="Places API reported opening_status",
    )
    line = dm_utils.format_disruption_log(
        {"disruption_id": "d-9", "reason": reason, "confidence": 1.0}
    )

    assert "d-9" in line
    assert "Closed" in line


# Schemas
def test_affected_element_schema() -> None:
    element = AffectedElement(
        activity_name="Temple of the Tooth",
        time_slot="14:00-15:30",
        day="Day 3",
        location="Kandy",
    )

    assert element.activity_name == "Temple of the Tooth"
    assert element.location == "Kandy"


def test_disruption_schema_roundtrip() -> None:
    disruption = Disruption.model_validate(make_disruption())

    assert disruption.severity in dm_models.SEVERITIES
    assert disruption.source in dm_models.SOURCES
    assert disruption.category in dm_models.CATEGORIES
    assert disruption.confidence == pytest.approx(0.82)

    dumped = disruption.model_dump()
    assert dumped["affected_element"]["day"] == "Day 2"
    assert dumped["reason"]["short"] == "Heavy rain expected"


def test_disruption_confidence_out_of_range_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Disruption.model_validate(make_disruption(confidence=1.5))

    with pytest.raises(ValidationError):
        Disruption.model_validate(make_disruption(confidence=-0.1))


def test_disruption_missing_field_rejected() -> None:
    from pydantic import ValidationError

    payload = make_disruption()
    del payload["affected_element"]

    with pytest.raises(ValidationError):
        Disruption.model_validate(payload)


def test_disruption_batch_schema() -> None:
    disruption = Disruption.model_validate(make_disruption())
    batch = DisruptionBatch(
        disruptions=[disruption],
        detected_at=datetime(2026, 10, 8, 9, 5, tzinfo=timezone.utc),
    )

    assert len(batch.disruptions) == 1
    assert batch.detected_at.year == 2026


def test_severity_vocabulary_matches_contract() -> None:
    assert dm_models.SEVERITIES == ("step", "day", "plan")
    assert dm_models.SOURCES == ("weather", "places", "complaint", "gps")
    assert dm_models.CATEGORIES == (
        "weather",
        "attraction",
        "transport",
        "user_report",
    )


def test_schemas_live_in_app_schemas_per_project_structure() -> None:
    assert dm_models.Disruption is Disruption
    assert dm_models.AffectedElement is AffectedElement
    assert dm_models.SOURCES == ("weather", "places", "complaint", "gps")


def test_no_module_local_models_package_exists() -> None:
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(
            "app.replanning.disruption_detection.models"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    sys.exit(pytest.main([__file__, "-v"]))