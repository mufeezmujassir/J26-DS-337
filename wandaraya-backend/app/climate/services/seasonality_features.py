"""Explainable Seasonality Features and Baselines Service (Stage 12.4C).

Computes interpretable seasonality features, baseline comparisons (A, B, C),
and statistical robustness profiles for recommendation context layers.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from app.climate.services.climatology import MonthlyClimatologyResult


@dataclass(frozen=True)
class SeasonalityFeatureResult:
    district_id: int
    dataset_version_id: int
    month: int
    feature_version: str
    relative_rainfall_favorability: float
    temperature_comfort_index: float
    humidity_comfort_index: float
    rainfall_reliability_index: float
    seasonality_uncertainty_score: float
    baseline_a_rainfall_rank: int
    baseline_b_multivar_score: float
    baseline_b_multivar_rank: int
    baseline_c_variability_rank: int
    feature_vector_json: dict
    metadata_json: dict


def compute_district_seasonality_features(
    climatology_profiles: Sequence[MonthlyClimatologyResult],
    feature_version: str = "12.4c_v1",
) -> list[SeasonalityFeatureResult]:
    """Compute explainable seasonality features and baselines across all 12 calendar months for a district.

    Expects exactly 12 MonthlyClimatologyResult items for a single district.
    """
    if len(climatology_profiles) != 12:
        raise ValueError(f"Expected exactly 12 monthly climatology profiles, got {len(climatology_profiles)}")

    sorted_profiles = sorted(climatology_profiles, key=lambda p: p.month)
    district_id = sorted_profiles[0].district_id
    dataset_version_id = sorted_profiles[0].dataset_version_id

    # 1. Rainfall ranges within district
    rainfalls = [p.rainfall_median_mm if p.rainfall_median_mm is not None else 0.0 for p in sorted_profiles]
    r_min = min(rainfalls)
    r_max = max(rainfalls)
    r_span = (r_max - r_min) if (r_max - r_min) > 0.001 else 1.0

    # Solar radiation normalization across 12 months
    solars = [p.solar_radiation_mean_mj if p.solar_radiation_mean_mj is not None else 15.0 for p in sorted_profiles]
    s_min = min(solars)
    s_max = max(solars)
    s_span = (s_max - s_min) if (s_max - s_min) > 0.001 else 1.0

    raw_features = []
    for p in sorted_profiles:
        m = p.month
        rf = p.rainfall_median_mm if p.rainfall_median_mm is not None else 0.0
        rf_mean = p.rainfall_mean_mm if p.rainfall_mean_mm is not None else 0.0
        rf_std = p.rainfall_std_mm if p.rainfall_std_mm is not None else 0.0
        rf_cv = p.rainfall_cv if p.rainfall_cv is not None else 0.0
        rf_iqr = p.rainfall_iqr_mm if p.rainfall_iqr_mm is not None else 0.0
        temp = p.temp_mean_c if p.temp_mean_c is not None else 26.0
        rh = p.relative_humidity_mean_pct if p.relative_humidity_mean_pct is not None else 75.0
        sol = p.solar_radiation_mean_mj if p.solar_radiation_mean_mj is not None else 18.0

        # Relative rainfall favorability (1.0 = driest month in district, 0.0 = wettest)
        rf_fav = round(1.0 - ((rf - r_min) / r_span), 4)

        # Temperature comfort index (Gaussian centered at 25°C, sigma = 5°C)
        t_diff = temp - 25.0
        t_comfort = round(float(math.exp(-(t_diff * t_diff) / (2.0 * 25.0))), 4)

        # Humidity comfort index (optimal <= 65%, degrading above 65%)
        h_comfort = round(max(0.0, min(1.0, 1.0 - max(0.0, rh - 65.0) / 30.0)), 4)

        # Rainfall reliability index (1 - bounded CV)
        rf_rel = round(max(0.0, min(1.0, 1.0 - min(1.0, rf_cv))), 4)

        # Seasonality uncertainty score (variability + sampling proxy)
        iqr_ratio = (rf_iqr / rf_mean) if rf_mean > 0.1 else 0.0
        uncertainty = round(min(1.0, 0.4 * min(1.0, rf_cv) + 0.3 * min(1.0, iqr_ratio) + 0.06), 4)

        # Solar norm
        sol_norm = (sol - s_min) / s_span

        # Baseline B composite multi-variable score
        b_score = round(0.45 * rf_fav + 0.25 * t_comfort + 0.15 * h_comfort + 0.15 * sol_norm, 4)

        # Baseline C risk metric (mean + 0.5 * std)
        c_risk = round(rf_mean + 0.5 * rf_std, 2)

        raw_features.append({
            "month": m,
            "profile": p,
            "rf_fav": rf_fav,
            "t_comfort": t_comfort,
            "h_comfort": h_comfort,
            "rf_rel": rf_rel,
            "uncertainty": uncertainty,
            "b_score": b_score,
            "c_risk": c_risk,
            "rf_val": rf,
        })

    # Ranking computation:
    # Baseline A: ascending rainfall (lowest rainfall = rank 1)
    sorted_a = sorted(raw_features, key=lambda x: (x["rf_val"], x["month"]))
    for rank, item in enumerate(sorted_a, 1):
        item["rank_a"] = rank

    # Baseline B: descending multi-variable score (highest score = rank 1)
    sorted_b = sorted(raw_features, key=lambda x: (-x["b_score"], x["month"]))
    for rank, item in enumerate(sorted_b, 1):
        item["rank_b"] = rank

    # Baseline C: ascending variability risk (lowest risk = rank 1)
    sorted_c = sorted(raw_features, key=lambda x: (x["c_risk"], x["month"]))
    for rank, item in enumerate(sorted_c, 1):
        item["rank_c"] = rank

    # Build final results
    results = []
    for item in sorted(raw_features, key=lambda x: x["month"]):
        p: MonthlyClimatologyResult = item["profile"]
        feature_vector = {
            "month": item["month"],
            "relative_rainfall_favorability": item["rf_fav"],
            "temperature_comfort_index": item["t_comfort"],
            "humidity_comfort_index": item["h_comfort"],
            "rainfall_reliability_index": item["rf_rel"],
            "seasonality_uncertainty_score": item["uncertainty"],
            "baseline_a_rainfall_rank": item["rank_a"],
            "baseline_b_multivar_score": item["b_score"],
            "baseline_b_multivar_rank": item["rank_b"],
            "baseline_c_variability_rank": item["rank_c"],
            "rainfall_median_mm": p.rainfall_median_mm,
            "rainfall_mean_mm": p.rainfall_mean_mm,
            "rainfall_cv": p.rainfall_cv,
            "temp_mean_c": p.temp_mean_c,
            "relative_humidity_mean_pct": p.relative_humidity_mean_pct,
            "solar_radiation_mean_mj": p.solar_radiation_mean_mj,
        }
        metadata = {
            "feature_version": feature_version,
            "methodology": {
                "rainfall_favorability": "Min-Max inverted normalization across district 12 calendar months",
                "temperature_comfort": "Gaussian bell centered at 25.0C with sigma=5.0C",
                "humidity_comfort": "Linear penalty above 65% RH normalized over 30% span",
                "rainfall_reliability": "1.0 minus clamped interannual rainfall coefficient of variation",
                "seasonality_uncertainty": "Weighted combination of interannual CV (0.4), relative IQR (0.3), and 0.2 geographic baseline representation limitation",
            },
            "baselines": {
                "baseline_a": "Rainfall-only ranking (ascending median monthly rainfall)",
                "baseline_b": "Multi-variable composite: 0.45*rf_fav + 0.25*t_comfort + 0.15*h_comfort + 0.15*solar_norm",
                "baseline_c": "Variability-aware rainfall ranking: rf_mean + 0.5*rf_std",
            },
            "limitations": [
                "Experimental proxy features; human comfort differs significantly across traveler demographics and outdoor/indoor activities.",
                "Based on 0.5x0.5 deg model reanalysis grid centroid, not physical station microclimate.",
            ],
        }

        results.append(
            SeasonalityFeatureResult(
                district_id=district_id,
                dataset_version_id=dataset_version_id,
                month=item["month"],
                feature_version=feature_version,
                relative_rainfall_favorability=item["rf_fav"],
                temperature_comfort_index=item["t_comfort"],
                humidity_comfort_index=item["h_comfort"],
                rainfall_reliability_index=item["rf_rel"],
                seasonality_uncertainty_score=item["uncertainty"],
                baseline_a_rainfall_rank=item["rank_a"],
                baseline_b_multivar_score=item["b_score"],
                baseline_b_multivar_rank=item["rank_b"],
                baseline_c_variability_rank=item["rank_c"],
                feature_vector_json=feature_vector,
                metadata_json=metadata,
            )
        )

    return results
