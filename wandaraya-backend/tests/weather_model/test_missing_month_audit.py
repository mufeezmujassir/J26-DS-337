from datetime import date

from app.weather_model.backtesting.audit_missing_months import audit_rows, month_range


def test_month_range_is_inclusive_across_year_boundary() -> None:
    assert list(month_range(date(2024, 11, 1), date(2025, 1, 1))) == [
        date(2024, 11, 1),
        date(2024, 12, 1),
        date(2025, 1, 1),
    ]


def test_audit_distinguishes_absent_records_from_null_measurements() -> None:
    audit = audit_rows(
        [
            {
                "district_id": 94,
                "district_name": "Example",
                "observation_date": date(2021, 1, 1),
                "rainfall_mm": 120.0,
                "temperature_min_c": None,
                "temperature_max_c": 30.0,
            },
            {
                "district_id": 94,
                "district_name": "Example",
                "observation_date": date(2021, 3, 1),
                "rainfall_mm": None,
                "temperature_min_c": 24.0,
                "temperature_max_c": 31.0,
            },
        ],
        start_month=date(2021, 1, 1),
        end_month=date(2021, 3, 1),
    )

    rainfall = audit["series"][0]["targets"]["rainfall_mm"]
    assert rainfall["available_months"] == 1
    assert rainfall["missing_months"] == [
        {"month": "2021-02-01", "kind": "absent_monthly_record"},
        {"month": "2021-03-01", "kind": "missing_measurement"},
    ]
    temperature_min = audit["series"][0]["targets"]["temperature_min_c"]
    assert temperature_min["missing_months"] == [
        {"month": "2021-01-01", "kind": "missing_measurement"},
        {"month": "2021-02-01", "kind": "absent_monthly_record"},
    ]
