"""Create a read-only Stage 9.8 model-quality audit report.

This command never updates ``weather_model_runs`` and never approves a model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.weather_model_run import WeatherModelRun
from app.weather_model.monitoring.registry_audit import audit_model_runs
from app.weather_model.persistence.database import get_weather_engine


DEFAULT_OUTPUT = Path("data/weather/monitoring/reports/model_registry_audit.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()

    engine = get_weather_engine()
    try:
        with Session(engine) as session:
            runs = session.scalars(
                select(WeatherModelRun).order_by(WeatherModelRun.created_at_utc.desc())
            ).all()
    finally:
        engine.dispose()

    report = audit_model_runs(runs)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    candidates = sum(item["decision"]["eligible_for_review"] for item in report)
    approved = sum(item["production_approved"] for item in report)
    print(f"Model runs audited: {len(report)}")
    print(f"Eligible for human review: {candidates}")
    print(f"Already production approved: {approved}")
    print(f"Report: {arguments.output}")


if __name__ == "__main__":
    main()
