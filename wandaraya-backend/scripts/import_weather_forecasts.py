"""Validate and import Stage 6 weather forecasts without overwriting prior runs."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.weather_forecast import WeatherForecast
from app.models.weather_model_run import WeatherModelRun
from app.weather_model.persistence.database import get_weather_engine


DEFAULT_REPORTS_DIR = Path("data/weather/forecasts/stage6/reports")
MANIFEST_COLUMNS = {
    "run_id", "district_id", "target", "selected_model", "training_start",
    "training_cutoff", "latest_calendar_month", "latest_observed_month",
    "latest_month_missing", "training_observations", "forecast_horizon_months",
    "production_approved", "parameters", "created_at_utc",
    "validation_gate_passed", "status",
}
FORECAST_COLUMNS = {
    "district_id", "target", "model", "ds", "yhat", "yhat_lower",
    "yhat_upper", "raw_yhat", "training_cutoff", "production_approved", "run_id",
}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
        return True
    if isinstance(value, str) and value.strip().lower() in {"false", "0", "no"}:
        return False
    if pd.isna(value):
        raise ValueError("Boolean value is missing.")
    raise ValueError(f"Invalid Boolean value: {value!r}")


def required_float(value: Any, *, field: str) -> float:
    converted = pd.to_numeric(value, errors="coerce")
    if pd.isna(converted):
        raise ValueError(f"{field} is required and must be numeric.")
    return float(converted)


def optional_float(value: Any, *, field: str) -> float | None:
    if pd.isna(value) or value == "":
        return None
    return required_float(value, field=field)


def required_date(value: Any, *, field: str):
    converted = pd.to_datetime(value, errors="coerce")
    if pd.isna(converted):
        raise ValueError(f"{field} is required and must be a date.")
    return converted.date()


def parse_parameters(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("parameters must contain a JSON object.")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        # Existing Stage 6 reports serialize a Python dictionary representation.
        parsed = ast.literal_eval(value)
    if not isinstance(parsed, dict):
        raise ValueError("parameters must be an object.")
    return parsed


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {sorted(missing)}")


def build_records(
    manifest: pd.DataFrame,
    forecasts: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    require_columns(manifest, MANIFEST_COLUMNS, "training_manifest.csv")
    require_columns(forecasts, FORECAST_COLUMNS, "all_forecasts.csv")
    if manifest["run_id"].duplicated().any():
        raise ValueError("training_manifest.csv contains duplicate run_id values.")
    if forecasts.duplicated(["run_id", "ds"]).any():
        raise ValueError("all_forecasts.csv contains duplicate run_id and ds values.")

    run_records: list[dict[str, Any]] = []
    manifest_lookup: dict[str, dict[str, Any]] = {}
    for _, row in manifest.iterrows():
        run_id = str(row["run_id"])
        record = {
            "run_id": run_id,
            "district_id": int(row["district_id"]),
            "target": str(row["target"]),
            "model_name": str(row["selected_model"]),
            "training_start": required_date(row["training_start"], field="training_start"),
            "training_cutoff": required_date(row["training_cutoff"], field="training_cutoff"),
            "latest_calendar_month": required_date(
                row["latest_calendar_month"], field="latest_calendar_month"
            ),
            "latest_observed_month": required_date(
                row["latest_observed_month"], field="latest_observed_month"
            ),
            "latest_month_missing": as_bool(row["latest_month_missing"]),
            "training_observations": int(row["training_observations"]),
            "forecast_horizon_months": int(row["forecast_horizon_months"]),
            "validation_gate_passed": as_bool(row["validation_gate_passed"]),
            "production_approved": as_bool(row["production_approved"]),
            "parameters": parse_parameters(row["parameters"]),
            "status": str(row["status"]),
            "created_at_utc": pd.Timestamp(row["created_at_utc"]).to_pydatetime(),
        }
        if record["training_start"] > record["training_cutoff"]:
            raise ValueError(f"Training date range is invalid: {run_id}")
        if record["latest_observed_month"] > record["latest_calendar_month"]:
            raise ValueError(f"Latest observed month exceeds calendar month: {run_id}")
        manifest_lookup[run_id] = record
        run_records.append(record)

    forecast_records: list[dict[str, Any]] = []
    for _, row in forecasts.iterrows():
        run_id = str(row["run_id"])
        model_run = manifest_lookup.get(run_id)
        if model_run is None:
            raise ValueError(f"Unknown forecast run ID: {run_id}")
        if (
            int(row["district_id"]) != model_run["district_id"]
            or str(row["target"]) != model_run["target"]
            or str(row["model"]) != model_run["model_name"]
            or required_date(row["training_cutoff"], field="training_cutoff")
            != model_run["training_cutoff"]
            or as_bool(row["production_approved"])
            != model_run["production_approved"]
        ):
            raise ValueError(f"Forecast metadata mismatch: {run_id}")

        predicted_value = required_float(row["yhat"], field="yhat")
        lower_bound = optional_float(row["yhat_lower"], field="yhat_lower")
        upper_bound = optional_float(row["yhat_upper"], field="yhat_upper")
        if model_run["target"] == "rainfall_mm" and predicted_value < 0:
            raise ValueError(f"Negative rainfall prediction: {run_id}")
        if lower_bound is not None and lower_bound > predicted_value:
            raise ValueError(f"Invalid lower bound: {run_id}")
        if upper_bound is not None and upper_bound < predicted_value:
            raise ValueError(f"Invalid upper bound: {run_id}")
        forecast_records.append(
            {
                "run_id": run_id,
                "forecast_month": required_date(row["ds"], field="ds"),
                "predicted_value": predicted_value,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "raw_prediction": required_float(row["raw_yhat"], field="raw_yhat"),
            }
        )

    horizons = Counter(record["run_id"] for record in forecast_records)
    for run in run_records:
        if horizons[run["run_id"]] != run["forecast_horizon_months"]:
            raise ValueError(
                f"Forecast horizon mismatch for {run['run_id']}: expected "
                f"{run['forecast_horizon_months']}, found {horizons[run['run_id']]}"
            )
    return run_records, forecast_records


def import_records(
    run_records: list[dict[str, Any]], forecast_records: list[dict[str, Any]]
) -> tuple[int, int]:
    engine = get_weather_engine()
    inserted_runs = 0
    inserted_forecasts = 0
    try:
        with Session(engine) as session, session.begin():
            for record in run_records:
                result = session.execute(
                    insert(WeatherModelRun)
                    .values(**record)
                    .on_conflict_do_nothing(index_elements=["run_id"])
                )
                inserted_runs += result.rowcount or 0
            for record in forecast_records:
                result = session.execute(
                    insert(WeatherForecast)
                    .values(**record)
                    .on_conflict_do_nothing(
                        index_elements=["run_id", "forecast_month"]
                    )
                )
                inserted_forecasts += result.rowcount or 0
    finally:
        engine.dispose()
    return inserted_runs, inserted_forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    manifest = pd.read_csv(arguments.reports_dir / "training_manifest.csv")
    forecasts = pd.read_csv(arguments.reports_dir / "all_forecasts.csv")
    run_records, forecast_records = build_records(manifest, forecasts)

    print("=" * 55)
    print("WANDARAYA - STAGE 7 IMPORT")
    print("=" * 55)
    print(f"Manifest rows validated: {len(run_records)}")
    print(f"Forecast rows validated: {len(forecast_records)}")
    if arguments.dry_run:
        print("Dry run completed. No database records were changed.")
        return

    inserted_runs, inserted_forecasts = import_records(run_records, forecast_records)
    print("Import transaction completed.")
    print(f"New model runs inserted: {inserted_runs}")
    print(f"New forecasts inserted: {inserted_forecasts}")
    print("Existing records were preserved.")


if __name__ == "__main__":
    main()
