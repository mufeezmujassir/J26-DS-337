"""Run the read-only Stage 9.8.3 forecast-integrity audit."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.weather_model.monitoring.forecast_integrity import run_forecast_integrity_audit


OUTPUT_PATH = Path("data/weather/reports/forecast_integrity/forecast_integrity_report.json")


def main() -> None:
    report = run_forecast_integrity_audit(settings.DATABASE_URL)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\nFORECAST INTEGRITY AUDIT")
    print("-" * 45)
    print("Model runs:", report["total_model_runs"])
    print("Forecast records:", report["total_forecasts"])
    print("Integrity passed:", report["integrity_passed"])
    print("Ready for preliminary review:", report["production_ready_for_review"])
    print("Orphan forecast run IDs:", report["orphan_forecast_run_ids"])
    print("Issues:", report["issue_counts"])
    print("Warnings:", report["warning_counts"])
    print("\nReport:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
