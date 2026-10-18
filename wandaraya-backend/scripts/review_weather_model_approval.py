"""Apply an explicit, audited human approval or rejection decision.

This is intentionally separate from training and import.  It refuses approval
unless the Stage 9.8 evaluator has made the run eligible for review.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.weather_forecast import WeatherForecast
from app.models.weather_model_run import WeatherModelRun
from app.weather_model.monitoring.approval import ModelApprovalEvaluator, QualityMetrics
from app.weather_model.monitoring.forecast_integrity import validate_forecast_run
from app.weather_model.persistence.database import get_weather_engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--decision", choices=("approve", "reject"), required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reason", required=True)
    arguments = parser.parse_args()

    engine = get_weather_engine()
    try:
        with Session(engine) as session, session.begin():
            run = session.get(WeatherModelRun, arguments.run_id)
            if run is None:
                raise ValueError(f"Unknown model run: {arguments.run_id}")
            metrics = QualityMetrics.from_mapping(run.parameters.get("quality_metrics"))
            assessment = ModelApprovalEvaluator().evaluate(
                target=run.target,
                model_name=run.model_name,
                training_observations=run.training_observations,
                validation_gate_passed=run.validation_gate_passed,
                metrics=metrics,
            )
            if arguments.decision == "approve" and not assessment.eligible_for_review:
                raise ValueError(
                    "This run is not eligible for approval: " + " ".join(assessment.reasons)
                )
            if arguments.decision == "approve":
                forecasts = session.scalars(
                    select(WeatherForecast).where(WeatherForecast.run_id == run.run_id)
                ).all()
                integrity = validate_forecast_run(
                    {
                        "run_id": run.run_id,
                        "district_id": run.district_id,
                        "target": run.target,
                        "model_name": run.model_name,
                        "latest_calendar_month": run.latest_calendar_month,
                        "latest_observed_month": run.latest_observed_month,
                        "latest_month_missing": run.latest_month_missing,
                        "forecast_horizon_months": run.forecast_horizon_months,
                        "training_observations": run.training_observations,
                        "validation_gate_passed": run.validation_gate_passed,
                        "production_approved": run.production_approved,
                        "parameters": run.parameters,
                    },
                    [
                        {
                            "forecast_month": item.forecast_month,
                            "predicted_value": item.predicted_value,
                            "lower_bound": item.lower_bound,
                            "upper_bound": item.upper_bound,
                            "raw_prediction": item.raw_prediction,
                        }
                        for item in forecasts
                    ],
                )
                if not integrity["production_ready_for_review"]:
                    raise ValueError(
                        "This run is not currently production-ready: "
                        + ", ".join(integrity["issues"] + integrity["readiness_blockers"])
                    )

            # Keep review provenance beside the training metadata. The
            # production flag changes only after this explicit named decision.
            parameters = dict(run.parameters)
            parameters["approval_review"] = {
                "decision": arguments.decision,
                "reviewer": arguments.reviewer,
                "reason": arguments.reason,
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
                "automated_assessment": assessment.lifecycle_state,
            }
            run.parameters = parameters
            run.production_approved = arguments.decision == "approve"
            run.status = "approved" if run.production_approved else "rejected"

            print(f"Run: {run.run_id}")
            print(f"Decision: {arguments.decision}")
            print(f"Production approved: {run.production_approved}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
