from app.weather_model.backtesting.generate_model_selection_evidence import (
    evidence_level,
    summarize_backtest,
)


def test_one_fold_comparison_is_marked_as_limited_evidence() -> None:
    assert evidence_level(1, 3) == "limited"


def test_summary_keeps_horizon_metrics_and_does_not_approve_production() -> None:
    report = {
        "district_id": 94,
        "target": "rainfall_mm",
        "training_policy": {"name": "strict_complete_case"},
        "fair_comparison": {
            "status": "completed",
            "common_prediction_count": 3,
            "comparison": {
                "monthly_climatology": {"mae": 10.0, "rmse": 12.0, "bias": 1.0},
                "seasonal_naive": {"mae": 12.0, "rmse": 14.0, "bias": 2.0},
                "prophet": {
                    "mae": 11.0,
                    "rmse": 13.0,
                    "bias": 1.5,
                    "metrics_by_horizon": {"1": {"mae": 11.0}},
                },
            },
        },
        "results": {
            "prophet": {"fold_count": 1, "fold_metadata": [], "skipped_folds": []}
        },
    }

    summary = summarize_backtest(report)

    assert summary["evidence_level"] == "limited"
    assert summary["provisional_recommendation"] == "monthly_climatology"
    assert summary["model_metrics"]["prophet"]["metrics_by_horizon"] == {
        "1": {"mae": 11.0}
    }
    assert summary["production_approved"] is False
