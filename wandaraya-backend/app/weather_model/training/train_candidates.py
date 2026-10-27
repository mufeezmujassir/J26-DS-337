"""Train versioned, unapproved Prophet and climatology candidate artifacts."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from app.weather_model.backtesting.observation_loader import (
    load_monthly_observations,
    load_monthly_observations_from_csv,
)
from app.weather_model.persistence.database import get_weather_engine
from app.weather_model.registry.registry_manager import RegistryManager
from app.weather_model.training.candidate_artifacts import (
    SUPPORTED_MODELS,
    create_candidate_artifact,
    prepare_candidate_training,
)


DEFAULT_ARTIFACT_ROOT = Path("data/weather/artifacts/candidates")
DEFAULT_REGISTRY_PATH = Path("data/weather/reports/registry/weather_model_registry.json")
DEFAULT_NASA_MONTHLY_PATH = Path("data/weather/modeling/nasa_power/district_weather_monthly.csv")


def candidate_jobs(registry, district_id: int | None, target: str | None, include_limited: bool, models: list[str]):
    allowed_evidence = {"eligible_for_review"}
    if include_limited:
        allowed_evidence.add("limited_evidence")
    for entry in registry.entries:
        if entry.evidence_status not in allowed_evidence:
            continue
        if district_id is not None and entry.district_id != district_id:
            continue
        if target is not None and entry.target != target:
            continue
        for model_name in models:
            yield entry, model_name


def failure_category(error: Exception) -> str:
    """Keep idempotent skips distinct from scientific eligibility rejections."""
    if isinstance(error, FileExistsError):
        return "existing_artifact"
    if isinstance(error, ValueError) and (
        "requires complete verified observations" in str(error)
        or "Temperature training rejected:" in str(error)
        or "fewer than 36 calendar months" in str(error)
        or "No historical observations" in str(error)
    ):
        return "insufficient_data"
    return "execution_failure"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List candidate jobs without reading/training data.")
    parser.add_argument("--district-id", type=int)
    parser.add_argument("--target", choices=("rainfall_mm", "temperature_min_c", "temperature_max_c"))
    parser.add_argument("--models", nargs="+", choices=sorted(SUPPORTED_MODELS), default=sorted(SUPPORTED_MODELS))
    parser.add_argument("--include-limited", action="store_true")
    parser.add_argument("--cutoff", type=date.fromisoformat)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument(
        "--data-source",
        choices=("nasa_power", "database"),
        default="nasa_power",
        help="Training source. NASA POWER is the canonical default; database preserves the legacy path.",
    )
    parser.add_argument("--nasa-monthly-path", type=Path, default=DEFAULT_NASA_MONTHLY_PATH)
    arguments = parser.parse_args()

    manager = RegistryManager(arguments.registry_path)
    registry = manager.load()
    if registry is None:
        raise FileNotFoundError("Build the weather model registry before training candidates.")
    jobs = list(candidate_jobs(
        registry,
        arguments.district_id,
        arguments.target,
        arguments.include_limited,
        arguments.models,
    ))
    if not jobs:
        print("No registry-eligible candidate training jobs matched the filters.")
        return
    if arguments.dry_run:
        print("\n=== PROPOSED WEATHER CANDIDATE TRAINING JOBS ===")
        for entry, model_name in jobs:
            print(
                f"district={entry.district_id} target={entry.target} "
                f"model={model_name} evidence={entry.evidence_status}"
            )
        print("Total jobs:", len(jobs))
        print("No data, artifact, registry, or approval state was changed.")
        return

    successes: list[dict] = []
    existing_artifacts: list[dict] = []
    insufficient_data: list[dict] = []
    execution_failures: list[dict] = []
    engine = get_weather_engine() if arguments.data_source == "database" else None
    try:
        for entry, model_name in jobs:
            try:
                if arguments.data_source == "nasa_power":
                    observations = load_monthly_observations_from_csv(
                        arguments.nasa_monthly_path,
                        entry.district_id,
                        entry.target,
                        arguments.cutoff,
                    )
                else:
                    observations = load_monthly_observations(
                        engine, entry.district_id, entry.target, arguments.cutoff
                    )
                training, provenance = prepare_candidate_training(
                    observations, target=entry.target, cutoff=arguments.cutoff
                )
                provenance["source_dataset"] = (
                    "NASA POWER daily district representatives aggregated to complete months"
                    if arguments.data_source == "nasa_power"
                    else "district_weather_monthly database table (legacy)"
                )
                provenance["source_path"] = (
                    str(arguments.nasa_monthly_path)
                    if arguments.data_source == "nasa_power"
                    else "database:district_weather_monthly"
                )
                manifest = create_candidate_artifact(
                    root=arguments.artifact_root,
                    district_id=entry.district_id,
                    target=entry.target,
                    model_name=model_name,
                    training=training,
                    provenance=provenance,
                    registry_evidence_fingerprint=entry.evidence_fingerprint,
                )
                manager.register_candidate_artifact(
                    registry,
                    entry.district_id,
                    entry.target,
                    model_name=model_name,
                    model_version=manifest["artifact_version"],
                    artifact_path=manifest["artifact_path"],
                    checksum_sha256=manifest["artifact_sha256"],
                )
                manager.save(registry)
                successes.append(manifest)
                print(
                    f"TRAINED district={entry.district_id} target={entry.target} "
                    f"model={model_name} version={manifest['artifact_version']}"
                )
            except Exception as exc:
                outcome = {
                    "district_id": entry.district_id,
                    "target": entry.target,
                    "model_name": model_name,
                    "error": str(exc),
                }
                category = failure_category(exc)
                if category == "existing_artifact":
                    existing_artifacts.append(outcome)
                    label = "REUSED"
                elif category == "insufficient_data":
                    insufficient_data.append(outcome)
                    label = "REJECTED"
                else:
                    execution_failures.append(outcome)
                    label = "FAILED"
                print(f"{label} district={entry.district_id} target={entry.target} model={model_name}: {exc}")
    finally:
        if engine is not None:
            engine.dispose()

    print("\n=== WEATHER CANDIDATE TRAINING ===")
    print("New artifacts created:     ", len(successes))
    print("Existing artifacts reused:  ", len(existing_artifacts))
    print("Rejected: insufficient data:", len(insufficient_data))
    print("Actual execution failures:  ", len(execution_failures))
    print("Production approved:", registry.production_approved)
    if insufficient_data:
        print("Rejected series did not satisfy the documented training policy.")
    if execution_failures:
        print("Execution failures are reported above; no failed job created a registry artifact entry.")


if __name__ == "__main__":
    main()
