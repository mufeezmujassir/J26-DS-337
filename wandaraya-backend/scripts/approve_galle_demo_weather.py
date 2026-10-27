"""Approve and publish the bounded Galle monthly-weather demo scope.

This command is intentionally narrow: district 78, the three supported weather
targets, and registry-recommended artifacts only. It records the human demo
authorization in both the registry audit trail and database run metadata.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from prophet.serialize import model_from_json
from sqlalchemy.orm import Session

from app.models.weather_forecast import WeatherForecast
from app.models.weather_model_run import WeatherModelRun
from app.weather_model.forecasting.reliability import ArtifactVerifier
from app.weather_model.persistence.database import get_weather_engine
from app.weather_model.registry.registry_manager import RegistryManager
from app.weather_model.registry.schemas import ApprovalRequest


DISTRICT_ID = 78
TARGETS = ("rainfall_mm", "temperature_min_c", "temperature_max_c")
REGISTRY_PATH = Path("data/weather/reports/registry/weather_model_registry.json")
DEMO_END_MONTH = date(2026, 11, 1)


def month_range(start: date, end: date) -> list[date]:
    values: list[date] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        values.append(cursor)
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return values


def predictions(artifact, months: list[date]) -> list[tuple[date, float, float | None, float | None]]:
    if artifact.model_name == "monthly_climatology":
        payload = json.loads(artifact.payload.decode("utf-8"))
        return [
            (month, float(payload["monthly_means"][str(month.month)]), None, None)
            for month in months
        ]
    if artifact.model_name == "prophet":
        model = model_from_json(artifact.payload.decode("utf-8"))
        frame = model.predict(pd.DataFrame({"ds": months}))
        return [
            (
                month,
                float(row.yhat),
                float(row.yhat_lower),
                float(row.yhat_upper),
            )
            for month, row in zip(months, frame.itertuples(index=False))
        ]
    raise ValueError(f"Unsupported approved model: {artifact.model_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute to apply the bounded Galle demo approval.")

    manager = RegistryManager(REGISTRY_PATH)
    registry = manager.load()
    if registry is None:
        raise ValueError("Weather model registry is missing.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = REGISTRY_PATH.with_name(f"weather_model_registry.before_galle_demo_{stamp}.json")
    shutil.copy2(REGISTRY_PATH, backup)

    for target in TARGETS:
        entry = manager._find(registry, DISTRICT_ID, target)
        if entry.recommended_model is None:
            raise ValueError(f"No recommended model for {target}")
        if entry.production_approved and entry.approval_status == "approved":
            if entry.selected_model != entry.recommended_model:
                raise ValueError(
                    f"Existing approval for {target} selects {entry.selected_model}, "
                    f"not the current recommendation {entry.recommended_model}."
                )
            continue
        resolutions = {
            flag: (
                "Accepted for the explicitly authorized, Galle-only demonstration; "
                "the limitation remains visible in registry evidence and must be re-reviewed "
                "before broader production use."
            )
            for flag in entry.review_flags
        }
        registry = manager.approve(
            registry,
            DISTRICT_ID,
            target,
            ApprovalRequest(
                reviewer_id="project-owner-demo-authorization-2026-10-22",
                selected_model=entry.recommended_model,
                justification=(
                    "Project owner explicitly authorized a bounded Galle weather demonstration "
                    "on 2026-10-22. Scope is district 78 and November 2026 only; existing "
                    "validation evidence and limitations are retained."
                ),
                resolved_review_flags=resolutions,
            ),
        )
    manager.save(registry)

    verifier = ArtifactVerifier(REGISTRY_PATH)
    engine = get_weather_engine()
    created: list[dict[str, object]] = []
    try:
        with Session(engine) as session, session.begin():
            for target in TARGETS:
                artifact = verifier.verify(DISTRICT_ID, target)
                provenance = artifact.manifest["provenance"]
                training_cutoff = date.fromisoformat(provenance["training_cutoff"])
                training_start = date.fromisoformat(provenance["training_start"])
                months = month_range(
                    date(training_cutoff.year + (training_cutoff.month == 12), training_cutoff.month % 12 + 1, 1),
                    DEMO_END_MONTH,
                )
                values = predictions(artifact, months)
                run_id = f"demo_d78_{target}_{artifact.model_name}_{stamp}"
                session.add(
                    WeatherModelRun(
                        run_id=run_id,
                        district_id=DISTRICT_ID,
                        target=target,
                        model_name=artifact.model_name,
                        training_start=training_start,
                        training_cutoff=training_cutoff,
                        latest_calendar_month=training_cutoff,
                        latest_observed_month=training_cutoff,
                        latest_month_missing=False,
                        training_observations=int(provenance["observed_months"]),
                        forecast_horizon_months=len(months),
                        validation_gate_passed=True,
                        production_approved=True,
                        parameters={
                            "model_version": artifact.model_version,
                            "registry_evidence_status": artifact.evidence_status,
                            "demo_scope": "Galle district 78 through 2026-11 only",
                            "authorized_by": "project-owner-demo-authorization-2026-10-22",
                            "known_limitation": "Training cutoff is 2025-10-01; refresh observations before general production use.",
                        },
                        status="approved_demo_scope",
                    )
                )
                # The ORM models intentionally have no relationship mapping,
                # so establish the FK parent before queuing forecast children.
                session.flush()
                for month, raw, lower, upper in values:
                    predicted = max(0.0, raw) if target == "rainfall_mm" else raw
                    session.add(
                        WeatherForecast(
                            run_id=run_id,
                            forecast_month=month,
                            predicted_value=predicted,
                            lower_bound=max(0.0, lower) if target == "rainfall_mm" and lower is not None else lower,
                            upper_bound=max(0.0, upper) if target == "rainfall_mm" and upper is not None else upper,
                            raw_prediction=raw,
                        )
                    )
                demo_value = next(item for item in values if item[0] == DEMO_END_MONTH)
                created.append(
                    {
                        "target": target,
                        "model": artifact.model_name,
                        "run_id": run_id,
                        "november_2026_value": demo_value[1],
                        "lower": demo_value[2],
                        "upper": demo_value[3],
                    }
                )
    finally:
        engine.dispose()

    print(json.dumps({"registry_backup": str(backup), "created": created}, indent=2))


if __name__ == "__main__":
    main()
