"""Date-specific forecasts from checksum-verified daily NASA Prophet models."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from app.weather_model.context.schemas import DailyForecastResult, DailyForecastValue
from app.weather_model.forecasting.daily_prophet import (
    RAIN_THRESHOLD_MM,
    finite_prediction,
    load_verified_daily_artifact,
    predict_daily,
)


class DailyForecastProvider:
    TARGETS = {
        "rainfall_mm": ("rainfall", "mm/day"),
        "temperature_min_c": ("temperature_min", "°C"),
        "temperature_max_c": ("temperature_max", "°C"),
    }

    def __init__(self, artifact_root: str | Path | None = None):
        # Resolve from the backend package rather than the process working
        # directory. Jupyter commonly runs from ``notebooks/weather`` while
        # FastAPI normally runs from the backend root.
        backend_root = Path(__file__).resolve().parents[3]
        self.artifact_root = (
            Path(artifact_root).resolve()
            if artifact_root is not None
            else backend_root / "data/weather/artifacts/daily_nasa_prophet"
        )

    @lru_cache(maxsize=2048)
    def get_daily_forecast(self, district_id: int, travel_date: date) -> DailyForecastResult:
        values: dict[str, DailyForecastValue] = {}
        manifests: dict[str, object] = {}
        missing: list[str] = []
        for target, (field, unit) in self.TARGETS.items():
            try:
                artifact_dir = self.artifact_root / f"district_{district_id}" / target
                model, manifest = load_verified_daily_artifact(artifact_dir)
                cutoff = date.fromisoformat(str(manifest["training_cutoff"]))
                if travel_date <= cutoff:
                    raise ValueError("Requested date is not after the training cutoff")
                row = predict_daily(model, [travel_date], target).iloc[0]
                values[field] = DailyForecastValue(
                    target=target,
                    value=finite_prediction(row.yhat),
                    lower=finite_prediction(row.yhat_lower),
                    upper=finite_prediction(row.yhat_upper),
                    unit=unit,
                )
                manifests[target] = {
                    "training_cutoff": manifest["training_cutoff"],
                    "test_metrics": manifest["test_metrics"],
                    "model_sha256": manifest["model_sha256"],
                    "rain_prediction_threshold_mm": manifest.get("rain_prediction_threshold_mm"),
                }
            except (OSError, ValueError, KeyError, TypeError):
                missing.append(target)
        rainfall = values.get("rainfall")
        rainfall_manifest = manifests.get("rainfall_mm") or {}
        rainfall_threshold = float(
            rainfall_manifest.get("rain_prediction_threshold_mm") or RAIN_THRESHOLD_MM
        )
        result = DailyForecastResult(
            district_id=district_id,
            requested_date=travel_date,
            available=bool(values),
            rainfall=rainfall,
            temperature_min=values.get("temperature_min"),
            temperature_max=values.get("temperature_max"),
            rain_expected=(rainfall.value >= rainfall_threshold) if rainfall else None,
            rain_threshold_mm=rainfall_threshold,
            missing_targets=missing,
            provenance={
                "dataset": "NASA POWER daily 2010-2025",
                "model_artifacts": manifests,
                "is_live_weather": False,
            },
            message=(
                "Date-specific long-range estimate from daily NASA POWER Prophet models."
                if values
                else "No verified daily NASA POWER Prophet model is available for this district."
            ),
        )
        return result
