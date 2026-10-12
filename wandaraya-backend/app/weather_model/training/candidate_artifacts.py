"""Reproducible, unapproved monthly weather candidate artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from app.weather_model.backtesting.missing_aware import (
    MonthlyObservation as MissingAwareObservation,
    prepare_training_history,
)
from app.weather_model.backtesting.observation_loader import ALLOWED_TARGETS
from app.weather_model.backtesting.rolling_origin import add_months, month_range
from app.weather_model.backtesting.schemas import MonthlyObservation


MIN_TRAINING_MONTHS = 36
MIN_TRAINING_COVERAGE = 0.95
SUPPORTED_MODELS = frozenset({"prophet", "monthly_climatology"})


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    )


def calendar_complete_history(observations: list[MonthlyObservation]) -> list[MonthlyObservation]:
    """Represent absent source rows explicitly without writing to the database."""
    if not observations:
        raise ValueError("No historical observations are available.")
    by_month = {item.month: item for item in observations}
    if len(by_month) != len(observations):
        raise ValueError("Duplicate observation months are not allowed.")
    return [
        by_month.get(month, MonthlyObservation(month=month, value=None))
        for month in month_range(observations[0].month, observations[-1].month)
    ]


def prepare_candidate_training(
    observations: list[MonthlyObservation],
    *,
    target: str,
    cutoff: date | None = None,
) -> tuple[list[MonthlyObservation], dict[str, Any]]:
    """Apply the established strict-rainfall / missing-aware-temperature policy."""
    if target not in ALLOWED_TARGETS:
        raise ValueError(f"Unsupported target: {target}")
    ordered = sorted(
        (item for item in observations if cutoff is None or item.month <= cutoff),
        key=lambda item: item.month,
    )
    complete = calendar_complete_history(ordered)
    training_cutoff = complete[-1].month
    observed_count = sum(item.value is not None for item in complete)
    missing_count = len(complete) - observed_count

    if target == "rainfall_mm":
        if len(complete) < MIN_TRAINING_MONTHS:
            raise ValueError("Rainfall history has fewer than 36 calendar months.")
        if any(item.value is None for item in complete):
            raise ValueError("Rainfall training requires complete verified observations; no imputation is allowed.")
        prepared = complete
        policy = {
            "name": "strict_complete_case",
            "min_coverage": None,
            "imputed_months": [],
            "imputation_methods": {},
        }
    else:
        preparation = prepare_training_history(
            [MissingAwareObservation(month=item.month, value=item.value) for item in complete],
            origin=training_cutoff,
            min_train_months=MIN_TRAINING_MONTHS,
            min_coverage=MIN_TRAINING_COVERAGE,
        )
        if not preparation.accepted:
            raise ValueError(
                f"Temperature training rejected: {preparation.reason} "
                f"(coverage={preparation.coverage_ratio:.3f})"
            )
        prepared = [MonthlyObservation(month=month, value=value) for month, value in preparation.observations]
        policy = {
            "name": "missing_aware_training_only",
            "min_coverage": MIN_TRAINING_COVERAGE,
            "imputed_months": list(preparation.imputed_months),
            "imputation_methods": dict(preparation.imputation_methods),
        }

    provenance = {
        "training_start": complete[0].month.isoformat(),
        "training_cutoff": training_cutoff.isoformat(),
        "calendar_months": len(complete),
        "observed_months": observed_count,
        "missing_source_months": missing_count,
        "imputed_training_months": len(policy["imputed_months"]),
        "training_policy": policy,
        "data_fingerprint": canonical_sha256(
            [{"month": item.month.isoformat(), "value": item.value} for item in complete]
        ),
    }
    return prepared, provenance


def prophet_configuration() -> dict[str, Any]:
    """Return the exact candidate configuration used by the batch adapter."""
    return {
        "growth": "linear",
        "yearly_seasonality": False,
        "weekly_seasonality": False,
        "daily_seasonality": False,
        "changepoint_prior_scale": 0.05,
        "seasonality_prior_scale": 1.0,
        "interval_width": 0.80,
        "extra_seasonality": {
            "name": "yearly_monthly",
            "period": 365.25,
            "fourier_order": 3,
            "prior_scale": 1.0,
        },
    }


def build_artifact_payload(model_name: str, training: list[MonthlyObservation]) -> tuple[bytes, dict[str, Any]]:
    """Train/serialize one candidate model without producing forecasts."""
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported candidate model: {model_name}")
    if model_name == "monthly_climatology":
        means = {
            str(month): float(mean(item.value for item in training if item.month.month == month))
            for month in range(1, 13)
        }
        payload = {"model_type": model_name, "monthly_means": means}
        return json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"), {"monthly_means": means}

    import pandas as pd
    from prophet import Prophet
    from prophet.serialize import model_to_json

    configuration = prophet_configuration()
    model = Prophet(
        growth=configuration["growth"],
        yearly_seasonality=configuration["yearly_seasonality"],
        weekly_seasonality=configuration["weekly_seasonality"],
        daily_seasonality=configuration["daily_seasonality"],
        changepoint_prior_scale=configuration["changepoint_prior_scale"],
        seasonality_prior_scale=configuration["seasonality_prior_scale"],
        interval_width=configuration["interval_width"],
    )
    model.add_seasonality(**configuration["extra_seasonality"])
    model.fit(pd.DataFrame({"ds": [item.month for item in training], "y": [item.value for item in training]}))
    return model_to_json(model).encode("utf-8"), configuration


def create_candidate_artifact(
    *,
    root: Path,
    district_id: int,
    target: str,
    model_name: str,
    training: list[MonthlyObservation],
    provenance: dict[str, Any],
    registry_evidence_fingerprint: str,
) -> dict[str, Any]:
    """Persist an immutable artifact directory and checksum-verified manifest."""
    artifact_bytes, configuration = build_artifact_payload(model_name, training)
    version_payload = {
        "district_id": district_id,
        "target": target,
        "model_name": model_name,
        "provenance": provenance,
        "configuration": configuration,
        "registry_evidence_fingerprint": registry_evidence_fingerprint,
        "artifact_sha256": sha256_bytes(artifact_bytes),
    }
    version = canonical_sha256(version_payload)[:16]
    directory = root / f"district_{district_id}" / target / model_name / version
    if directory.exists():
        raise FileExistsError(f"Artifact version already exists and will not be overwritten: {directory}")
    directory.mkdir(parents=True, exist_ok=False)
    artifact_path = directory / ("model.json" if model_name == "prophet" else "climatology.json")
    artifact_path.write_bytes(artifact_bytes)
    manifest = {
        "artifact_version": version,
        "district_id": district_id,
        "target": target,
        "model_name": model_name,
        "artifact_path": str(artifact_path),
        "artifact_sha256": sha256_bytes(artifact_bytes),
        "configuration": configuration,
        "provenance": provenance,
        "registry_evidence_fingerprint": registry_evidence_fingerprint,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_approved": False,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_candidate_artifact(manifest_path: Path) -> tuple[dict[str, Any], bytes]:
    """Load an artifact only after checking its persisted SHA-256 checksum."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = Path(manifest["artifact_path"])
    payload = artifact_path.read_bytes()
    if sha256_bytes(payload) != manifest["artifact_sha256"]:
        raise ValueError("Artifact checksum mismatch.")
    return manifest, payload
