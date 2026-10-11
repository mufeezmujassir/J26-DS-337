"""Run the read-only Stage 9.8.1 weather-model registry integrity audit."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.weather_model.monitoring.registry_audit import run_registry_audit


OUTPUT_PATH = Path("data/weather/reports/registry/weather_registry_audit.json")


def main() -> None:
    report = run_registry_audit(settings.DATABASE_URL)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    print("\nWEATHER MODEL REGISTRY AUDIT")
    print("-" * 45)
    print("Model runs:", report["total_model_runs"])
    print("Forecast records:", report["total_forecasts"])
    print("Integrity passed:", report["integrity_passed"])
    print("Validation gate passed:", report["validation_gate_passed"])
    print("Production approved:", report["production_approved"])
    print("Issues:", report["issue_counts"])
    print("Warnings:", report["warning_counts"])
    print("\nReport saved:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
