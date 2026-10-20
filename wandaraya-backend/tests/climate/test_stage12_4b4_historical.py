from datetime import date
from app.climate.validation import validate_daily_records
from scripts.acquire_stage12_4b4_batch02 import dry_run_result, request_from_manifest_url

def test_sixteen_year_calendar_days_are_5844():
    assert (date(2025,12,31)-date(2010,1,1)).days + 1 == 5844

def test_multiyear_completeness_is_never_over_100():
    rows=[{"date":"2010-01-01","precipitation_mm":0,"temperature_mean_c":25,"temperature_min_c":20,"temperature_max_c":30}]
    assert validate_daily_records(rows,expected_records=5844)["completeness_percent"] <= 100


def test_batch02_dry_run_has_no_network_or_database_writes():
    result = dry_run_result({"samples": [{"expected_records": 5844}, {"expected_records": 5844}]})
    assert result["network_requests"] == 0
    assert result["postgresql_writes"] is False
    assert result["qdrant_writes"] is False
    assert result["expected_records"] == 11688


def test_batch02_rejects_non_nasa_manifest_url():
    try:
        request_from_manifest_url("https://example.test/not-nasa")
    except ValueError as exc:
        assert "NASA POWER" in str(exc)
    else:
        raise AssertionError("non-NASA URL must be rejected")
