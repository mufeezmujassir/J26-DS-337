"""Unit tests for the Airflow callables without requiring Airflow itself."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.weather_model.context.schemas import LiveWeatherDay, LiveWeatherResult
from app.weather_model.orchestration import airflow_tasks


class _LiveClient:
    def __init__(self, result: LiveWeatherResult) -> None:
        self.result = result
        self.closed = False

    def get_forecast(self, **_kwargs: object) -> LiveWeatherResult:
        return self.result

    def close(self) -> None:
        self.closed = True


def test_live_refresh_caches_only_valid_provider_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _LiveClient(LiveWeatherResult(
        latitude=6.05,
        longitude=80.22,
        requested_date=date(2026, 10, 12),
        available=True,
        generated_at_utc=datetime.now(timezone.utc),
        forecast=LiveWeatherDay(date=date(2026, 10, 12), temperature_max_c=30.0),
        message="valid",
    ))
    monkeypatch.setattr(airflow_tasks, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(airflow_tasks, "LiveWeatherClient", lambda: client)
    monkeypatch.setenv("WEATHER_LIVE_LOCATIONS_JSON", '[{"latitude": 6.05, "longitude": 80.22}]')
    monkeypatch.setenv("WEATHER_LIVE_RATE_LIMIT_SECONDS", "0")

    result = airflow_tasks.refresh_live_weather_cache(date(2026, 10, 12))

    assert result == {"status": "completed", "cached": 1, "rejected": 0}
    cached = json.loads((tmp_path / "cache/live_2026-10-12.json").read_text(encoding="utf-8"))
    assert len(cached["valid_results"]) == 1
    assert client.closed is True


def test_live_refresh_skips_when_locations_are_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEATHER_LIVE_LOCATIONS_JSON", raising=False)
    assert airflow_tasks.refresh_live_weather_cache(date(2026, 10, 12))["status"] == "skipped"


def test_live_refresh_rejects_invalid_provider_data_and_recovers_on_a_later_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    invalid = _LiveClient(LiveWeatherResult(
        latitude=6.05, longitude=80.22, requested_date=date(2026, 10, 12), available=False,
        forecast=None, message="invalid provider response",
    ))
    valid = _LiveClient(LiveWeatherResult(
        latitude=6.05, longitude=80.22, requested_date=date(2026, 10, 12), available=True,
        generated_at_utc=datetime.now(timezone.utc),
        forecast=LiveWeatherDay(date=date(2026, 10, 12), temperature_max_c=30.0), message="valid",
    ))
    clients = iter((invalid, valid))
    monkeypatch.setattr(airflow_tasks, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(airflow_tasks, "LiveWeatherClient", lambda: next(clients))
    monkeypatch.setenv("WEATHER_LIVE_LOCATIONS_JSON", '[{"latitude": 6.05, "longitude": 80.22}]')
    monkeypatch.setenv("WEATHER_LIVE_RATE_LIMIT_SECONDS", "0")

    first = airflow_tasks.refresh_live_weather_cache(date(2026, 10, 12))
    second = airflow_tasks.refresh_live_weather_cache(date(2026, 10, 12))
    cached = json.loads((tmp_path / "cache/live_2026-10-12.json").read_text(encoding="utf-8"))

    assert first["cached"] == 0 and first["rejected"] == 1
    assert second["cached"] == 1 and second["rejected"] == 0
    assert len(cached["valid_results"]) == 1  # Same-date rerun replaces, never duplicates.


def test_historical_import_requires_explicit_verified_append_only_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHER_HISTORICAL_UPDATE_POLICY", "")
    monkeypatch.setenv("WEATHER_HISTORICAL_IMPORT_COMMAND", "python -m scripts.import_weather")
    assert airflow_tasks.import_verified_historical_weather()["status"] == "skipped"


def test_training_is_dry_run_unless_explicitly_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = "planned"
        stderr = ""

    def fake_run(arguments, **_kwargs):
        calls.append(arguments)
        return _Completed()

    monkeypatch.setattr(airflow_tasks, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(airflow_tasks.subprocess, "run", fake_run)
    monkeypatch.delenv("WEATHER_TRAIN_EXECUTE", raising=False)

    result = airflow_tasks.train_weather_candidates()

    assert result["executed_training"] is False
    assert calls[0][-1] == "--dry-run"


def test_prediction_cache_is_explicitly_unavailable_without_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEATHER_PREDICTION_CACHE_REQUESTS_JSON", raising=False)
    result = airflow_tasks.refresh_prediction_cache(date(2026, 10, 12))
    assert result["status"] == "skipped"


@pytest.mark.parametrize(
    ("filename", "dag_id", "schedule_variable"),
    [
        ("weather_live.py", "weather_live", "WEATHER_LIVE_SCHEDULE"),
        ("weather_historical.py", "weather_historical", "WEATHER_HISTORICAL_SCHEDULE"),
        ("weather_model_train.py", "weather_model_train", "WEATHER_MODEL_TRAIN_SCHEDULE"),
        ("weather_predictions_cache.py", "weather_predictions_cache", "WEATHER_PREDICTIONS_CACHE_SCHEDULE"),
    ],
)
def test_weather_dags_are_paused_and_configurable(filename: str, dag_id: str, schedule_variable: str) -> None:
    content = (Path(__file__).parents[2] / "dags" / filename).read_text(encoding="utf-8")
    assert f'dag_id="{dag_id}"' in content
    assert schedule_variable in content
    assert "is_paused_upon_creation=True" in content
    assert "retries=" in content
    assert "execution_timeout=" in content
