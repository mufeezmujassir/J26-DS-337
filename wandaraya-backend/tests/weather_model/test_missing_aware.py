from datetime import date

import pytest

from app.weather_model.backtesting.missing_aware import (
    MonthlyObservation,
    add_months,
    prepare_training_history,
)


def make_history(count=48, missing=None):
    start = date(2021, 1, 1)
    return [
        MonthlyObservation(
            month=add_months(start, index),
            value=None if add_months(start, index) == missing else 20.0 + index * 0.1,
        )
        for index in range(count)
    ]


def test_complete_history_is_accepted() -> None:
    result = prepare_training_history(make_history(), origin=date(2024, 12, 1))
    assert result.accepted
    assert result.coverage_ratio == 1.0
    assert result.imputed_months == ()


def test_may_2022_missing_temperature_is_interpolated() -> None:
    result = prepare_training_history(
        make_history(missing=date(2022, 5, 1)), origin=date(2024, 12, 1)
    )
    assert result.accepted
    assert result.coverage_ratio == pytest.approx(47 / 48)
    assert result.imputed_months == ("2022-05-01",)
    assert dict(result.observations)[date(2022, 5, 1)] == pytest.approx(21.6)


def test_history_below_coverage_threshold_is_rejected() -> None:
    history = make_history()
    history[10] = MonthlyObservation(history[10].month, None)
    history[11] = MonthlyObservation(history[11].month, None)
    history[12] = MonthlyObservation(history[12].month, None)
    result = prepare_training_history(history, origin=date(2024, 12, 1))
    assert result.accepted is False
    assert result.reason == "insufficient_coverage"


def test_missing_month_without_neighbors_is_rejected() -> None:
    history = make_history(missing=date(2021, 1, 1))
    result = prepare_training_history(history, origin=date(2024, 12, 1))
    assert result.accepted is False
    assert result.reason == "unable_to_impute_month"


def test_future_observations_are_never_used_for_training() -> None:
    history = make_history(60, missing=date(2022, 5, 1))
    result = prepare_training_history(history, origin=date(2022, 4, 1), min_train_months=12)
    assert result.accepted
    assert all(month <= date(2022, 4, 1) for month, _ in result.observations)


def test_invalid_origin_or_duplicate_month_is_rejected() -> None:
    with pytest.raises(ValueError, match="Origin"):
        prepare_training_history(make_history(), origin=date(2024, 12, 2))
    duplicate = make_history()
    duplicate.append(duplicate[-1])
    with pytest.raises(ValueError, match="Duplicate"):
        prepare_training_history(duplicate, origin=date(2024, 12, 1))
