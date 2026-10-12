from app.weather_model.backtesting.diagnose_national_benchmark import diagnose_report


def test_diagnosis_groups_zero_prediction_fold_reasons() -> None:
    result = diagnose_report(
        {
            "results": [
                {
                    "district_id": 78,
                    "target": "rainfall_mm",
                    "fair_comparison_status": "completed",
                    "common_prediction_count": 3,
                },
                {
                    "district_id": 94,
                    "target": "rainfall_mm",
                    "common_prediction_count": 0,
                    "skipped_folds": [
                        {"reason": "incomplete_training_history"},
                        {"reason": "missing_test_actual"},
                    ],
                },
            ],
            "failures": [{"district_id": 95, "target": "rainfall_mm"}],
            "skipped": [{"district_id": 73, "target": "temperature_min_c"}],
        }
    )
    assert result["completed_comparisons"] == 1
    assert result["zero_common_prediction_series"] == 1
    assert result["zero_prediction_reason_counts"] == {
        "incomplete_training_history": 1,
        "missing_test_actual": 1,
    }
    assert result["execution_or_report_failures"] == 1
