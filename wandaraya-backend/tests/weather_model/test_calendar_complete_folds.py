from datetime import date

from app.weather_model.backtesting.rolling_origin import _folds, add_months
from app.weather_model.backtesting.schemas import MonthlyObservation


def make_observations(count=58, missing_rows=None, null_months=None):
    missing_rows = missing_rows or set()
    null_months = null_months or set()
    observations = []
    for index in range(count):
        month = add_months(date(2021, 1, 1), index)
        if month in missing_rows:
            continue
        observations.append(
            MonthlyObservation(
                month=month,
                value=None if month in null_months else float(25 + (index % 12) * 0.1),
            )
        )
    return observations


def get_folds(observations, missing_aware):
    return list(
        _folds(
            observations,
            horizon_months=3,
            min_training_months=36,
            step_months=3,
            missing_aware_training=missing_aware,
            min_training_coverage=0.95,
        )
    )


def test_missing_temperature_row_is_represented_and_prepared() -> None:
    missing_month = date(2022, 5, 1)
    folds = get_folds(make_observations(missing_rows={missing_month}), missing_aware=True)
    successful = [fold for fold in folds if fold[3] is None]

    assert successful
    origin, train, test, reason, metadata = successful[0]
    assert reason is None
    assert missing_month in [item.month for item in train]
    assert all(item.value is not None for item in train)
    assert missing_month.isoformat() in metadata["imputed_months"]
    assert all(item.month > origin for item in test)


def test_rainfall_does_not_fill_absent_training_row() -> None:
    folds = get_folds(
        make_observations(missing_rows={date(2022, 5, 1)}),
        missing_aware=False,
    )

    assert folds
    assert all(reason == "incomplete_training_history" for _, _, _, reason, _ in folds)


def test_origins_use_calendar_spacing_and_stop_at_complete_horizon() -> None:
    folds = get_folds(make_observations(missing_rows={date(2022, 5, 1)}), missing_aware=True)
    origins = [fold[0] for fold in folds]

    assert origins == [
        date(2023, 12, 1),
        date(2024, 3, 1),
        date(2024, 6, 1),
        date(2024, 9, 1),
        date(2024, 12, 1),
        date(2025, 3, 1),
        date(2025, 6, 1),
    ]
    assert all(add_months(origin, 3) <= date(2025, 10, 1) for origin in origins)


def test_missing_actual_in_scheduled_window_has_explicit_reason() -> None:
    folds = get_folds(
        make_observations(missing_rows={date(2024, 2, 1)}),
        missing_aware=True,
    )
    december_2023 = next(fold for fold in folds if fold[0] == date(2023, 12, 1))

    assert december_2023[3] == "missing_test_actual"
    assert december_2023[4]["missing_test_months"] == ["2024-02-01"]
