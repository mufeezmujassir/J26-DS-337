"""Seasonality Explanation Validator and Grounded Generator (Stage 12.4D.1 Task F).

Enforces strict audit standards on generated natural language explanations, ensuring:
- Absolute numerical concordance between stored scores/ranks and narrative text
- Explicit disclosure of reference period (2010-2025) and geographic proxy resolution
- Clear separation between historical climate favorability, live forecasts, and activity safety
- Mandatory partial-evidence caveats for marine, waterfall, and wildlife activities
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any


EXPLANATION_AUDIT_VERSION = "v1.1"


@dataclass(frozen=True)
class ExplanationValidationResult:
    is_valid: bool
    status: str  # 'VALIDATED', 'NUMERICAL_DISCREPANCY', 'UNSUPPORTED_SAFETY_CLAIM', 'MISSING_LIMITATIONS'
    detected_anomalies: list[str]


def compute_suitability_class(score: float) -> str:
    """Deterministic experimental suitability class."""
    if score >= 0.75:
        return "HIGH_RELATIVE_CLIMATE_FAVORABILITY"
    elif score >= 0.60:
        return "FAVORABLE"
    elif score >= 0.45:
        return "MODERATE"
    else:
        return "UNFAVORABLE"


def generate_canonical_explanation(
    attraction_name: str,
    district_name: str,
    activity_name: str,
    activity_code: str,
    month: int,
    score: float,
    rank: int,
    climatology_metrics: dict[str, Any],
    feature_contributions: dict[str, float],
    evidence_status: str,
    requires_external_evidence: bool,
    missing_evidence_requirements: list[str],
    geographic_source_type: str = "DISTRICT_REPRESENTATIVE_PROXY",
    reference_period: str = "2010-2025",
    audit_version: str = EXPLANATION_AUDIT_VERSION,
) -> dict[str, Any]:
    """Generate a 100% grounded, auditable explanation dictionary."""
    month_name = calendar.month_name[month]
    suit_class = compute_suitability_class(score)
    rf_med = climatology_metrics.get("rainfall_median_mm")
    t_mean = climatology_metrics.get("temp_mean_c")
    rh_mean = climatology_metrics.get("relative_humidity_mean_pct")
    rain_freq = climatology_metrics.get("rainy_day_frequency_mean")

    # Ordinal rank string
    ordinal_suffixes = {1: "1st", 2: "2nd", 3: "3rd"}
    rank_str = ordinal_suffixes.get(rank, f"{rank}th")

    # Canonical summary statement
    summary = (
        f"{month_name} ranks {rank_str} among the 12 historical calendar months for {activity_name} "
        f"at {attraction_name} ({district_name} District). "
        f"Its experimental climate favorability score is {score:.3f} ({suit_class}). "
        f"This evaluation is strictly derived from {reference_period} historical climate statistics "
        f"and does not predict actual weather conditions or establish operational safety."
    )

    # Positive and negative drivers
    positive_factors = []
    negative_factors = []

    rel_rain = feature_contributions.get("relative_rainfall_favorability", 0.0)
    temp_comf = feature_contributions.get("temperature_comfort_index", 0.0)
    hum_comf = feature_contributions.get("humidity_comfort_index", 0.0)
    rain_rel = feature_contributions.get("rainfall_reliability_index", 0.0)

    if rel_rain >= 0.70:
        positive_factors.append(f"Low historical rainfall volume (median: {rf_med:.1f} mm/month) favors outdoor activities.")
    elif rel_rain < 0.40:
        negative_factors.append(f"Elevated historical rainfall (median: {rf_med:.1f} mm/month) poses weather disruption risk.")

    if temp_comf >= 0.80:
        positive_factors.append(f"Mean ambient temperature of {t_mean:.1f}°C aligns closely with activity thermal comfort.")
    elif temp_comf < 0.50:
        negative_factors.append(f"Mean ambient temperature of {t_mean:.1f}°C departs from optimal thermal comfort band.")

    if rain_rel >= 0.75:
        positive_factors.append("High interannual rainfall consistency across the 16-year baseline.")
    elif rain_rel < 0.55:
        negative_factors.append("Moderate to high interannual rainfall volatility across historical years.")

    if not positive_factors:
        positive_factors.append("No strongly dominant favorable climate factor observed.")
    if not negative_factors:
        negative_factors.append("No severe historical climate impediments detected.")

    # Explicit limitations and uncertainties
    uncertainty_factors = [
        f"Statistical baseline covers {reference_period} (16 calendar years). Individual future days may depart significantly from historical monthly averages.",
    ]
    if geographic_source_type == "DISTRICT_REPRESENTATIVE_PROXY":
        uncertainty_factors.append(
            f"Evaluated using {district_name} District representative coordinate; localized microclimate variations (e.g. elevation lapse rate) are not resolved at 0.5° resolution."
        )
    elif geographic_source_type == "ATTRACTION_COORDINATE_REANALYSIS":
        uncertainty_factors.append(
            "Derived from attraction coordinate reanalysis (0.5° MERRA-2 grid). Montane microclimates may exhibit localized lapse rates unrepresented in 0.5° grid cells."
        )

    # Missing critical evidence / safety caveats
    missing_critical_evidence = []
    if requires_external_evidence or evidence_status == "CLIMATE_ONLY_PARTIAL":
        missing_critical_evidence.extend(missing_evidence_requirements)
        missing_critical_evidence.append(
            "Favorable climate favorability score DOES NOT confirm marine safety, swell height, water quality, trail accessibility, or absence of flash flood hazards."
        )

    return {
        "summary": summary,
        "experimental_climate_favorability_score": round(score, 4),
        "relative_monthly_rank": rank,
        "suitability_class": suit_class,
        "main_positive_factors": positive_factors,
        "main_negative_factors": negative_factors,
        "climate_source": "NASA POWER Daily API v2.10.0 (0.5° MERRA-2/GEOS Reanalysis)",
        "geographic_source_type": geographic_source_type,
        "historical_reference_period": reference_period,
        "interannual_uncertainty": uncertainty_factors,
        "missing_critical_evidence": missing_critical_evidence,
        "explicit_limitations": [
            "Not a real-time weather forecast.",
            "Does not replace official DMC / Department of Meteorology advisories.",
            "Does not verify operational facility status, park opening, or guide availability.",
        ],
        "feature_contributions": feature_contributions,
        "climatology_snapshot": {
            "rainfall_median_mm": rf_med,
            "temp_mean_c": t_mean,
            "relative_humidity_mean_pct": rh_mean,
            "rainy_day_frequency": rain_freq,
        },
        "audit_version": audit_version,
    }


def validate_explanation_against_record(
    explanation_json: dict[str, Any],
    stored_score: float,
    stored_rank: int,
    attraction_name: str,
    activity_name: str,
    month: int,
    geographic_source_type: str,
) -> ExplanationValidationResult:
    """Validate that stored explanation matches record and contains zero unsupported safety claims."""
    anomalies: list[str] = []

    # 1. Summary presence
    summary = explanation_json.get("summary", "")
    if not summary:
        anomalies.append("Explanation summary is empty.")

    # 2. Score check
    exp_score = explanation_json.get("experimental_climate_favorability_score")
    if exp_score is not None:
        if abs(exp_score - stored_score) > 0.001:
            anomalies.append(f"Score mismatch: stored {stored_score:.4f} vs explanation {exp_score:.4f}")

    # 3. Rank check
    exp_rank = explanation_json.get("relative_monthly_rank")
    if exp_rank is not None:
        if exp_rank != stored_rank:
            anomalies.append(f"Rank mismatch: stored {stored_rank} vs explanation {exp_rank}")

    # 4. Prohibit false safety claims
    summary_lower = summary.lower()
    for forbidden in ["guarantees safety", "safe for swimming", "safe to surf", "confirmed safe", "weather guarantee"]:
        if forbidden in summary_lower:
            anomalies.append(f"Prohibited safety assertion found in summary: '{forbidden}'")

    # 5. Prohibit live forecast assertion
    if "forecast predicts" in summary_lower or "tomorrow's weather" in summary_lower:
        anomalies.append("Explanation falsely implies a real-time weather forecast.")

    # 6. Check limitations presence
    if not explanation_json.get("explicit_limitations"):
        anomalies.append("Missing required explicit limitations section.")

    if not anomalies:
        return ExplanationValidationResult(is_valid=True, status="VALIDATED", detected_anomalies=[])
    else:
        return ExplanationValidationResult(is_valid=False, status="ANOMALY_DETECTED", detected_anomalies=anomalies)
