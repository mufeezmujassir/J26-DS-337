
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


TARGETS = (
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
)

MODELS = (
    "monthly_climatology",
    "seasonal_naive",
    "prophet",
)

REPORT_DIR = Path("data/weather/reports/backtesting")
NATIONAL_REPORT = REPORT_DIR / "national_benchmark_report.json"
PROGRESS_REPORT = REPORT_DIR / "national_benchmark_progress.json"
DEFAULT_NASA_MONTHLY_PATH = Path("data/weather/modeling/nasa_power/district_weather_monthly.csv")


def get_nasa_district_target_coverage(path):
    frame = pd.read_csv(path, parse_dates=["observation_date"])
    rows = []
    for district_id, district in frame.groupby("district_id", sort=True):
        rows.append({
            "district_id": int(district_id),
            "total_months": len(district),
            "first_month": district["observation_date"].min(),
            "last_month": district["observation_date"].max(),
            "rainfall_count": int(district["rainfall_mm"].count()),
            "min_temp_count": int(district["temperature_min_c"].count()),
            "max_temp_count": int(district["temperature_max_c"].count()),
        })
    return rows


def get_district_target_coverage(database_url):
    engine = create_engine(database_url)

    query = text("""
        SELECT
            district_id,
            COUNT(*) AS total_months,
            MIN(observation_date) AS first_month,
            MAX(observation_date) AS last_month,
            COUNT(rainfall_mm) AS rainfall_count,
            COUNT(temperature_min_c) AS min_temp_count,
            COUNT(temperature_max_c) AS max_temp_count
        FROM district_weather_monthly
        GROUP BY district_id
        ORDER BY district_id
    """)

    try:
        with engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(query).mappings()
            ]
    finally:
        engine.dispose()


def report_path(district_id, target):
    return REPORT_DIR / (
        f"district_{district_id}_{target}_backtest.json"
    )


def job_key(district_id, target):
    """Return a stable identity for one district/target benchmark job."""
    return district_id, target


def write_json(path, payload):
    """Atomically persist a report so an interrupted run keeps valid JSON."""
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def national_report_matches_configuration(report, args):
    """Whether a prior national report can safely be resumed."""
    configuration = report.get("configuration", {})
    requested_source = getattr(args, "data_source", "database")
    recorded_source = configuration.get("data_source", "database")
    requested_nasa_path = str(getattr(args, "nasa_monthly_path", DEFAULT_NASA_MONTHLY_PATH))
    return (
        configuration.get("min_train_months") == args.min_train_months
        and configuration.get("horizon_months") == args.horizon
        and configuration.get("step_months") == args.step_months
        and configuration.get("min_coverage") == args.min_coverage
        and recorded_source == requested_source
        and (
            requested_source != "nasa_power"
            or configuration.get("nasa_monthly_path") == requested_nasa_path
        )
    )


def build_output(args, jobs, results, failures, skipped, *, complete):
    data_source = getattr(args, "data_source", "database")
    nasa_monthly_path = str(getattr(args, "nasa_monthly_path", DEFAULT_NASA_MONTHLY_PATH))
    completed = sum(
        item["fair_comparison_status"] == "completed"
        and item["provisional_lowest_mae_model"] is not None
        for item in results
    )

    return {
        "stage": "9.8.7.5",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": complete,
        "configuration": {
            "min_train_months": args.min_train_months,
            "horizon_months": args.horizon,
            "step_months": args.step_months,
            "min_coverage": args.min_coverage,
            "data_source": data_source,
            "nasa_monthly_path": nasa_monthly_path if data_source == "nasa_power" else None,
        },
        "summary": {
            "jobs_attempted": len(jobs),
            "reports_loaded": len(results),
            "completed_fair_comparisons": completed,
            "failures": len(failures),
            "insufficient_history": len(skipped),
        },
        "results": results,
        "failures": failures,
        "skipped": skipped,
        "production_approved": False,
    }


def run_backtest(
    district_id,
    target,
    min_train_months,
    horizon,
    step_months,
    data_source,
    nasa_monthly_path,
):
    command = [
        sys.executable,
        "-m",
        "app.weather_model.backtesting.run_database_backtest",
        "--district-id",
        str(district_id),
        "--target",
        target,
        "--min-train-months",
        str(min_train_months),
        "--horizon",
        str(horizon),
        "--step-months",
        str(step_months),
        "--data-source",
        data_source,
        "--nasa-monthly-path",
        str(nasa_monthly_path),
    ]

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    return process.returncode, process.stdout, process.stderr


def summarize_report(report):
    comparison = report.get("fair_comparison", {})
    metrics = comparison.get("comparison", {})

    model_metrics = {}

    for model in MODELS:
        values = metrics.get(model, {})
        model_metrics[model] = {
            "mae": values.get("mae"),
            "rmse": values.get("rmse"),
            "bias": values.get("bias"),
            "prediction_count": values.get("prediction_count"),
            "metrics_by_horizon": values.get(
                "metrics_by_horizon", {}
            ),
        }

    valid_models = {
        name: values
        for name, values in model_metrics.items()
        if values["mae"] is not None
        and values["prediction_count"]
    }

    provisional_best = (
        min(
            valid_models,
            key=lambda name: valid_models[name]["mae"],
        )
        if len(valid_models) == len(MODELS)
        and comparison.get("status") == "completed"
        else None
    )

    climatology = model_metrics["monthly_climatology"]["mae"]
    prophet = model_metrics["prophet"]["mae"]

    improvement = None
    if climatology is not None and climatology > 0 and prophet is not None:
        improvement = round(
            (climatology - prophet) / climatology * 100,
            2,
        )

    prophet_folds = report.get("results", {}).get(
        "prophet", {}
    )

    return {
        "district_id": report["district_id"],
        "target": report["target"],
        "observation_count": report.get("observation_count"),
        "fair_comparison_status": comparison.get("status"),
        "common_prediction_count": comparison.get(
            "common_prediction_count", 0
        ),
        "model_metrics": model_metrics,
        "prophet_improvement_over_climatology_percent": improvement,
        "provisional_lowest_mae_model": provisional_best,
        "imputed_training_folds": sum(
            bool(item.get("imputed_months"))
            for item in prophet_folds.get("fold_metadata", [])
        ),
        "skipped_folds": prophet_folds.get("skipped_folds", []),
        "production_approved": False,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--min-train-months", type=int, default=36)
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--district-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--data-source",
        choices=("nasa_power", "database"),
        default="nasa_power",
    )
    parser.add_argument("--nasa-monthly-path", type=Path, default=DEFAULT_NASA_MONTHLY_PATH)
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse matching successful jobs from the latest national or "
            "checkpoint report, then rerun only unfinished/failed jobs."
        ),
    )

    args = parser.parse_args()

    if args.min_train_months < 1 or args.horizon < 1 or args.step_months < 1:
        parser.error("Training months, horizon, and step must be positive.")

    if not 0 < args.min_coverage <= 1:
        parser.error("min-coverage must be between 0 and 1.")

    # The existing backtester uses a 95% training coverage policy.
    # Do not advertise another value until its CLI supports it.
    if args.min_coverage != 0.95:
        parser.error(
            "The existing backtester currently supports 0.95 coverage."
        )

    if args.resume and args.district_id is not None:
        parser.error(
            "--resume must run the complete benchmark; do not combine it "
            "with --district-id."
        )

    if args.data_source == "nasa_power":
        coverage = get_nasa_district_target_coverage(args.nasa_monthly_path)
    else:
        database_url = os.environ["DATABASE_URL"]
        coverage = get_district_target_coverage(database_url)

    jobs = []
    skipped = []

    for row in coverage:
        district_id = row["district_id"]

        if args.district_id is not None and district_id != args.district_id:
            continue

        for target, count_field in (
            ("rainfall_mm", "rainfall_count"),
            ("temperature_min_c", "min_temp_count"),
            ("temperature_max_c", "max_temp_count"),
        ):
            observed_count = int(row[count_field])

            # This is a preliminary filter, not the complete
            # missing-aware training eligibility decision.
            if observed_count < args.min_train_months:
                skipped.append({
                    "district_id": district_id,
                    "target": target,
                    "reason": "insufficient_observed_months",
                    "observed_months": observed_count,
                })
                continue

            jobs.append((district_id, target))

    print(f"Eligible preliminary jobs: {len(jobs)}")
    print(f"Insufficient-history series: {len(skipped)}")

    if args.dry_run:
        for district_id, target in jobs:
            print(f"WOULD RUN: district={district_id} target={target}")
        return

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    results_by_job = {}
    failures = []

    if args.resume:
        # An incomplete checkpoint is newer and more useful than the last
        # completed national report.  This lets an interrupted refresh resume
        # from the exact job that was last persisted.
        resume_source = None
        for candidate in (PROGRESS_REPORT, NATIONAL_REPORT):
            if not candidate.exists():
                continue
            try:
                candidate_output = json.loads(
                    candidate.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                continue
            if national_report_matches_configuration(candidate_output, args):
                resume_source = candidate
                prior_output = candidate_output
                break

        if resume_source is not None:
            try:
                scheduled_jobs = {
                    job_key(district_id, target)
                    for district_id, target in jobs
                }
                for item in prior_output.get("results", []):
                    key = job_key(
                        item.get("district_id"),
                        item.get("target"),
                    )
                    if key in scheduled_jobs:
                        results_by_job[key] = item
                print(
                    "Resuming from",
                    resume_source,
                    f"({len(results_by_job)} successful jobs reused).",
                )
            except (KeyError, TypeError) as exc:
                print(f"Ignoring invalid resume report: {exc}")
        elif PROGRESS_REPORT.exists() or NATIONAL_REPORT.exists():
            print(
                "Resume report configuration does not match; "
                "running every eligible job."
            )

    def ordered_results():
        return [
            results_by_job[job_key(district_id, target)]
            for district_id, target in jobs
            if job_key(district_id, target) in results_by_job
        ]

    def checkpoint():
        write_json(
            PROGRESS_REPORT,
            build_output(
                args,
                jobs,
                ordered_results(),
                failures,
                skipped,
                complete=False,
            ),
        )

    for index, (district_id, target) in enumerate(jobs, start=1):
        key = job_key(district_id, target)
        if key in results_by_job:
            print(
                f"[{index}/{len(jobs)}] District {district_id}: "
                f"{target} (reused)",
                flush=True,
            )
            continue

        print(
            f"[{index}/{len(jobs)}] "
            f"District {district_id}: {target}",
            flush=True,
        )

        code, stdout, stderr = run_backtest(
            district_id,
            target,
            args.min_train_months,
            args.horizon,
            args.step_months,
            args.data_source,
            args.nasa_monthly_path,
        )

        path = report_path(district_id, target)

        if code != 0 or not path.exists():
            failures.append({
                "district_id": district_id,
                "target": target,
                "return_code": code,
                "error": stderr[-2000:],
            })
            print("  FAILED")
            checkpoint()
            continue

        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if (
                report.get("district_id") != district_id
                or report.get("target") != target
                or report.get("min_train_months") != args.min_train_months
                or report.get("horizon_months") != args.horizon
                or report.get("step_months") != args.step_months
            ):
                raise ValueError("Report identity or configuration mismatch")

            summary = summarize_report(report)
            results_by_job[key] = summary

            print(
                "  Common predictions:",
                summary["common_prediction_count"],
            )
            print(
                "  Provisional lowest MAE:",
                summary["provisional_lowest_mae_model"],
            )

        except (ValueError, KeyError, TypeError) as exc:
            failures.append({
                "district_id": district_id,
                "target": target,
                "error": str(exc),
            })

        checkpoint()

    output = build_output(
        args,
        jobs,
        ordered_results(),
        failures,
        skipped,
        complete=True,
    )
    write_json(NATIONAL_REPORT, output)
    write_json(PROGRESS_REPORT, output)

    print("\nNational benchmark completed.")
    print(json.dumps(output["summary"], indent=2))
    print(f"Report: {NATIONAL_REPORT}")


if __name__ == "__main__":
    main()
