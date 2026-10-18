"""Generate a factual Stage 9.8.12 weather-layer validation report.

The report validates persisted artifacts and configuration only.  Airflow task
execution is intentionally never inferred from an import check.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.weather_model.training.candidate_artifacts import load_candidate_artifact


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = PROJECT_ROOT / "data/weather/reports/registry/weather_model_registry.json"
COVERAGE_PATH = PROJECT_ROOT / "data/weather/reports/backtesting/district_coverage_audit.json"
OUTPUT_PATH = PROJECT_ROOT / "data/weather/reports/validation/weather_layer_end_to_end_validation.json"
DAG_SPECS = (
    ("weather_live", "weather_live.py", "0 */3 * * *"),
    ("weather_historical", "weather_historical.py", "0 2 1 * *"),
    ("weather_model_train", "weather_model_train.py", "0 3 2 * *"),
    ("weather_predictions_cache", "weather_predictions_cache.py", "0 4 * * 1"),
)


def _artifact_integrity() -> dict[str, Any]:
    manifests = sorted((PROJECT_ROOT / "data/weather/artifacts/candidates").glob("**/manifest.json"))
    valid, invalid = 0, []
    for manifest_path in manifests:
        try:
            manifest, _ = load_candidate_artifact(manifest_path)
            required = {"artifact_version", "district_id", "target", "model_name", "provenance", "registry_evidence_fingerprint"}
            missing = sorted(required - manifest.keys())
            if missing:
                raise ValueError("manifest missing: " + ", ".join(missing))
            if manifest.get("production_approved") is not False:
                raise ValueError("candidate manifest must remain unapproved")
            valid += 1
        except Exception as exc:  # Report every damaged artifact; do not stop auditing.
            invalid.append({"manifest": str(manifest_path.relative_to(PROJECT_ROOT)), "reason": str(exc)})
    return {"manifests_found": len(manifests), "checksum_valid": valid, "invalid": invalid}


def _registry_status() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"status": "missing", "entries": 0, "production_approved": 0, "candidate_references": 0}
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = registry.get("entries", [])
    references = sum(len(entry.get("candidate_artifacts", {})) for entry in entries)
    return {
        "status": "loaded",
        "entries": len(entries),
        "production_approved": sum(bool(entry.get("production_approved")) for entry in entries),
        "candidate_references": references,
        "registry_production_approved": bool(registry.get("production_approved")),
    }


def _coverage_status() -> dict[str, Any]:
    if not COVERAGE_PATH.exists():
        return {"status": "not_generated"}
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    return {
        "status": "loaded_existing_audit",
        "districts": len(coverage),
        "districts_with_observations": sum(item.get("total_months", 0) > 0 for item in coverage),
        "candidate_district_target_pairs": sum(len(item.get("candidate_targets", [])) for item in coverage),
        "source": str(COVERAGE_PATH.relative_to(PROJECT_ROOT)),
    }


def _dag_status(*, import_status: str = "requires_airflow_runtime_check") -> list[dict[str, Any]]:
    dag_dir = PROJECT_ROOT / "dags"
    rows = []
    for dag_id, filename, default_schedule in DAG_SPECS:
        path = dag_dir / filename
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        rows.append({
            "dag_id": dag_id,
            "file": str(path.relative_to(PROJECT_ROOT)),
            "definition_present": bool(content),
            "paused_by_default": "is_paused_upon_creation=True" in content,
            "retry_and_timeout_configured": "retries=" in content and "execution_timeout=" in content,
            "default_schedule_utc": default_schedule,
            "import_status": import_status,
            "task_execution_status": "not_claimed_by_static_validation",
        })
    return rows


def _test_result(run_tests: bool) -> dict[str, Any]:
    if not run_tests:
        return {"status": "not_run"}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/weather_model", "-q"],
        cwd=PROJECT_ROOT, text=True, capture_output=True, check=False,
    )
    match = re.search(r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?", completed.stdout)
    passed = int(match.group(1)) if match else 0
    failed = int(match.group(2) or 0) if match else (1 if completed.returncode else 0)
    skipped = int(match.group(3) or 0) if match else 0
    return {"status": "completed", "passed": passed, "failed": failed, "skipped": skipped, "return_code": completed.returncode, "output_tail": completed.stdout[-2000:]}


def build_report(
    *, run_tests: bool = False, airflow_import_status: str = "requires_airflow_runtime_check"
) -> dict[str, Any]:
    artifacts = _artifact_integrity()
    registry = _registry_status()
    tests = _test_result(run_tests)
    readiness_reasons = [
        "Airflow task execution is not asserted by this report; inspect task instances and logs after a deliberate manual trigger.",
        "No model artifact is production-approved, so long-range model forecasts remain unavailable by design.",
        "Historical coverage remains limited to districts and target series represented in the existing coverage audit.",
    ]
    if artifacts["invalid"]:
        readiness = "blocked"
        readiness_reasons.insert(0, "One or more candidate artifacts failed integrity verification.")
    else:
        readiness = "conditionally_ready"
    return {
        "stage": "9.8.12",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": readiness,
        "readiness_reasons": readiness_reasons,
        "tests": tests,
        "data_coverage": _coverage_status(),
        "model_registry": registry,
        "artifact_integrity": artifacts,
        "airflow_dags": _dag_status(import_status=airflow_import_status),
        "scientific_safeguards": {
            "temperature_minimum_coverage": 0.95,
            "rainfall_imputation": "prohibited",
            "automatic_production_approval": False,
            "cross_district_substitution": "prohibited_without_validated_policy",
            "monthly_rainfall_interpreted_as_daily": False,
        },
        "known_limitations": readiness_reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tests", action="store_true", help="Run tests/weather_model and record its exact result.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--airflow-import-status",
        choices=("passed", "failed", "requires_airflow_runtime_check"),
        default="requires_airflow_runtime_check",
        help="Record the result of a separately executed `airflow dags list-import-errors` check.",
    )
    args = parser.parse_args()
    report = build_report(run_tests=args.run_tests, airflow_import_status=args.airflow_import_status)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"readiness": report["readiness"], "report": str(args.output), "tests": report["tests"]}, indent=2))


if __name__ == "__main__":
    main()
