"""Daily Prophet training, evaluation, serialization, and prediction."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from prophet import Prophet
from prophet.serialize import model_from_json, model_to_json


RAIN_THRESHOLD_MM = 0.5


def build_daily_prophet(target: str) -> Prophet:
    if target not in {"rainfall_mm", "temperature_min_c", "temperature_max_c"}:
        raise ValueError(f"Unsupported daily target: {target}")
    return Prophet(
        growth="linear",
        yearly_seasonality=10,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="additive",
        changepoint_prior_scale=0.03,
        seasonality_prior_scale=5.0,
        interval_width=0.80,
    )


def training_frame(observations: pd.DataFrame, target: str) -> pd.DataFrame:
    frame = observations[["date", target]].rename(columns={"date": "ds", target: "y"}).dropna()
    if frame["ds"].duplicated().any() or len(frame) < 365 * 3:
        raise ValueError("Daily Prophet requires unique dates and at least three years of observations")
    if target == "rainfall_mm":
        frame["y"] = np.log1p(frame["y"].clip(lower=0))
    return frame


def fit_daily_prophet(observations: pd.DataFrame, target: str) -> Prophet:
    model = build_daily_prophet(target)
    model.fit(training_frame(observations, target))
    return model


def predict_daily(model: Prophet, dates: pd.Series | list[date], target: str) -> pd.DataFrame:
    future = pd.DataFrame({"ds": pd.to_datetime(dates)})
    result = model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    if target == "rainfall_mm":
        for column in ("yhat", "yhat_lower", "yhat_upper"):
            result[column] = np.expm1(result[column]).clip(lower=0)
    else:
        for column in ("yhat", "yhat_lower", "yhat_upper"):
            result[column] = result[column].clip(lower=-20, upper=60)
    return result


def select_rain_prediction_threshold(actual: pd.Series, predicted: pd.Series) -> float:
    """Choose a validation-only threshold that maximizes balanced accuracy."""
    actual_rain = np.asarray(actual, dtype=float) >= RAIN_THRESHOLD_MM
    predictions = np.asarray(predicted, dtype=float)
    candidates = np.unique(np.quantile(predictions, np.linspace(0.05, 0.95, 91)))
    best_threshold = RAIN_THRESHOLD_MM
    best_score = -1.0
    for threshold in candidates:
        predicted_rain = predictions >= threshold
        tp = np.sum(actual_rain & predicted_rain)
        fn = np.sum(actual_rain & ~predicted_rain)
        tn = np.sum(~actual_rain & ~predicted_rain)
        fp = np.sum(~actual_rain & predicted_rain)
        sensitivity = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        score = (sensitivity + specificity) / 2
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
    return round(max(0.0, best_threshold), 6)


def evaluation_metrics(
    actual: pd.Series,
    predicted: pd.Series,
    target: str,
    *,
    rain_prediction_threshold: float = RAIN_THRESHOLD_MM,
) -> dict[str, float]:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    error = predicted_values - actual_values
    metrics = {
        "mae": round(float(np.mean(np.abs(error))), 4),
        "rmse": round(float(np.sqrt(np.mean(error ** 2))), 4),
        "bias": round(float(np.mean(error)), 4),
    }
    if target == "rainfall_mm":
        observed_rain = actual_values >= RAIN_THRESHOLD_MM
        predicted_rain = predicted_values >= rain_prediction_threshold
        tp = int(np.sum(observed_rain & predicted_rain))
        fp = int(np.sum(~observed_rain & predicted_rain))
        fn = int(np.sum(observed_rain & ~predicted_rain))
        tn = int(np.sum(~observed_rain & ~predicted_rain))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        metrics.update({
            "rain_event_accuracy": round((tp + tn) / len(actual_values), 4),
            "rain_event_precision": round(precision, 4),
            "rain_event_recall": round(recall, 4),
            "rain_event_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
            "rain_prediction_threshold_mm": rain_prediction_threshold,
        })
    return metrics


def save_daily_artifact(
    model: Prophet,
    *,
    artifact_dir: Path,
    district_id: int,
    district_name: str,
    target: str,
    training_start: date,
    training_cutoff: date,
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
    source_provenance: dict[str, object],
    rain_prediction_threshold: float | None = None,
) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.json"
    payload = model_to_json(model).encode("utf-8")
    model_path.write_bytes(payload)
    manifest = {
        "schema_version": 1,
        "model_type": "daily_prophet",
        "district_id": district_id,
        "district_name": district_name,
        "target": target,
        "resolution": "daily",
        "observed_rain_threshold_mm": RAIN_THRESHOLD_MM if target == "rainfall_mm" else None,
        "rain_prediction_threshold_mm": rain_prediction_threshold if target == "rainfall_mm" else None,
        "training_start": training_start.isoformat(),
        "training_cutoff": training_cutoff.isoformat(),
        "validation_period": "2024-01-01..2024-12-31",
        "test_period": "2025-01-01..2025-12-31",
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "source_provenance": source_provenance,
        "model_sha256": hashlib.sha256(payload).hexdigest(),
        "production_approved": True,
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_verified_daily_artifact(artifact_dir: Path) -> tuple[Prophet, dict[str, object]]:
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    payload = (artifact_dir / "model.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["model_sha256"]:
        raise ValueError("Daily Prophet artifact checksum mismatch")
    if not manifest.get("production_approved") or manifest.get("resolution") != "daily":
        raise ValueError("Daily Prophet artifact is not production approved")
    return model_from_json(payload.decode("utf-8")), manifest


def finite_prediction(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Daily Prophet returned a non-finite prediction")
    return float(value)
