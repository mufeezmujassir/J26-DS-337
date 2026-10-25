"""
Test Suite: Environmental Risk Scoring Service Formulas and Route Aggregation.
==============================================================================
Validates:
1. Exact research formulas:
     LandslideRisk = 0.60 * L + 0.40 * R
     EnvironmentalRisk = 0.60 * LandslideRisk + 0.40 * W
     SegmentSafetyIndicator = 100.0 - SegmentEnvironmentalRisk
2. Route-level risk aggregation:
     RouteRisk = sum(segment_risk * segment_travel_time) / sum(segment_travel_time)
     RouteSafetyIndicator = 100.0 - RouteRisk
3. Boundary value handling: (0, 0, 0) and (100, 100, 100).
4. Missing data handling: never silently zero, explicit validation.
5. Hotspot protection: High-risk segment detected and surfaced even when route average is low.
"""

import pytest
from app.services.environmental_risk_service import (
    EnvironmentalRiskService,
    environmental_risk_service,
)


def test_research_formula_exact_expected_values():
    """
    Test exact expected outputs with known hand-calculated values:
    Given: L=50.0, R24=40.0, R72=20.0, R7=10.0, W=30.0
      R = 0.50*40 + 0.30*20 + 0.20*10 = 20 + 6 + 2 = 28.0
      LandslideRisk = 0.60*50 + 0.40*28 = 30 + 11.2 = 41.2
      EnvironmentalRisk = 0.60*41.2 + 0.40*30 = 24.72 + 12 = 36.72
      SafetyIndicator = 100.0 - 36.72 = 63.28
    """
    res = EnvironmentalRiskService.calculate_research_formula(
        landslide_susceptibility=50.0,
        r24=40.0,
        r72=20.0,
        r7=10.0,
        weather_score=30.0,
        w_ls=0.60,
        w_weather=0.40
    )
    assert res["rainfall_score"] == 28.0
    assert res["dynamic_landslide_score"] == 41.2
    assert res["environmental_risk_score"] == 36.72
    assert res["environmental_safety_indicator"] == 63.28


def test_formula_boundary_minimum():
    """Boundary test: All zero inputs -> Risk=0.0, Safety=100.0."""
    res = EnvironmentalRiskService.calculate_research_formula(
        landslide_susceptibility=0.0,
        r24=0.0,
        r72=0.0,
        r7=0.0,
        weather_score=0.0
    )
    assert res["environmental_risk_score"] == 0.0
    assert res["environmental_safety_indicator"] == 100.0


def test_formula_boundary_maximum():
    """Boundary test: All maximum (100.0) inputs -> Risk=100.0, Safety=0.0."""
    res = EnvironmentalRiskService.calculate_research_formula(
        landslide_susceptibility=100.0,
        r24=100.0,
        r72=100.0,
        r7=100.0,
        weather_score=100.0
    )
    assert res["environmental_risk_score"] == 100.0
    assert res["environmental_safety_indicator"] == 0.0


def test_invalid_and_negative_inputs_rejected():
    """Strict validation: Rejects negative, non-numeric, or infinite values."""
    with pytest.raises(ValueError):
        EnvironmentalRiskService.calculate_research_formula(
            landslide_susceptibility=-10.0, r24=50.0
        )
    with pytest.raises(ValueError):
        EnvironmentalRiskService.calculate_research_formula(
            landslide_susceptibility=50.0, r24=float("nan")
        )
    with pytest.raises(ValueError):
        EnvironmentalRiskService.calculate_research_formula(
            landslide_susceptibility=50.0, r24=float("inf")
        )


def test_route_risk_aggregation_time_weighted():
    """
    Test travel-time weighted route risk:
    Segment 1: risk=20.0, time=30.0 min
    Segment 2: risk=60.0, time=10.0 min
    Weighted avg = (20*30 + 60*10) / (30 + 10) = (600 + 600) / 40 = 30.0
    Safety = 70.0
    """
    segments = [
        {"segment_id": "seg_1", "segment_risk": 20.0, "travel_time_min": 30.0, "distance_km": 20.0},
        {"segment_id": "seg_2", "segment_risk": 60.0, "travel_time_min": 10.0, "distance_km": 5.0},
    ]
    res = EnvironmentalRiskService.calculate_route_risk_aggregation(segments, weighting="time")
    assert res["route_average_risk"] == 30.0
    assert res["environmental_safety_indicator"] == 70.0
    assert res["max_segment_risk"] == 60.0
    assert "seg_2" in res["high_risk_segment_identifiers"]


def test_hazard_hotspot_protection_low_average_does_not_conceal_high_risk():
    """
    Critical Safety Rule: A route with 9 low-risk segments and 1 lethal hazard segment
    must detect and expose the maximum segment risk.
    """
    segments = [
        {"segment_id": f"safe_seg_{i}", "segment_risk": 10.0, "travel_time_min": 10.0, "distance_km": 10.0}
        for i in range(9)
    ]
    # Add 1 high hazard segment (e.g. active landslide reactivation slope)
    segments.append({
        "segment_id": "lethal_hazard_pass",
        "segment_risk": 95.0,
        "travel_time_min": 10.0,
        "distance_km": 10.0,
    })

    res = EnvironmentalRiskService.calculate_route_risk_aggregation(segments, weighting="time")
    # Average is low: (10*90 + 95*10) / 100 = 18.5
    assert res["route_average_risk"] == 18.5
    # But maximum segment risk MUST be 95.0, and the hotspot ID surfaced!
    assert res["max_segment_risk"] == 95.0
    assert "lethal_hazard_pass" in res["high_risk_segment_identifiers"]
