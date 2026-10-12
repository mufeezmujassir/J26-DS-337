"""Safe Airflow task callables that reuse existing weather components."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.weather_model.context.live_weather_client import LiveWeatherClient
from app.weather_model.forecasting.forecast_service import ForecastService


PROJECT_ROOT = Path(os.getenv("WANDARAYA_PROJECT_ROOT", "/opt/airflow/project"))
CACHE_DIR = PROJECT_ROOT / "data/weather/cache"
REGISTRY_PATH = PROJECT_ROOT / "data/weather/reports/registry/weather_model_registry.json"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def _load_json_env(name: str) -> list[dict[str, Any]]:
    raw = os.getenv(name, "[]")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be a JSON list.") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{name} must be a JSON list of objects.")
    return value


def refresh_live_weather_cache(run_date: date) -> dict[str, Any]:
    """Fetch configured locations only; invalid provider data is never cached."""
    locations = _load_json_env("WEATHER_LIVE_LOCATIONS_JSON")
    if not locations:
        return {"status": "skipped", "reason": "no_configured_live_locations", "cached": 0}
    delay_seconds = max(0.0, float(os.getenv("WEATHER_LIVE_RATE_LIMIT_SECONDS", "1")))
    client = LiveWeatherClient()
    valid: list[dict[str, Any]] = []
    rejected = 0
    try:
        for index, location in enumerate(locations):
            result = client.get_forecast(
                latitude=float(location["latitude"]), longitude=float(location["longitude"]), travel_date=run_date
            )
            if result.available and result.forecast is not None:
                valid.append(result.model_dump(mode="json"))
            else:
                rejected += 1
            if index < len(locations) - 1 and delay_seconds:
                time.sleep(delay_seconds)
    finally:
        client.close()
    _atomic_json(CACHE_DIR / f"live_{run_date.isoformat()}.json", {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "run_date": run_date.isoformat(),
        "valid_results": valid, "rejected_provider_results": rejected,
    })
    return {"status": "completed", "cached": len(valid), "rejected": rejected}


def import_verified_historical_weather() -> dict[str, Any]:
    """Run only an explicitly configured verified, append-only import command."""
    policy = os.getenv("WEATHER_HISTORICAL_UPDATE_POLICY", "")
    command = os.getenv("WEATHER_HISTORICAL_IMPORT_COMMAND", "").strip()
    if policy != "verified_append_only" or not command:
        return {"status": "skipped", "reason": "verified_append_only_import_not_configured"}
    arguments = shlex.split(command)
    if not arguments or arguments[0] not in {"python", "python3", sys.executable}:
        raise ValueError("WEATHER_HISTORICAL_IMPORT_COMMAND must be an explicit Python command.")
    completed = subprocess.run(arguments, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=3600, check=False)
    if completed.returncode:
        raise RuntimeError(f"Verified historical import failed: {completed.stderr[-1000:]}")
    return {"status": "completed", "command": arguments, "stdout_tail": completed.stdout[-1000:]}


def train_weather_candidates() -> dict[str, Any]:
    """Invoke the existing candidate trainer; defaults to dry-run for safety."""
    execute = os.getenv("WEATHER_TRAIN_EXECUTE", "false").lower() == "true"
    arguments = [sys.executable, "-m", "app.weather_model.training.train_candidates"]
    if not execute:
        arguments.append("--dry-run")
    completed = subprocess.run(arguments, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=7200, check=False)
    if completed.returncode:
        raise RuntimeError(f"Candidate training task failed: {completed.stderr[-1000:]}")
    return {"status": "completed", "executed_training": execute, "stdout_tail": completed.stdout[-2000:]}


def refresh_prediction_cache(run_date: date) -> dict[str, Any]:
    """Cache reliability-aware results; unavailable entries remain explicit."""
    requests = _load_json_env("WEATHER_PREDICTION_CACHE_REQUESTS_JSON")
    if not requests:
        return {"status": "skipped", "reason": "no_configured_prediction_cache_requests", "cached": 0}
    service = ForecastService(REGISTRY_PATH)
    results = []
    for request in requests:
        forecast_date = date.fromisoformat(request.get("forecast_date", run_date.isoformat()))
        result = service.get_forecast(
            district_id=int(request["district_id"]), target=str(request["target"]),
            forecast_date=forecast_date, reference_date=run_date,
            latitude=request.get("latitude"), longitude=request.get("longitude"),
        )
        results.append(result.model_dump(mode="json"))
    _atomic_json(CACHE_DIR / f"predictions_{run_date.isoformat()}.json", {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "reference_date": run_date.isoformat(), "results": results,
    })
    return {"status": "completed", "cached": len(results), "available": sum(item["status"] == "available" for item in results)}
