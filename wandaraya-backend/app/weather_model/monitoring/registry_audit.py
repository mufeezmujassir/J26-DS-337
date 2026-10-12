"""Read-only integrity and quality-evidence audits for weather model runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import date
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text

from app.weather_model.monitoring.approval import ModelApprovalEvaluator, QualityMetrics


VALID_TARGETS = {
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
}
EXPECTED_HORIZON_MONTHS = 3
MIN_TRAINING_OBSERVATIONS = 24


def months_between(start: date, end: date) -> int:
    """Return whole calendar-month distance without treating days as months."""
    return (end.year - start.year) * 12 + end.month - start.month


def audit_model_run(
    run: Mapping[str, Any],
    forecast_count: int,
) -> dict[str, Any]:
    """Check one registry row without writing to the database.

    This intentionally checks metadata consistency only.  Forecast-month
    continuity and numerical accuracy belong to later monitoring stages.
    """
    issues: list[str] = []
    warnings: list[str] = []

    if run["target"] not in VALID_TARGETS:
        issues.append("invalid_target")
    if run["training_observations"] < MIN_TRAINING_OBSERVATIONS:
        issues.append("insufficient_training_observations")
    if run["forecast_horizon_months"] != EXPECTED_HORIZON_MONTHS:
        warnings.append("unexpected_forecast_horizon")
    if forecast_count != run["forecast_horizon_months"]:
        issues.append("forecast_count_mismatch")
    if run["training_start"] > run["training_cutoff"]:
        issues.append("invalid_training_period")
    if run["latest_observed_month"] > run["latest_calendar_month"]:
        issues.append("invalid_observation_date")

    observation_lag_months = months_between(
        run["latest_observed_month"], run["latest_calendar_month"]
    )
    if observation_lag_months > 0:
        warnings.append("historical_observation_lag")
    if run["latest_month_missing"]:
        warnings.append("latest_month_missing")
    if run["production_approved"] and not run["validation_gate_passed"]:
        issues.append("approved_without_validation")
    if run["production_approved"] and issues:
        issues.append("approved_model_has_integrity_issues")

    return {
        "run_id": run["run_id"],
        "district_id": run["district_id"],
        "target": run["target"],
        "model_name": run["model_name"],
        "status": run["status"],
        "forecast_count": forecast_count,
        "forecast_horizon_months": run["forecast_horizon_months"],
        "observation_lag_months": observation_lag_months,
        "validation_gate_passed": run["validation_gate_passed"],
        "production_approved": run["production_approved"],
        "integrity_passed": not issues,
        "issues": issues,
        "warnings": warnings,
    }


def run_registry_audit(database_url: str) -> dict[str, Any]:
    """Load registry metadata and create a structured, read-only audit report."""
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            runs = connection.execute(
                text("SELECT * FROM weather_model_runs ORDER BY created_at_utc DESC")
            ).mappings().all()
            forecast_counts = {
                row["run_id"]: int(row["forecast_count"])
                for row in connection.execute(
                    text(
                        "SELECT run_id, COUNT(*) AS forecast_count "
                        "FROM weather_forecasts GROUP BY run_id"
                    )
                ).mappings()
            }
            total_forecasts = int(
                connection.execute(text("SELECT COUNT(*) FROM weather_forecasts")).scalar_one()
            )
    finally:
        engine.dispose()

    results = [
        audit_model_run(run, forecast_counts.get(run["run_id"], 0))
        for run in runs
    ]
    issue_counts = Counter(issue for result in results for issue in result["issues"])
    warning_counts = Counter(warning for result in results for warning in result["warnings"])
    return {
        "total_model_runs": len(results),
        "total_forecasts": total_forecasts,
        "integrity_passed": sum(result["integrity_passed"] for result in results),
        "validation_gate_passed": sum(result["validation_gate_passed"] for result in results),
        "production_approved": sum(result["production_approved"] for result in results),
        "issue_counts": dict(sorted(issue_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "runs": results,
    }


def audit_model_runs(
    runs: Iterable[Any],
    *,
    evaluator: ModelApprovalEvaluator | None = None,
) -> list[dict[str, Any]]:
    """Return audit records without changing database state or approval flags."""
    quality_evaluator = evaluator or ModelApprovalEvaluator()
    audited: list[dict[str, Any]] = []
    for run in runs:
        parameters = run.parameters if isinstance(run.parameters, dict) else {}
        metrics = QualityMetrics.from_mapping(parameters.get("quality_metrics"))
        decision = quality_evaluator.evaluate(
            target=run.target,
            model_name=run.model_name,
            training_observations=run.training_observations,
            validation_gate_passed=run.validation_gate_passed,
            metrics=metrics,
        )
        audited.append(
            {
                "run_id": run.run_id,
                "district_id": run.district_id,
                "target": run.target,
                "model_name": run.model_name,
                "production_approved": run.production_approved,
                "stored_status": run.status,
                "quality_metrics_present": metrics is not None,
                "decision": asdict(decision),
            }
        )
    return audited
