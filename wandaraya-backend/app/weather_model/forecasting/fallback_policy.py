"""Explicit source-order policy; intentionally contains no district substitution."""

from __future__ import annotations

from datetime import date


LIVE_FORECAST_HORIZON_DAYS = 5


def live_provider_supported(requested_date: date, reference_date: date) -> bool:
    """OpenWeather's configured 5-day feed is only valid in this window."""
    days_ahead = (requested_date - reference_date).days
    return 0 <= days_ahead <= LIVE_FORECAST_HORIZON_DAYS
