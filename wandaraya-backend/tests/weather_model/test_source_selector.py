from datetime import date, timedelta

import pytest

from app.weather_model.context.schemas import WeatherSource
from app.weather_model.context.source_selector import WeatherSourceSelector


REFERENCE_DATE = date(2026, 10, 10)


@pytest.mark.parametrize(
    ("days_ahead", "expected_source"),
    [
        (-1, WeatherSource.HISTORICAL),
        (0, WeatherSource.LIVE_API),
        (5, WeatherSource.LIVE_API),
        (6, WeatherSource.DAILY_FORECAST),
        (30, WeatherSource.DAILY_FORECAST),
        (90, WeatherSource.DAILY_FORECAST),
        (91, WeatherSource.DAILY_FORECAST),
        (180, WeatherSource.DAILY_FORECAST),
    ],
)
def test_source_selection(days_ahead: int, expected_source: WeatherSource) -> None:
    result = WeatherSourceSelector.select(
        district_id=78,
        travel_date=REFERENCE_DATE + timedelta(days=days_ahead),
        reference_date=REFERENCE_DATE,
    )
    assert result.selected_source == expected_source
    assert result.days_ahead == days_ahead


def test_daily_forecast_requires_approval() -> None:
    result = WeatherSourceSelector.select(
        district_id=78,
        travel_date=REFERENCE_DATE + timedelta(days=30),
        reference_date=REFERENCE_DATE,
    )
    assert result.requires_production_approval is True


def test_invalid_district() -> None:
    with pytest.raises(ValueError, match="district_id must be positive"):
        WeatherSourceSelector.select(-1, REFERENCE_DATE, REFERENCE_DATE)
