from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.weather_model.context.monthly_forecast_provider import MonthlyForecastProvider


REQUESTED_MONTH = date(2026, 11, 1)
CREATED_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _run(target: str, run_id: str = "run-1", approved: bool = True):
    return SimpleNamespace(
        run_id=run_id,
        target=target,
        model_name="prophet",
        production_approved=approved,
        training_cutoff=date(2026, 10, 1),
        created_at_utc=CREATED_AT,
    )


def _forecast(run_id: str = "run-1", value: float = 100.0):
    return SimpleNamespace(
        run_id=run_id,
        forecast_month=REQUESTED_MONTH,
        predicted_value=value,
        created_at=CREATED_AT,
    )


def test_returns_partial_result_for_available_approved_targets() -> None:
    result = MonthlyForecastProvider._build_result(
        78, REQUESTED_MONTH, [(_run("rainfall_mm"), _forecast())]
    )
    assert result.available is True
    assert result.rainfall is not None
    assert result.rainfall.value == 100.0
    assert result.rainfall.unit == "mm/month"
    assert result.missing_targets == ["temperature_min_c", "temperature_max_c"]


def test_rejects_unapproved_or_mismatched_records() -> None:
    result = MonthlyForecastProvider._build_result(
        78,
        REQUESTED_MONTH,
        [
            (_run("rainfall_mm", approved=False), _forecast()),
            (_run("temperature_min_c", run_id="run-2"), _forecast("wrong-run")),
        ],
    )
    assert result.available is False
    assert result.missing_targets == list(MonthlyForecastProvider.TARGETS)
