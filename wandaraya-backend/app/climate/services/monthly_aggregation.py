"""Monthly climate aggregation service (Stage 12.4C).

Aggregates raw daily climate observations into district-year-month summary records.
Strictly calendar-aware, deterministic, and idempotent.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class DailyObservationRecord:
    observation_date: date
    precipitation_mm: float | None
    temperature_mean_c: float | None
    temperature_min_c: float | None
    temperature_max_c: float | None
    relative_humidity_pct: float | None
    wind_speed: float | None
    solar_radiation: float | None


@dataclass(frozen=True)
class MonthlyAggregateResult:
    district_id: int
    dataset_version_id: int
    year: int
    month: int
    calendar_days: int
    observed_days: int
    completeness_pct: float
    temp_mean_c: float | None
    temp_max_mean_c: float | None
    temp_min_mean_c: float | None
    temp_min_observed_c: float | None
    temp_max_observed_c: float | None
    diurnal_range_mean_c: float | None
    precipitation_total_mm: float | None
    precipitation_daily_mean_mm: float | None
    precipitation_max_daily_mm: float | None
    rainy_days_count: int
    rainy_days_frequency: float
    heavy_rain_days_count: int
    very_heavy_rain_days_count: int
    relative_humidity_mean_pct: float | None
    relative_humidity_min_pct: float | None
    relative_humidity_max_pct: float | None
    wind_speed_mean_ms: float | None
    wind_speed_max_ms: float | None
    solar_radiation_mean_mj: float | None
    solar_radiation_total_mj: float | None
    quality_status: str
    processing_version: str


def compute_monthly_aggregate(
    district_id: int,
    dataset_version_id: int,
    year: int,
    month: int,
    observations: Sequence[DailyObservationRecord],
    processing_version: str = "12.4c_v1",
    rain_threshold_mm: float = 1.0,
    heavy_rain_threshold_mm: float = 10.0,
    very_heavy_rain_threshold_mm: float = 20.0,
) -> MonthlyAggregateResult:
    """Compute monthly aggregate metrics for a specific district, year, and month."""
    _, cal_days = calendar.monthrange(year, month)
    obs_days = len(observations)
    completeness = round((obs_days / cal_days) * 100.0, 2) if cal_days > 0 else 0.0

    t_mean_vals = [o.temperature_mean_c for o in observations if o.temperature_mean_c is not None]
    t_max_vals = [o.temperature_max_c for o in observations if o.temperature_max_c is not None]
    t_min_vals = [o.temperature_min_c for o in observations if o.temperature_min_c is not None]

    diurnal_ranges = [
        o.temperature_max_c - o.temperature_min_c
        for o in observations
        if o.temperature_max_c is not None and o.temperature_min_c is not None
    ]

    p_vals = [o.precipitation_mm for o in observations if o.precipitation_mm is not None]
    rh_vals = [o.relative_humidity_pct for o in observations if o.relative_humidity_pct is not None]
    ws_vals = [o.wind_speed for o in observations if o.wind_speed is not None]
    sol_vals = [o.solar_radiation for o in observations if o.solar_radiation is not None]

    temp_mean = round(sum(t_mean_vals) / len(t_mean_vals), 2) if t_mean_vals else None
    temp_max_mean = round(sum(t_max_vals) / len(t_max_vals), 2) if t_max_vals else None
    temp_min_mean = round(sum(t_min_vals) / len(t_min_vals), 2) if t_min_vals else None
    temp_min_obs = round(min(t_min_vals), 2) if t_min_vals else None
    temp_max_obs = round(max(t_max_vals), 2) if t_max_vals else None
    diurnal_mean = round(sum(diurnal_ranges) / len(diurnal_ranges), 2) if diurnal_ranges else None

    # Precipitation: distinguish sum vs mean daily
    precip_total = round(sum(p_vals), 2) if p_vals else None
    precip_daily_mean = round(sum(p_vals) / len(p_vals), 2) if p_vals else None
    precip_max_daily = round(max(p_vals), 2) if p_vals else None

    rainy_count = sum(1 for p in p_vals if p >= rain_threshold_mm)
    heavy_count = sum(1 for p in p_vals if p >= heavy_rain_threshold_mm)
    very_heavy_count = sum(1 for p in p_vals if p >= very_heavy_rain_threshold_mm)
    rainy_freq = round(rainy_count / obs_days, 4) if obs_days > 0 else 0.0

    rh_mean = round(sum(rh_vals) / len(rh_vals), 2) if rh_vals else None
    rh_min = round(min(rh_vals), 2) if rh_vals else None
    rh_max = round(max(rh_vals), 2) if rh_vals else None

    ws_mean = round(sum(ws_vals) / len(ws_vals), 2) if ws_vals else None
    ws_max = round(max(ws_vals), 2) if ws_vals else None

    solar_mean = round(sum(sol_vals) / len(sol_vals), 2) if sol_vals else None
    solar_total = round(sum(sol_vals), 2) if sol_vals else None

    quality_status = "VALIDATED" if completeness >= 95.0 else "PARTIAL"

    return MonthlyAggregateResult(
        district_id=district_id,
        dataset_version_id=dataset_version_id,
        year=year,
        month=month,
        calendar_days=cal_days,
        observed_days=obs_days,
        completeness_pct=completeness,
        temp_mean_c=temp_mean,
        temp_max_mean_c=temp_max_mean,
        temp_min_mean_c=temp_min_mean,
        temp_min_observed_c=temp_min_obs,
        temp_max_observed_c=temp_max_obs,
        diurnal_range_mean_c=diurnal_mean,
        precipitation_total_mm=precip_total,
        precipitation_daily_mean_mm=precip_daily_mean,
        precipitation_max_daily_mm=precip_max_daily,
        rainy_days_count=rainy_count,
        rainy_days_frequency=rainy_freq,
        heavy_rain_days_count=heavy_count,
        very_heavy_rain_days_count=very_heavy_count,
        relative_humidity_mean_pct=rh_mean,
        relative_humidity_min_pct=rh_min,
        relative_humidity_max_pct=rh_max,
        wind_speed_mean_ms=ws_mean,
        wind_speed_max_ms=ws_max,
        solar_radiation_mean_mj=solar_mean,
        solar_radiation_total_mj=solar_total,
        quality_status=quality_status,
        processing_version=processing_version,
    )
