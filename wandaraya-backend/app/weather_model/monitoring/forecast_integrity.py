"""Read-only forecast-record integrity and preliminary readiness assessment."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Mapping

from sqlalchemy import create_engine, text

from app.weather_model.monitoring.approval import ModelApprovalEvaluator, QualityMetrics


VALID_TARGETS = {
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
}
MAX_OBSERVATION_AGE_MONTHS = 3


def month_index(value: date) -> int:
    return value.year * 12 + value.month


def first_day(value: date) -> date:
    return value.replace(day=1)


def _month_from_index(value: int) -> date:
    year, month_zero_indexed = divmod(value - 1, 12)
    return date(year, month_zero_indexed + 1, 1)


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def validate_forecast_run(
    run: Mapping[str, Any],
    forecasts: list[Mapping[str, Any]],
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Validate forecast rows for one run without writing to the registry.

    ``production_ready_for_review`` is intentionally only a preliminary
    screening result.  It is never equivalent to production approval.
    """
    today = reference_date or datetime.now(timezone.utc).date()
    issues: list[str] = []
    warnings: list[str] = []
    readiness_blockers: list[str] = []
    horizon = int(run["forecast_horizon_months"])
    latest_calendar_month = first_day(_as_date(run["latest_calendar_month"]))
    latest_observed_month = first_day(_as_date(run["latest_observed_month"]))

    if run["target"] not in VALID_TARGETS:
        issues.append("invalid_target")
    if not forecasts:
        issues.append("missing_forecasts")

    forecast_months: list[date] = []
    for forecast in forecasts:
        forecast_month = _as_date(forecast["forecast_month"])
        forecast_months.append(forecast_month)
        if forecast_month != first_day(forecast_month):
            issues.append("forecast_month_not_month_start")
        for field in ("predicted_value", "raw_prediction"):
            if not _is_finite(forecast.get(field)):
                issues.append(f"non_finite_{field}")
        predicted = forecast.get("predicted_value")
        lower = forecast.get("lower_bound")
        upper = forecast.get("upper_bound")
        if lower is not None and not _is_finite(lower):
            issues.append("non_finite_lower_bound")
        if upper is not None and not _is_finite(upper):
            issues.append("non_finite_upper_bound")
        if _is_finite(predicted):
            if run["target"] == "rainfall_mm" and float(predicted) < 0:
                issues.append("negative_rainfall_prediction")
            if _is_finite(lower) and float(lower) > float(predicted):
                issues.append("invalid_prediction_interval")
            if _is_finite(upper) and float(upper) < float(predicted):
                issues.append("invalid_prediction_interval")
        if _is_finite(lower) and _is_finite(upper) and float(lower) > float(upper):
            issues.append("invalid_prediction_interval")

    month_counts = Counter(forecast_months)
    if any(count > 1 for count in month_counts.values()):
        issues.append("duplicate_forecast_month")

    expected_months = {
        _month_from_index(month_index(latest_calendar_month) + offset)
        for offset in range(1, horizon + 1)
    }
    actual_months = set(forecast_months)
    if expected_months - actual_months:
        issues.append("missing_forecast_month")
    if actual_months - expected_months:
        issues.append("unexpected_forecast_month")
    if len(forecasts) != horizon:
        issues.append("forecast_count_mismatch")

    observation_age_months = max(0, month_index(first_day(today)) - month_index(latest_observed_month))
    if observation_age_months > MAX_OBSERVATION_AGE_MONTHS:
        warnings.append("stale_training_observations")
        readiness_blockers.append("stale_training_observations")
    if run["latest_month_missing"]:
        warnings.append("latest_month_missing")
        readiness_blockers.append("latest_month_missing")

    latest_forecast_month = max(actual_months) if actual_months else None
    if latest_forecast_month is None or latest_forecast_month < first_day(today):
        warnings.append("forecast_horizon_expired")
        readiness_blockers.append("forecast_horizon_expired")
    if not run["validation_gate_passed"]:
        readiness_blockers.append("validation_gate_not_passed")

    parameters = run.get("parameters")
    metrics = QualityMetrics.from_mapping(
        parameters.get("quality_metrics") if isinstance(parameters, Mapping) else None
    )
    quality = ModelApprovalEvaluator().evaluate(
        target=run["target"],
        model_name=run["model_name"],
        training_observations=int(run.get("training_observations", 0)),
        validation_gate_passed=bool(run["validation_gate_passed"]),
        metrics=metrics,
    )
    if not quality.eligible_for_review:
        readiness_blockers.append("quality_gate_not_passed")

    integrity_passed = not issues
    production_ready_for_review = integrity_passed and not readiness_blockers
    if run["production_approved"] and not production_ready_for_review:
        issues.append("approved_run_not_production_ready")
        integrity_passed = False

    return {
        "run_id": run["run_id"],
        "district_id": run["district_id"],
        "target": run["target"],
        "model_name": run["model_name"],
        "forecast_count": len(forecasts),
        "forecast_horizon_months": horizon,
        "latest_forecast_month": latest_forecast_month,
        "observation_age_months": observation_age_months,
        "integrity_passed": integrity_passed,
        "quality_eligible_for_review": quality.eligible_for_review,
        "production_ready_for_review": production_ready_for_review,
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "readiness_blockers": sorted(set(readiness_blockers)),
    }


def run_forecast_integrity_audit(database_url: str) -> dict[str, Any]:
    """Audit all persisted forecasts, including impossible-but-detectable orphans."""
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            runs = connection.execute(
                text("SELECT * FROM weather_model_runs ORDER BY created_at_utc DESC")
            ).mappings().all()
            forecast_rows = connection.execute(
                text("SELECT * FROM weather_forecasts ORDER BY run_id, forecast_month")
            ).mappings().all()
    finally:
        engine.dispose()

    forecasts_by_run: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for forecast in forecast_rows:
        forecasts_by_run[forecast["run_id"]].append(forecast)
    known_run_ids = {run["run_id"] for run in runs}
    orphan_run_ids = sorted(set(forecasts_by_run) - known_run_ids)
    results = [
        validate_forecast_run(run, forecasts_by_run.get(run["run_id"], []))
        for run in runs
    ]
    issue_counts = Counter(issue for result in results for issue in result["issues"])
    warning_counts = Counter(warning for result in results for warning in result["warnings"])
    if orphan_run_ids:
        issue_counts["orphan_forecast_record"] = sum(
            len(forecasts_by_run[run_id]) for run_id in orphan_run_ids
        )

    return {
        "total_model_runs": len(results),
        "total_forecasts": len(forecast_rows),
        "integrity_passed": sum(result["integrity_passed"] for result in results),
        "production_ready_for_review": sum(
            result["production_ready_for_review"] for result in results
        ),
        "orphan_forecast_run_ids": orphan_run_ids,
        "issue_counts": dict(sorted(issue_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "runs": results,
    }
