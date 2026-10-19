from app.climate.validation import validate_daily_records

def test_rejects_negative_rain_and_bad_temperature_order():
    result=validate_daily_records([{"date":"2024-01-01","precipitation_mm":-1,"temperature_mean_c":30,"temperature_min_c":32,"temperature_max_c":31}])
    assert result["accepted"] == 0
    assert {"negative_precipitation","temperature_order_invalid"}.issubset(result["rejections"][0]["reasons"])

def test_accepts_valid_daily_record():
    result=validate_daily_records([{"date":"2024-01-01","precipitation_mm":1,"temperature_mean_c":28,"temperature_min_c":25,"temperature_max_c":31}])
    assert result["accepted"] == 1

def test_explicit_multiyear_expected_count_is_used():
    result=validate_daily_records([{"date":"2010-01-01","precipitation_mm":1,"temperature_mean_c":28,"temperature_min_c":25,"temperature_max_c":31}], expected_records=5844)
    assert result["completeness_percent"] == 0.02
