"""Activity Suitability Scoring Service (Stage 12.4D Task H).

Calculates deterministic, explainable, activity-specific climate favorability scores
and ranks 12 calendar months for an attraction-activity pair.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.climate.activity_taxonomy import ActivityTypeDefinition


@dataclass(frozen=True)
class MonthlySuitabilityScore:
    month: int
    score: float
    rank: int
    evidence_status: str
    confidence_level: str
    uncertainty_score: float
    feature_contributions: dict[str, float]
    positive_factors: list[str]
    negative_factors: list[str]
    limitations: list[str]


def calculate_activity_suitability_for_year(
    activity_def: ActivityTypeDefinition,
    monthly_climate_features: list[dict[str, Any]],
    geographic_source_type: str = "DISTRICT_REPRESENTATIVE_PROXY",
) -> list[MonthlySuitabilityScore]:
    """Calculate activity suitability scores and ranks for all 12 calendar months.

    `monthly_climate_features` must be a list of 12 dicts (one per month) containing:
    - month (1-12)
    - relative_rainfall_favorability [0, 1]
    - temperature_comfort_index [0, 1]
    - humidity_comfort_index [0, 1]
    - rainfall_reliability_index [0, 1]
    - solar_radiation_mean_mj (or pre-normalized solar_radiation_context)
    - seasonality_uncertainty_score [0, 1]
    """
    if len(monthly_climate_features) != 12:
        raise ValueError(f"Expected 12 monthly climate profiles, got {len(monthly_climate_features)}")

    # Pre-normalize solar radiation across the 12 months if not already normalized
    solars = [f.get("solar_radiation_mean_mj", 18.0) for f in monthly_climate_features]
    s_min, s_max = min(solars), max(solars)
    s_span = (s_max - s_min) if (s_max - s_min) > 0.01 else 1.0

    raw_scores = []
    weights = activity_def.feature_weights

    # Ensure weights sum to 1.0
    w_sum = sum(weights.values())
    norm_weights = {k: v / w_sum for k, v in weights.items()}

    for feat in monthly_climate_features:
        m = feat["month"]
        rf_fav = feat.get("relative_rainfall_favorability", 0.5)
        t_comf = feat.get("temperature_comfort_index", 0.5)
        h_comf = feat.get("humidity_comfort_index", 0.5)
        rf_rel = feat.get("rainfall_reliability_index", 0.5)
        unc_score = feat.get("seasonality_uncertainty_score", 0.3)

        sol_raw = feat.get("solar_radiation_mean_mj", 18.0)
        sol_ctx = feat.get("solar_radiation_context", (sol_raw - s_min) / s_span)

        feature_map = {
            "relative_rainfall_favorability": rf_fav,
            "temperature_comfort_index": t_comf,
            "humidity_comfort_index": h_comf,
            "solar_radiation_context": sol_ctx,
            "rainfall_reliability_index": rf_rel,
        }

        # Calculate weighted sum
        score = 0.0
        contributions = {}
        for feat_name, w in norm_weights.items():
            f_val = feature_map.get(feat_name, 0.5)
            contrib = w * f_val
            contributions[feat_name] = round(contrib, 4)
            score += contrib

        score = round(score, 4)

        # Identify positive and negative factors
        positives = []
        negatives = []
        if rf_fav >= 0.70:
            positives.append("Historically comparatively dry period with low rainfall disruption risk.")
        elif rf_fav <= 0.30:
            negatives.append("Historically heavy rainfall or monsoon conditions create high disruption probability.")

        if t_comf >= 0.75:
            positives.append("Thermal conditions fall comfortably within optimal traveler comfort bounds.")
        elif t_comf <= 0.35:
            negatives.append("Thermal conditions exhibit elevated heat stress or highland chill.")

        if h_comf >= 0.70:
            positives.append("Manageable relative humidity reduces outdoor walking fatigue.")
        elif h_comf <= 0.30:
            negatives.append("High tropical humidity elevates perceived discomfort and outdoor perspiration.")

        if sol_ctx >= 0.75:
            positives.append("High solar radiation and clear skies enhance outdoor scenery and visibility.")
        elif sol_ctx <= 0.30:
            negatives.append("Lower solar radiation correlates with frequent overcast conditions.")

        if rf_rel >= 0.70:
            positives.append("High interannual rainfall stability makes historical conditions repeatable.")
        elif rf_rel <= 0.35:
            negatives.append("High year-to-year rainfall variability introduces seasonal volatility.")

        # Limitations
        limitations = [
            f"Climate score is an experimental relative index derived from 0.5° NASA POWER reanalysis, not an in-situ weather forecast.",
        ]
        if geographic_source_type == "DISTRICT_REPRESENTATIVE_PROXY":
            limitations.append("District representative proxy used; local microclimates (elevation, valley gaps) may differ.")

        if activity_def.requires_external_evidence and activity_def.unsupported_abstention_warning:
            limitations.append(activity_def.unsupported_abstention_warning)

        confidence = "HIGH" if (geographic_source_type == "ATTRACTION_COORDINATE_REANALYSIS" and not activity_def.requires_external_evidence) else ("MEDIUM" if not activity_def.requires_external_evidence else "LOW_PARTIAL")

        raw_scores.append({
            "month": m,
            "score": score,
            "evidence_status": activity_def.evidence_status,
            "confidence_level": confidence,
            "uncertainty_score": unc_score,
            "feature_contributions": contributions,
            "positive_factors": positives,
            "negative_factors": negatives,
            "limitations": limitations,
        })

    # Rank the 12 months in descending order of score (highest score = Rank 1)
    sorted_months = sorted(raw_scores, key=lambda x: (-x["score"], x["month"]))
    for rank, item in enumerate(sorted_months, 1):
        item["rank"] = rank

    # Return ordered by month
    results = []
    for item in sorted(raw_scores, key=lambda x: x["month"]):
        results.append(
            MonthlySuitabilityScore(
                month=item["month"],
                score=item["score"],
                rank=item["rank"],
                evidence_status=item["evidence_status"],
                confidence_level=item["confidence_level"],
                uncertainty_score=item["uncertainty_score"],
                feature_contributions=item["feature_contributions"],
                positive_factors=item["positive_factors"],
                negative_factors=item["negative_factors"],
                limitations=item["limitations"],
            )
        )

    return results
