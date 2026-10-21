"""16-Year Month-of-Year Climatology Service (Stage 12.4C).

Calculates long-term historical monthly climatology baselines across annual monthly aggregates.
Uses annual monthly totals as observations to avoid pseudoreplication.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from app.climate.services.monthly_aggregation import MonthlyAggregateResult


@dataclass(frozen=True)
class MonthlyClimatologyResult:
    district_id: int
    dataset_version_id: int
    month: int
    reference_period: str
    processing_version: str
    rainfall_mean_mm: float | None
    rainfall_median_mm: float | None
    rainfall_std_mm: float | None
    rainfall_iqr_mm: float | None
    rainfall_p10_mm: float | None
    rainfall_p90_mm: float | None
    rainfall_min_mm: float | None
    rainfall_max_mm: float | None
    rainfall_cv: float | None
    rainy_day_frequency_mean: float | None
    heavy_rain_days_mean: float | None
    very_heavy_rain_days_mean: float | None
    temp_mean_c: float | None
    temp_max_mean_c: float | None
    temp_min_mean_c: float | None
    diurnal_range_mean_c: float | None
    relative_humidity_mean_pct: float | None
    wind_speed_mean_ms: float | None
    solar_radiation_mean_mj: float | None
    solar_radiation_total_mean_mj: float | None
    valid_years_count: int
    total_observed_days: int
    geographic_uncertainty: str


def compute_monthly_climatology(
    district_id: int,
    dataset_version_id: int,
    month: int,
    aggregates: Sequence[MonthlyAggregateResult],
    reference_period: str = "2010-2025",
    processing_version: str = "12.4c_v1",
    geographic_uncertainty: str = "DISTRICT_REPRESENTATIVE_POINT",
) -> MonthlyClimatologyResult:
    """Compute 16-year historical month-of-year climatology baseline from annual monthly aggregates."""
    month_aggs = [a for a in aggregates if a.month == month and a.district_id == district_id]
    valid_years = len(month_aggs)
    total_obs_days = sum(a.observed_days for a in month_aggs)

    # Rainfall totals per year (1 observation per year)
    rainfall_totals = [
        a.precipitation_total_mm for a in month_aggs if a.precipitation_total_mm is not None
    ]

    if rainfall_totals:
        arr_rf = np.array(rainfall_totals, dtype=float)
        rf_mean = round(float(np.mean(arr_rf)), 2)
        rf_median = round(float(np.median(arr_rf)), 2)
        rf_std = round(float(np.std(arr_rf, ddof=1)), 2) if len(arr_rf) > 1 else 0.0
        p25 = float(np.percentile(arr_rf, 25))
        p75 = float(np.percentile(arr_rf, 75))
        rf_iqr = round(p75 - p25, 2)
        rf_p10 = round(float(np.percentile(arr_rf, 10)), 2)
        rf_p90 = round(float(np.percentile(arr_rf, 90)), 2)
        rf_min = round(float(np.min(arr_rf)), 2)
        rf_max = round(float(np.max(arr_rf)), 2)
        rf_cv = round(rf_std / rf_mean, 4) if rf_mean > 0 else 0.0
    else:
        rf_mean = rf_median = rf_std = rf_iqr = rf_p10 = rf_p90 = rf_min = rf_max = rf_cv = None

    rainy_freqs = [a.rainy_days_frequency for a in month_aggs]
    rainy_freq_mean = round(sum(rainy_freqs) / len(rainy_freqs), 4) if rainy_freqs else None

    heavy_counts = [a.heavy_rain_days_count for a in month_aggs]
    heavy_mean = round(sum(heavy_counts) / len(heavy_counts), 2) if heavy_counts else None

    very_heavy_counts = [a.very_heavy_rain_days_count for a in month_aggs]
    very_heavy_mean = round(sum(very_heavy_counts) / len(very_heavy_counts), 2) if very_heavy_counts else None

    # Temperature metrics
    t_means = [a.temp_mean_c for a in month_aggs if a.temp_mean_c is not None]
    t_max_means = [a.temp_max_mean_c for a in month_aggs if a.temp_max_mean_c is not None]
    t_min_means = [a.temp_min_mean_c for a in month_aggs if a.temp_min_mean_c is not None]
    diurnal_means = [a.diurnal_range_mean_c for a in month_aggs if a.diurnal_range_mean_c is not None]

    t_mean = round(sum(t_means) / len(t_means), 2) if t_means else None
    t_max_mean = round(sum(t_max_means) / len(t_max_means), 2) if t_max_means else None
    t_min_mean = round(sum(t_min_means) / len(t_min_means), 2) if t_min_means else None
    diurnal_mean = round(sum(diurnal_means) / len(diurnal_means), 2) if diurnal_means else None

    # Humidity, wind, solar
    rh_means = [a.relative_humidity_mean_pct for a in month_aggs if a.relative_humidity_mean_pct is not None]
    rh_mean = round(sum(rh_means) / len(rh_means), 2) if rh_means else None

    ws_means = [a.wind_speed_mean_ms for a in month_aggs if a.wind_speed_mean_ms is not None]
    ws_mean = round(sum(ws_means) / len(ws_means), 2) if ws_means else None

    sol_means = [a.solar_radiation_mean_mj for a in month_aggs if a.solar_radiation_mean_mj is not None]
    sol_mean = round(sum(sol_means) / len(sol_means), 2) if sol_means else None

    sol_totals = [a.solar_radiation_total_mj for a in month_aggs if a.solar_radiation_total_mj is not None]
    sol_total_mean = round(sum(sol_totals) / len(sol_totals), 2) if sol_totals else None

    return MonthlyClimatologyResult(
        district_id=district_id,
        dataset_version_id=dataset_version_id,
        month=month,
        reference_period=reference_period,
        processing_version=processing_version,
        rainfall_mean_mm=rf_mean,
        rainfall_median_mm=rf_median,
        rainfall_std_mm=rf_std,
        rainfall_iqr_mm=rf_iqr,
        rainfall_p10_mm=rf_p10,
        rainfall_p90_mm=rf_p90,
        rainfall_min_mm=rf_min,
        rainfall_max_mm=rf_max,
        rainfall_cv=rf_cv,
        rainy_day_frequency_mean=rainy_freq_mean,
        heavy_rain_days_mean=heavy_mean,
        very_heavy_rain_days_mean=very_heavy_mean,
        temp_mean_c=t_mean,
        temp_max_mean_c=t_max_mean,
        temp_min_mean_c=t_min_mean,
        diurnal_range_mean_c=diurnal_mean,
        relative_humidity_mean_pct=rh_mean,
        wind_speed_mean_ms=ws_mean,
        solar_radiation_mean_mj=sol_mean,
        solar_radiation_total_mean_mj=sol_total_mean,
        valid_years_count=valid_years,
        total_observed_days=total_obs_days,
        geographic_uncertainty=geographic_uncertainty,
    )
