"""Pytest test suite for Stage 12.4C Monthly Climate Knowledge Base and Seasonality Baselines."""
from __future__ import annotations

import pytest
from app.climate.services.monthly_aggregation import DailyObservationRecord, compute_monthly_aggregate
from app.climate.services.climatology import MonthlyClimatologyResult, compute_monthly_climatology
from app.climate.services.seasonality_features import compute_district_seasonality_features
from datetime import date


def test_compute_monthly_aggregate_calculation():
    records = [
        DailyObservationRecord(
            observation_date=date(2020, 1, 1),
            precipitation_mm=5.0,
            temperature_mean_c=26.0,
            temperature_min_c=22.0,
            temperature_max_c=30.0,
            relative_humidity_pct=75.0,
            wind_speed=2.5,
            solar_radiation=18.0,
        ),
        DailyObservationRecord(
            observation_date=date(2020, 1, 2),
            precipitation_mm=15.0,
            temperature_mean_c=27.0,
            temperature_min_c=23.0,
            temperature_max_c=31.0,
            relative_humidity_pct=80.0,
            wind_speed=3.0,
            solar_radiation=16.0,
        ),
    ]
    res = compute_monthly_aggregate(
        district_id=78,
        dataset_version_id=3,
        year=2020,
        month=1,
        observations=records,
    )
    assert res.precipitation_total_mm == 20.0
    assert res.precipitation_daily_mean_mm == 10.0
    assert res.temp_mean_c == 26.5
    assert res.temp_min_observed_c == 22.0
    assert res.temp_max_observed_c == 31.0
    assert res.diurnal_range_mean_c == 8.0
    assert res.rainy_days_count == 2
    assert res.heavy_rain_days_count == 1
    assert res.very_heavy_rain_days_count == 0
    assert res.solar_radiation_total_mj == 34.0


def test_compute_climatology_percentiles():
    aggs = []
    for yr in range(2010, 2026):
        rf = 50.0 + (yr - 2010) * 10.0  # 50, 60, ... 200
        aggs.append(
            compute_monthly_aggregate(
                district_id=78,
                dataset_version_id=3,
                year=yr,
                month=1,
                observations=[
                    DailyObservationRecord(
                        observation_date=date(yr, 1, 1),
                        precipitation_mm=rf,
                        temperature_mean_c=26.0,
                        temperature_min_c=22.0,
                        temperature_max_c=30.0,
                        relative_humidity_pct=75.0,
                        wind_speed=2.5,
                        solar_radiation=18.0,
                    )
                ],
            )
        )
    clim = compute_monthly_climatology(district_id=78, dataset_version_id=3, month=1, aggregates=aggs)
    assert clim.valid_years_count == 16
    assert clim.rainfall_min_mm == 50.0
    assert clim.rainfall_max_mm == 200.0
    assert clim.rainfall_min_mm <= clim.rainfall_p10_mm <= clim.rainfall_median_mm <= clim.rainfall_p90_mm <= clim.rainfall_max_mm
    assert clim.rainfall_iqr_mm > 0.0
    assert clim.rainfall_cv > 0.0


def test_seasonality_features_permutations():
    profiles = []
    for m in range(1, 13):
        profiles.append(
            MonthlyClimatologyResult(
                district_id=78,
                dataset_version_id=3,
                month=m,
                reference_period="2010-2025",
                processing_version="12.4c_v1",
                rainfall_mean_mm=100.0 + m * 15.0,
                rainfall_median_mm=95.0 + m * 15.0,
                rainfall_std_mm=20.0,
                rainfall_iqr_mm=25.0,
                rainfall_p10_mm=70.0 + m * 15.0,
                rainfall_p90_mm=130.0 + m * 15.0,
                rainfall_min_mm=50.0,
                rainfall_max_mm=250.0,
                rainfall_cv=0.15,
                rainy_day_frequency_mean=0.3,
                heavy_rain_days_mean=3.0,
                very_heavy_rain_days_mean=1.0,
                temp_mean_c=26.0,
                temp_max_mean_c=30.0,
                temp_min_mean_c=22.0,
                diurnal_range_mean_c=8.0,
                relative_humidity_mean_pct=75.0,
                wind_speed_mean_ms=2.5,
                solar_radiation_mean_mj=18.0,
                solar_radiation_total_mean_mj=540.0,
                valid_years_count=16,
                total_observed_days=480,
                geographic_uncertainty="DISTRICT_REPRESENTATIVE_POINT",
            )
        )
    feats = compute_district_seasonality_features(profiles)
    assert len(feats) == 12
    ranks_a = sorted([f.baseline_a_rainfall_rank for f in feats])
    ranks_b = sorted([f.baseline_b_multivar_rank for f in feats])
    ranks_c = sorted([f.baseline_c_variability_rank for f in feats])
    expected = list(range(1, 13))
    assert ranks_a == expected
    assert ranks_b == expected
    assert ranks_c == expected
    # Month 1 had lowest rainfall -> rank 1 in Baseline A
    assert feats[0].baseline_a_rainfall_rank == 1
