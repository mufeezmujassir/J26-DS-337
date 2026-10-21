"""Explainability Engine for Seasonality Features (Stage 12.4D Task M).

Generates evidence-backed, transparent natural language explanations
traceable to underlying climate statistics, activity weights, and limitations.
"""
from __future__ import annotations

import calendar
from typing import Any


def generate_seasonality_explanation(
    attraction_name: str,
    district_name: str,
    activity_name: str,
    month: int,
    score: float,
    rank: int,
    climatology_data: dict[str, Any],
    feature_contributions: dict[str, float],
    evidence_status: str,
    positive_factors: list[str],
    negative_factors: list[str],
    limitations: list[str],
    geographic_source_type: str = "DISTRICT_REPRESENTATIVE_PROXY",
    reference_period: str = "2010-2025",
    activity_profile_version: str = "12.4d_v1",
) -> dict[str, Any]:
    """Generate structured, transparent explanation for a specific attraction-activity-month evaluation."""
    month_name = calendar.month_name[month]
    rf_med = climatology_data.get("rainfall_median_mm")
    t_mean = climatology_data.get("temp_mean_c")
    rh_mean = climatology_data.get("relative_humidity_mean_pct")
    rain_freq = climatology_data.get("rainy_day_frequency_mean")

    # Build summary statement
    if rank <= 3:
        favorability_tier = "one of the historically most favorable months"
    elif rank <= 8:
        favorability_tier = "a moderate intermediate seasonal month"
    else:
        favorability_tier = "one of the historically least favorable months"

    summary = (
        f"{month_name} ranks #{rank} of 12 ({favorability_tier}, score: {score:.3f}) for {activity_name} at "
        f"{attraction_name} ({district_name} District). "
        f"Historically, {month_name} exhibits median precipitation of {rf_med if rf_med is not None else 'N/A'} mm, "
        f"mean temperature of {t_mean if t_mean is not None else 'N/A'}°C, and relative humidity of "
        f"{rh_mean if rh_mean is not None else 'N/A'}%."
    )

    uncertainty_factors = [
        f"Based on {reference_period} historical monthly climatology (16 years). Interannual variation can cause specific dates to depart from monthly averages.",
    ]
    if geographic_source_type == "DISTRICT_REPRESENTATIVE_PROXY":
        uncertainty_factors.append(
            f"Evaluated using {district_name} district representative coordinate reanalysis; localized microclimate effects are not captured."
        )

    unsupported_factors = []
    if evidence_status == "CLIMATE_ONLY_PARTIAL":
        unsupported_factors.extend([
            lim for lim in limitations if "requires" in lim.lower() or "safety" in lim.lower() or "marine" in lim.lower()
        ])

    return {
        "summary": summary,
        "positive_factors": positive_factors if positive_factors else ["No strongly dominant favorable factors."],
        "negative_factors": negative_factors if negative_factors else ["No severe historical climate disruptions."],
        "uncertainty_factors": uncertainty_factors,
        "unsupported_factors": unsupported_factors,
        "data_source": "NASA POWER Daily API v2.10.0 (0.5° MERRA-2/GEOS Reanalysis)",
        "geographic_source_type": geographic_source_type,
        "reference_period": reference_period,
        "activity_profile_version": activity_profile_version,
        "climate_metrics": {
            "month": month,
            "month_name": month_name,
            "rainfall_median_mm": rf_med,
            "temp_mean_c": t_mean,
            "relative_humidity_mean_pct": rh_mean,
            "rainy_day_frequency": rain_freq,
        },
        "feature_contributions": feature_contributions,
    }
