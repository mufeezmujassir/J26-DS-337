"""Tests for the Wandaraya disruption detection module."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

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