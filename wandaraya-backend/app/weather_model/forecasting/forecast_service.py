"""Safe selection between live weather and explicitly approved artifacts."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.weather_model.context.live_weather_client import LiveWeatherClient
from app.weather_model.forecasting.fallback_policy import live_provider_supported
from app.weather_model.forecasting.reliability import ArtifactVerifier, VerifiedArtifact, is_forecast_after_training_cutoff
from app.weather_model.forecasting.schemas import ForecastReliability, ReliableForecastResult


UNITS = {
    "rainfall_mm": "millimetres",
    "temperature_min_c": "celsius",
    "temperature_max_c": "celsius",
}


class ForecastService:
    """Never silently uses unapproved candidates or another district's data."""

    def __init__(self, registry_path: Path, live_client: LiveWeatherClient | None = None) -> None:
        self.verifier = ArtifactVerifier(registry_path)
        self.live_client = live_client or LiveWeatherClient()

    def get_forecast(
        self,
        *,
        district_id: int,
        target: str,
        forecast_date: date,
        reference_date: date,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> ReliableForecastResult:
        if target not in UNITS:
            raise ValueError(f"Unsupported target: {target}")
        if (latitude is None) != (longitude is None):
            raise ValueError("Latitude and longitude must be supplied together.")

        # Live data is the first choice when the requested date is inside the
        # provider's documented short horizon.
        live_reason = None
        if latitude is not None and live_provider_supported(forecast_date, reference_date):
            live = self.live_client.get_forecast(
                latitude=latitude, longitude=longitude, travel_date=forecast_date
            )
            if live.available and live.forecast is not None:
                value = {
                    "rainfall_mm": live.forecast.precipitation_mm_forecast,
                    "temperature_min_c": live.forecast.temperature_min_c,
                    "temperature_max_c": live.forecast.temperature_max_c,
                }[target]
                if value is not None:
                    return ReliableForecastResult(
                        district_id=district_id, target=target, forecast_month=forecast_date,
                        status="available", predicted_value=float(value), unit=UNITS[target],
                        source="openweathermap", production_approved=False,
                        reliability=ForecastReliability(
                            level="live_provider", reason="valid_live_provider_forecast",
                            issued_at_utc=live.generated_at_utc,
                            horizon_days=(forecast_date - reference_date).days,
                            freshness="current", validation_status="provider_response_validated",
                            details={"resolution": live.resolution, "forecast_intervals": live.forecast.forecast_intervals},
                        ),
                    )
                live_reason = "live_provider_missing_requested_target"
            else:
                live_reason = f"live_provider_unavailable: {live.message}"
        elif latitude is not None:
            live_reason = "requested_date_outside_live_provider_horizon"

        try:
            artifact = self.verifier.verify(district_id, target)
            if not is_forecast_after_training_cutoff(artifact, forecast_date):
                raise ValueError("forecast_date_is_not_after_training_cutoff")
            value = self._predict_from_artifact(artifact, forecast_date)
            return ReliableForecastResult(
                district_id=district_id, target=target, forecast_month=forecast_date,
                status="available", predicted_value=value, unit=UNITS[target], source="approved_model",
                model_version=artifact.model_version, production_approved=True,
                reliability=ForecastReliability(
                    level="approved_model", reason="approved_artifact_verified",
                    freshness="not_applicable", validation_status="registry_manifest_checksum_verified",
                    model_evidence_status=artifact.evidence_status,
                    details={"model_name": artifact.model_name, "training_cutoff": artifact.manifest["provenance"]["training_cutoff"]},
                ),
            )
        except ValueError as exc:
            reason = str(exc)
            if live_reason:
                reason = f"{reason}; {live_reason}"
            return self._unavailable(district_id, target, forecast_date, reason)

    @staticmethod
    def _predict_from_artifact(artifact: VerifiedArtifact, forecast_date: date) -> float:
        if artifact.model_name == "monthly_climatology":
            payload = json.loads(artifact.payload.decode("utf-8"))
            value = payload["monthly_means"].get(str(forecast_date.month))
        elif artifact.model_name == "prophet":
            import pandas as pd
            from prophet.serialize import model_from_json

            model = model_from_json(artifact.payload.decode("utf-8"))
            value = float(model.predict(pd.DataFrame({"ds": [forecast_date]})).iloc[0]["yhat"])
        else:
            raise ValueError("unsupported_approved_artifact_model")
        if value is None:
            raise ValueError("approved_artifact_cannot_predict_requested_month")
        value = float(value)
        if artifact.target == "rainfall_mm":
            return max(0.0, value)
        if not 0.0 <= value <= 45.0:
            raise ValueError("approved_artifact_temperature_outside_physical_range")
        return value

    @staticmethod
    def _unavailable(district_id: int, target: str, forecast_date: date, reason: str) -> ReliableForecastResult:
        return ReliableForecastResult(
            district_id=district_id, target=target, forecast_month=forecast_date,
            status="unavailable", unit=UNITS[target], reliability=ForecastReliability(
                level="unavailable", reason=reason, freshness="unavailable",
                validation_status="no_verified_production_forecast",
            ),
        )
