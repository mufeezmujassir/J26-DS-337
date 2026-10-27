"""Strict, read-only loader for canonical district monthly observations."""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.weather_model.backtesting.schemas import MonthlyObservation


ALLOWED_TARGETS = {
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
}


def load_monthly_observations_from_csv(
    path: str | Path,
    district_id: int,
    target: str,
    cutoff: date | None = None,
) -> list[MonthlyObservation]:
    """Load one district/target from the canonical NASA-derived monthly CSV."""
    if target not in ALLOWED_TARGETS:
        raise ValueError(f"Unsupported target: {target}")
    frame = pd.read_csv(path, parse_dates=["observation_date"])
    required = {"district_id", "observation_date", target}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Monthly CSV is missing columns: {sorted(missing)}")
    frame = frame[frame["district_id"] == district_id].sort_values("observation_date")
    if cutoff is not None:
        frame = frame[frame["observation_date"].dt.date <= cutoff]
    if frame["observation_date"].duplicated().any():
        raise ValueError(f"Duplicate month for district {district_id}")
    observations: list[MonthlyObservation] = []
    for row in frame.itertuples(index=False):
        month = row.observation_date.date()
        value = getattr(row, target)
        value = None if pd.isna(value) else float(value)
        if month.day != 1:
            raise ValueError(f"Non-month-start date: {month}")
        if value is not None and not math.isfinite(value):
            raise ValueError(f"Non-finite observation: {month}")
        if target == "rainfall_mm" and value is not None and value < 0:
            raise ValueError(f"Negative rainfall: {month}")
        observations.append(MonthlyObservation(month=month, value=value))
    return observations


def load_monthly_observations(
    engine: Engine,
    district_id: int,
    target: str,
    cutoff: date | None = None,
) -> list[MonthlyObservation]:
    """Load calendar rows without filling or hiding missing target values."""
    if target not in ALLOWED_TARGETS:
        raise ValueError(f"Unsupported target: {target}")
    if district_id <= 0:
        raise ValueError("Invalid district ID")

    # SQL identifiers cannot be bound. ``target`` is safe because it is
    # constrained to the small allow-list above.
    cutoff_clause = "AND observation_date <= :cutoff" if cutoff is not None else ""
    query = text(
        f"""
        SELECT observation_date, {target} AS value
        FROM district_weather_monthly
        WHERE district_id = :district_id
          {cutoff_clause}
        ORDER BY observation_date
        """
    )
    parameters = {"district_id": district_id}
    if cutoff is not None:
        parameters["cutoff"] = cutoff
    with engine.connect() as connection:
        rows = connection.execute(query, parameters).mappings().all()

    observations: list[MonthlyObservation] = []
    seen_months: set[date] = set()
    for row in rows:
        month = row["observation_date"]
        if isinstance(month, datetime):
            month = month.date()
        raw_value = row["value"]
        value = None if raw_value is None else float(raw_value)
        if month.day != 1:
            raise ValueError(f"Non-month-start date: {month}")
        if month in seen_months:
            raise ValueError(f"Duplicate month: {month}")
        if value is not None and not math.isfinite(value):
            raise ValueError(f"Non-finite observation: {month}")
        if target == "rainfall_mm" and value is not None and value < 0:
            raise ValueError(f"Negative rainfall: {month}")
        seen_months.add(month)
        observations.append(MonthlyObservation(month=month, value=value))
    return observations
