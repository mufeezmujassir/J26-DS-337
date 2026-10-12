from types import SimpleNamespace

from app.weather_model.backtesting.run_national_benchmark import (
    build_output,
    national_report_matches_configuration,
)


def test_resume_requires_an_identical_benchmark_configuration() -> None:
    args = SimpleNamespace(
        min_train_months=36,
        horizon=3,
        step_months=3,
        min_coverage=0.95,
    )
    report = {
        "configuration": {
            "min_train_months": 36,
            "horizon_months": 3,
            "step_months": 3,
            "min_coverage": 0.95,
        }
    }

    assert national_report_matches_configuration(report, args)

    report["configuration"]["horizon_months"] = 6
    assert not national_report_matches_configuration(report, args)


def test_checkpoint_output_marks_incomplete_runs() -> None:
    args = SimpleNamespace(
        min_train_months=36,
        horizon=3,
        step_months=3,
        min_coverage=0.95,
    )
    result = {
        "fair_comparison_status": "completed",
        "provisional_lowest_mae_model": "prophet",
    }

    output = build_output(
        args,
        [(94, "rainfall_mm")],
        [result],
        [],
        [],
        complete=False,
    )

    assert output["complete"] is False
    assert output["summary"]["completed_fair_comparisons"] == 1
