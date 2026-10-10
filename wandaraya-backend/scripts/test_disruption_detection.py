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
from app.replanning.disruption_detection.severity_classifier import (  # noqa: E402
    SEVERITY_ORDER,
    classify_severity,
    rank as severity_rank,
)
from app.replanning.disruption_detection import trigger_rules as rules_mod  # noqa: E402
from app.replanning.disruption_detection.trigger_rules import (  # noqa: E402
    RULES,
    apply_rules,
    get_rule,
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


def signals(
    weather: Dict[str, Any] | None = None,
    places: Dict[str, Any] | None = None,
    gps: Dict[str, Any] | None = None,
    complaint: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a merged signal dict, overlaying defaults with partials."""
    base: Dict[str, Any] = {
        "weather": {
            "rain_duration_hours": 0.0,
            "rain_intensity": "none",
            "temperature_celsius": 28.0,
            "heat_warning": False,
        },
        "places": {
            "is_open": True,
            "closure_flag": False,
            "capacity_issue": False,
            "crowd_level": "low",
        },
        "gps": {
            "gps_deviation_km": 0.0,
            "time_delay_minutes": 0,
            "off_route": False,
            "running_late": False,
        },
        "complaint": {
            "complaint_score": 0.0,
            "keywords_found": [],
            "category": "other",
            "change_request": False,
        },
        "context": {
            "is_outdoor": False,
            "closures_today": 0,
            "hotel_overbooked": False,
            "city_change_requested": False,
        },
    }
    for key, overlay in (
        ("weather", weather),
        ("places", places),
        ("gps", gps),
        ("complaint", complaint),
        ("context", context),
    ):
        if overlay is not None:
            base[key] = {**base[key], **overlay}
    return base


def fired_names(rule_outputs: list) -> set[str]:
    return {entry["name"] for entry in rule_outputs}



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


# ---------------------------------------------------------------------------
# 11. Trigger rules
# ---------------------------------------------------------------------------


def test_rules_count_and_names() -> None:
    """The module ships the eight documented rules."""
    assert len(RULES) == 8
    assert {rule.name for rule in RULES} == {
        "rain_3h_outdoor",
        "attraction_closed",
        "multi_closure",
        "gps_off_route",
        "time_delay_major",
        "complaint_detected",
        "change_request_detected",
        "city_change_required",
    }


def test_rules_have_valid_metadata() -> None:
    """Every rule carries valid severity, source and category."""
    valid_sources = {"weather", "places", "gps", "complaint"}
    valid_categories = {
        "weather",
        "attraction",
        "transport",
        "user_report",
    }

    for rule in RULES:
        assert rule.severity in {"step", "day", "plan"}
        assert rule.source in valid_sources
        assert rule.category in valid_categories or callable(rule.category)
        assert callable(rule.condition)
        assert callable(rule.describe)


def test_rule_thresholds_come_from_config() -> None:
    """Rule thresholds mirror config.yaml values."""
    config = dm_utils.load_config("config.yaml")

    assert rules_mod.RAIN_THRESHOLD_HOURS == config["weather"]["rain_threshold_hours"]
    assert rules_mod.GPS_DEVIATION_THRESHOLD_KM == config["gps"]["deviation_threshold_km"]
    assert rules_mod.DELAY_THRESHOLD_MINUTES == config["gps"]["delay_threshold_minutes"]


def test_rain_3h_outdoor_fires() -> None:
    """Over-3h rain on an outdoor activity fires the weather rule."""
    fired = apply_rules(
        signals(
            weather={"rain_duration_hours": 4.0},
            context={"is_outdoor": True},
        )
    )

    assert "rain_3h_outdoor" in fired_names(fired)
    assert next(r for r in fired if r["name"] == "rain_3h_outdoor")["severity"] == "step"


def test_rain_indoor_does_not_fire() -> None:
    """Rain alone does not fire unless the activity is outdoor."""
    fired = apply_rules(
        signals(
            weather={"rain_duration_hours": 4.0},
            context={"is_outdoor": False},
        )
    )

    assert "rain_3h_outdoor" not in fired_names(fired)


def test_rain_at_threshold_does_not_fire() -> None:
    """Duration equal to the threshold is not a trigger."""
    fired = apply_rules(
        signals(
            weather={"rain_duration_hours": 3.0},
            context={"is_outdoor": True},
        )
    )

    assert "rain_3h_outdoor" not in fired_names(fired)


def test_attraction_closed_fires() -> None:
    """A closed attraction fires the step-level closure rule."""
    fired = apply_rules(signals(places={"is_open": False}))

    assert "attraction_closed" in fired_names(fired)


def test_multi_closure_fires_day() -> None:
    """Two closures today escalate to day severity."""
    fired = apply_rules(
        signals(context={"closures_today": 2})
    )

    assert "multi_closure" in fired_names(fired)
    assert next(r for r in fired if r["name"] == "multi_closure")["severity"] == "day"


def test_gps_off_route_fires_over_threshold() -> None:
    """Deviation beyond 5 km fires; exactly 5 km does not."""
    assert "gps_off_route" in fired_names(
        apply_rules(signals(gps={"gps_deviation_km": 5.5}))
    )
    assert "gps_off_route" not in fired_names(
        apply_rules(signals(gps={"gps_deviation_km": 5.0}))
    )


def test_time_delay_major_fires_over_threshold() -> None:
    """Delay beyond 60 minutes fires; exactly 60 does not."""
    assert "time_delay_major" in fired_names(
        apply_rules(signals(gps={"time_delay_minutes": 61}))
    )
    assert "time_delay_major" not in fired_names(
        apply_rules(signals(gps={"time_delay_minutes": 60}))
    )


def test_complaint_detected_fires_over_threshold() -> None:
    """Complaint score beyond 0.7 fires; exactly 0.7 does not."""
    assert "complaint_detected" in fired_names(
        apply_rules(signals(complaint={"complaint_score": 0.71}))
    )
    assert "complaint_detected" not in fired_names(
        apply_rules(signals(complaint={"complaint_score": 0.7}))
    )


def test_change_request_fires_day() -> None:
    """A chat change request fires the day-level rule."""
    fired = apply_rules(
        signals(complaint={"change_request": True})
    )

    assert "change_request_detected" in fired_names(fired)
    assert next(r for r in fired if r["name"] == "change_request_detected")["severity"] == "day"


def test_city_change_required_fires_plan() -> None:
    """Hotel overbooking or a city change request fires the plan rule."""
    hotel_fired = apply_rules(signals(context={"hotel_overbooked": True}))
    city_fired = apply_rules(signals(context={"city_change_requested": True}))

    assert "city_change_required" in fired_names(hotel_fired)
    assert "city_change_required" in fired_names(city_fired)
    plan_rule = next(
        r for r in hotel_fired if r["name"] == "city_change_required"
    )
    assert plan_rule["severity"] == "plan"


def test_clean_signals_fire_nothing() -> None:
    """A happy-path trip fires no rules at all."""
    fired = apply_rules(signals())

    assert fired == []


def test_apply_rules_output_shape() -> None:
    """Fired entries carry name/severity/source/category/reason."""
    fired = apply_rules(signals(places={"is_open": False}))
    entry = fired[0]

    assert set(entry) == {"name", "severity", "source", "category", "reason"}
    assert set(entry["reason"]) == {"short", "description", "details"}


def test_complaint_rule_category_mapping() -> None:
    """Complaint 'other' maps to user_report; real categories pass through."""
    other = apply_rules(
        signals(complaint={"complaint_score": 0.8, "category": "other"})
    )
    transport = apply_rules(
        signals(complaint={"complaint_score": 0.8, "category": "transport"})
    )

    assert next(r for r in other if r["name"] == "complaint_detected")["category"] == "user_report"
    assert next(r for r in transport if r["name"] == "complaint_detected")["category"] == "transport"


def test_get_rule_by_name() -> None:
    """Rules are retrievable by name; unknown names return None."""
    assert get_rule("rain_3h_outdoor") is not None
    assert get_rule("does_not_exist") is None


# ---------------------------------------------------------------------------
# 12. Severity classifier
# ---------------------------------------------------------------------------


def test_classifier_plan_wins() -> None:
    """plan beats day and step."""
    result = classify_severity(
        [
            {"severity": "step"},
            {"severity": "day"},
            {"severity": "plan"},
        ]
    )

    assert result == "plan"


def test_classifier_day_wins_over_step() -> None:
    """day beats step when no plan is present."""
    result = classify_severity([{"severity": "step"}, {"severity": "day"}])

    assert result == "day"


def test_classifier_step_alone() -> None:
    """A single step rule classifies as step."""
    assert classify_severity([{"severity": "step"}]) == "step"


def test_classifier_empty_is_none() -> None:
    """No triggered rules classify as none."""
    assert classify_severity([]) == "none"


def test_classifier_ignores_unknown_severity() -> None:
    """Rules with unrecognised severity do not break classification."""
    assert classify_severity([{"severity": "banana"}]) == "none"
    assert classify_severity([{"severity": "banana"}, {"severity": "day"}]) == "day"


def test_classifier_severity_order() -> None:
    """Severity order and numeric rank match the documented hierarchy."""
    assert SEVERITY_ORDER == ("none", "step", "day", "plan")
    assert severity_rank("step") < severity_rank("day") < severity_rank("plan")
    assert severity_rank("unknown") == severity_rank("none")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    sys.exit(pytest.main([__file__, "-v"]))