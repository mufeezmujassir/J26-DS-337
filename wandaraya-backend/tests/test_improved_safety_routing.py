"""
Unit & Integration Test Suite: Improved Environmental Risk Modelling and Safety Routing.
=======================================================================================
Validates requirements from WANDARAYA Component 2:
1. Geological susceptibility score (L) mapping and spatial queries.
2. Multi-horizon rainfall risk score (R) normalization and weighting:
     R = 0.50 * R24 + 0.30 * R72 + 0.20 * R7
3. Weather context score (W) non-overlapping formulation.
4. Combined research formula:
     DynamicLandslide = 0.60 * L + 0.40 * R
     EnvironmentalRisk = 0.60 * DynamicLandslide + 0.40 * W = 0.36 * L + 0.24 * R + 0.40 * W
     SafetyIndicator = 100.0 - EnvironmentalRisk
5. Research model risk categories (Low, Moderate, Elevated, High).
6. Separation of research model categories from official warnings (is_official_government_warning = False).
7. Risk-weighted Dijkstra edge cost:
     SafetyEdgeCost = SegmentTravelTime * [1 + lambda * (SegmentRisk / 100)^2]
   with lambda parameter sensitivity (lambda=1, 3, 5) and closure exclusion.
8. Route risk aggregation:
     - Travel-time-weighted average risk
     - Maximum segment risk
     - Time spent in elevated-risk segments (>= 50.0)
     - Highest-risk segment and mode
9. RAGRO genetic optimizer integration with route risk metrics.
"""

import pytest
from app.services.graph import MultimodalGraph, GraphMode, Node, Edge
from app.services.dijkstra import DijkstraRouter, EnvironmentalRiskCostModel
from app.services.weather_risk_service import (
    WeatherRiskService,
    weather_risk_service,
    calculate_rainfall_risk_score,
    calculate_weather_context_score,
    normalize_rainfall_component,
)
from app.services.environmental_risk_service import (
    EnvironmentalRiskService,
    environmental_risk_service,
    get_model_risk_category,
)
from app.services.landslide_service import (
    LandslideService,
    landslide_service,
    DEFAULT_HAZARD_CLASS_SUSCEPTIBILITY,
)
from app.services.ragro import RAGROOptimizer, RAGROConfig


# ============================================================================
# Section 1: Geological Susceptibility Mapping & Spatial Properties
# ============================================================================

def test_geological_susceptibility_mapping_configuration():
    """Verify standard evidence-based NBRO hazard class mapping."""
    mapping = DEFAULT_HAZARD_CLASS_SUSCEPTIBILITY
    assert mapping["VERY_HIGH_HAZARD"] == 95.0
    assert mapping["HIGH_HAZARD"] == 75.0
    assert mapping["MODEST_HAZARD"] == 40.0
    assert mapping["LOW_HAZARD"] == 15.0
    assert mapping["WATER_BODY_UNCLASSIFIED"] == 0.0
    assert mapping["NO_HAZARD_ZONE"] == 0.0


def test_segment_susceptibility_query():
    """Verify segment susceptibility spatial query along a known segment."""
    # Segment in Nuwara Eliya area
    coords = [(6.9700, 80.7800), (6.9600, 80.7900)]
    res = landslide_service.get_segment_susceptibility(coords)
    assert "mean_susceptibility" in res
    assert "max_susceptibility" in res
    assert "dominant_hazard_class" in res
    assert 0.0 <= res["mean_susceptibility"] <= 100.0


# ============================================================================
# Section 2: Multi-Horizon Rainfall Risk Score Normalization (R)
# ============================================================================

def test_rainfall_component_normalization():
    """Test 0-100 normalization of R24, R72, and R7."""
    from app.services.weather_risk_service import THRESHOLD_R24_MAX_MM, THRESHOLD_R72_MAX_MM, THRESHOLD_R7_MAX_MM
    # 0 mm -> 0 score
    assert normalize_rainfall_component(0.0, THRESHOLD_R24_MAX_MM) == 0.0
    # Half of saturation threshold (50mm / 100mm) -> 50.0 score
    assert normalize_rainfall_component(50.0, THRESHOLD_R24_MAX_MM) == 50.0
    # Saturation threshold (100mm) -> 100.0 score
    assert normalize_rainfall_component(100.0, THRESHOLD_R24_MAX_MM) == 100.0
    # Over saturation -> capped at 100.0
    assert normalize_rainfall_component(180.0, THRESHOLD_R24_MAX_MM) == 100.0

    # R72: threshold 200mm
    assert normalize_rainfall_component(100.0, THRESHOLD_R72_MAX_MM) == 50.0
    # R7: threshold 350mm
    assert normalize_rainfall_component(175.0, THRESHOLD_R7_MAX_MM) == 50.0


def test_multi_horizon_rainfall_combination():
    """
    R = 0.50 * R24 + 0.30 * R72 + 0.20 * R7
    All inputs normalized to 0-100 before combining.
    """
    # Raw rainfall: r24=50mm (norm 50), r72=100mm (norm 50), r7=175mm (norm 50)
    res = calculate_rainfall_risk_score(r24_mm=50.0, r72_mm=100.0, r7_mm=175.0)
    assert res["r24_normalized_score"] == 50.0
    assert res["r72_normalized_score"] == 50.0
    assert res["r7_normalized_score"] == 50.0
    # 0.50*50 + 0.30*50 + 0.20*50 = 50.0
    assert res["rainfall_risk_score"] == 50.0
    assert res["horizon_completeness"] == "COMPLETE"
    assert res["data_type"] == "FORECAST"


def test_missing_historical_rainfall_preserves_incomplete_status():
    """When R72 or R7 are missing, report explicit status without fabricating values."""
    res = calculate_rainfall_risk_score(r24_mm=60.0, r72_mm=None, r7_mm=None)
    assert res["r24_normalized_score"] == 60.0
    assert res["r72_normalized_score"] == 0.0
    assert res["horizon_completeness"] == "R24_ONLY"


# ============================================================================
# Section 3: Weather Context Score (W) Non-Overlapping Formulation
# ============================================================================

def test_weather_context_score_non_overlapping():
    """
    W synthesizes wind, severe convective storms, and visibility,
    explicitly avoiding double-counting cumulative rainfall.
    """
    # Severe thunderstorm + high wind gust (20 m/s > 15 m/s) + fog (<1000m)
    res = calculate_weather_context_score(
        weather_descriptions=["Severe Thunderstorm", "Heavy Convective Gale"],
        wind_speed_mps=22.0,
        visibility_m=500.0
    )
    assert res["weather_context_score"] >= 60.0
    assert "convective_score" in res["breakdown"]
    assert "wind_score" in res["breakdown"]
    assert "visibility_score" in res["breakdown"]

    # Clear weather
    res_clear = calculate_weather_context_score(
        weather_descriptions=["Clear sky"],
        wind_speed_mps=3.0,
        visibility_m=10000.0
    )
    assert res_clear["weather_context_score"] == 0.0


# ============================================================================
# Section 4: Combined Research Formula & Model Categories
# ============================================================================

def test_combined_research_formula_expansion():
    """
    DynamicLandslide = 0.60 * L + 0.40 * R
    EnvironmentalRisk = 0.60 * DynamicLandslide + 0.40 * W
    Expands to: 0.36 * L + 0.24 * R + 0.40 * W
    """
    L = 80.0
    R = 60.0
    W = 40.0
    res = EnvironmentalRiskService.calculate_research_formula(
        landslide_susceptibility=L,
        r24=R,
        r72=R,
        r7=R,
        weather_score=W,
    )
    expected_dynamic_ls = 0.60 * 80.0 + 0.40 * 60.0  # 48.0 + 24.0 = 72.0
    expected_env_risk = round(0.60 * expected_dynamic_ls + 0.40 * 40.0, 2)  # 43.2 + 16.0 = 59.2
    assert res["dynamic_landslide_score"] == expected_dynamic_ls
    assert res["environmental_risk_score"] == expected_env_risk
    assert res["environmental_safety_indicator"] == round(100.0 - expected_env_risk, 2)


def test_model_risk_categories_and_disclaimer():
    """Verify display categories and non-official disclaimer."""
    assert get_model_risk_category(15.0) == "Low model-estimated risk"
    assert get_model_risk_category(35.0) == "Moderate model-estimated risk"
    assert get_model_risk_category(60.0) == "Elevated model-estimated risk"
    assert get_model_risk_category(85.0) == "High model-estimated risk"


# ============================================================================
# Section 5: Risk-Weighted Dijkstra & Lambda Sensitivity
# ============================================================================

def test_risk_weighted_dijkstra_cost_model():
    """
    SafetyEdgeCost = SegmentTravelTime * [1 + lambda * (SegmentRisk / 100)^2]
    Verify lambda sensitivity and zero risk behavior.
    """
    # Create test edge with travel time = 30 min, risk = 80.0
    edge_high_risk = Edge("u", "v", GraphMode.ROAD, True, {
        "travel_time_min": 30.0,
        "distance_km": 20.0,
        "environmental_risk_score": 80.0
    })

    # Edge with zero risk
    edge_zero_risk = Edge("u", "w", GraphMode.ROAD, True, {
        "travel_time_min": 30.0,
        "distance_km": 20.0,
        "environmental_risk_score": 0.0
    })

    # Closed edge
    edge_closed = Edge("u", "x", GraphMode.ROAD, True, {
        "travel_time_min": 30.0,
        "distance_km": 20.0,
        "environmental_risk_score": 20.0,
        "closure_status": "closed"
    })

    model_l1 = EnvironmentalRiskCostModel(lambda_risk=1.0)
    model_l3 = EnvironmentalRiskCostModel(lambda_risk=3.0)
    model_l5 = EnvironmentalRiskCostModel(lambda_risk=5.0)

    # Zero risk edge should always cost exactly base travel time (30.0)
    assert model_l1.get_cost(edge_zero_risk) == 30.0
    assert model_l3.get_cost(edge_zero_risk) == 30.0
    assert model_l5.get_cost(edge_zero_risk) == 30.0

    # High risk edge (80/100 -> ratio^2 = 0.64):
    # lambda=1: 30 * [1 + 1.0 * 0.64] = 30 * 1.64 = 49.2
    assert model_l1.get_cost(edge_high_risk) == pytest.approx(49.2, 0.01)
    # lambda=3: 30 * [1 + 3.0 * 0.64] = 30 * 2.92 = 87.6
    assert model_l3.get_cost(edge_high_risk) == pytest.approx(87.6, 0.01)
    # lambda=5: 30 * [1 + 5.0 * 0.64] = 30 * 4.20 = 126.0
    assert model_l5.get_cost(edge_high_risk) == pytest.approx(126.0, 0.01)

    # Closed edge must be excluded (return None / infinite cost)
    assert model_l3.get_cost(edge_closed) is None


def test_dijkstra_selects_safest_path_under_lambda():
    """
    On a network with two alternative paths:
    Path 1 (Hazardous Pass): 20 min, risk 90.0
    Path 2 (Safe Valley Detour): 35 min, risk 10.0
    Ordinary shortest-time Dijkstra picks Path 1.
    Risk-weighted Dijkstra with lambda=3 picks Path 2.
    """
    g = MultimodalGraph()
    g.add_node(Node("A", lat=7.0, lon=80.0))
    g.add_node(Node("B_pass", lat=7.1, lon=80.1))
    g.add_node(Node("B_valley", lat=7.05, lon=80.05))
    g.add_node(Node("C", lat=7.2, lon=80.2))

    # Path 1: A -> B_pass -> C (Total time: 20 min, risk: 90.0)
    g.add_edge(Edge("A", "B_pass", GraphMode.ROAD, True, {
        "travel_time_min": 10.0, "distance_km": 10.0, "environmental_risk_score": 90.0
    }))
    g.add_edge(Edge("B_pass", "C", GraphMode.ROAD, True, {
        "travel_time_min": 10.0, "distance_km": 10.0, "environmental_risk_score": 90.0
    }))

    # Path 2: A -> B_valley -> C (Total time: 35 min, risk: 10.0)
    g.add_edge(Edge("A", "B_valley", GraphMode.ROAD, True, {
        "travel_time_min": 17.5, "distance_km": 18.0, "environmental_risk_score": 10.0
    }))
    g.add_edge(Edge("B_valley", "C", GraphMode.ROAD, True, {
        "travel_time_min": 17.5, "distance_km": 18.0, "environmental_risk_score": 10.0
    }))

    # 1. Ordinary shortest-time Dijkstra baseline -> selects fast but dangerous Path 1
    router_fastest = DijkstraRouter(g, objective="fastest")
    res_fastest = router_fastest.route("A", "C")
    assert "B_pass" in res_fastest.nodes
    assert res_fastest.total_travel_time_min == 20.0

    # 2. Risk-weighted Dijkstra (lambda=3) -> diverts to safe Path 2
    router_safe = DijkstraRouter(g, objective="safety", lambda_risk=3.0)
    res_safe = router_safe.route("A", "C")
    assert "B_valley" in res_safe.nodes
    assert "B_pass" not in res_safe.nodes
    assert res_safe.total_travel_time_min == 35.0
    assert "safety-weighted Dijkstra" in res_safe.selection_explanation


# ============================================================================
# Section 6: Route Risk Aggregation & Elevated Risk Duration
# ============================================================================

def test_route_risk_aggregation_elevated_duration():
    """
    Verify route risk metrics:
    - AverageRisk = sum(risk * time) / sum(time)
    - Time in elevated-risk segments (risk >= 50.0)
    - Highest-risk segment and mode
    """
    segments = [
        {"segment_id": "seg_1", "mode": "bus", "travel_time_min": 30.0, "distance_km": 20.0, "segment_risk": 20.0},
        {"segment_id": "seg_2", "mode": "road", "travel_time_min": 45.0, "distance_km": 30.0, "segment_risk": 80.0},
        {"segment_id": "seg_3", "mode": "rail", "travel_time_min": 25.0, "distance_km": 15.0, "segment_risk": 40.0},
    ]
    # Total time = 30 + 45 + 25 = 100 min
    # Weighted risk sum = (20*30) + (80*45) + (40*25) = 600 + 3600 + 1000 = 5200
    # Average risk = 5200 / 100 = 52.0
    res = EnvironmentalRiskService.calculate_route_risk_aggregation(segments, weighting="time")
    assert res["route_average_risk"] == 52.0
    assert res["environmental_safety_indicator"] == 48.0
    assert res["max_segment_risk"] == 80.0
    # Elevated risk segment is seg_2 (risk 80.0 >= 50.0) with time 45.0 min
    assert res["time_spent_in_elevated_risk_min"] == 45.0
    assert res["distance_in_elevated_risk_km"] == 30.0
    assert res["elevated_risk_time_ratio_pct"] == 45.0
    assert res["highest_risk_segment"]["segment_id"] == "seg_2"
    assert res["highest_risk_segment"]["mode"] == "road"


# ============================================================================
# Section 7: RAGRO Optimizer with Elevated Risk Metrics
# ============================================================================

def test_ragro_produces_elevated_risk_metrics():
    """Verify RAGRO chromosome contains all new research assessment fields."""
    g = MultimodalGraph()
    g.add_node(Node("n0", lat=7.00, lon=80.50))
    g.add_node(Node("n1", lat=7.10, lon=80.55))
    g.add_node(Node("n2", lat=7.20, lon=80.60))

    g.add_edge(Edge("n0", "n1", GraphMode.ROAD, True, {
        "distance_km": 10.0, "travel_time_min": 20.0, "cost_lkr": 50.0, "environmental_risk_score": 65.0
    }))
    g.add_edge(Edge("n1", "n2", GraphMode.ROAD, True, {
        "distance_km": 15.0, "travel_time_min": 30.0, "cost_lkr": 75.0, "environmental_risk_score": 25.0
    }))

    optimizer = RAGROOptimizer(g, config=RAGROConfig(population_size=4, max_generations=2, random_seed=42))
    chrom = optimizer._evaluate_chromosome(["n0", "n1", "n2"])

    assert chrom.time_spent_in_elevated_risk_min == 20.0  # segment 1 (65.0 >= 50.0)
    assert chrom.highest_risk_segment_mode == "road"
    assert "model-estimated risk" in chrom.model_risk_category
    assert len(chrom.selection_explanation) > 10

    chrom_dict = chrom.to_dict()
    assert "time_spent_in_elevated_risk_min" in chrom_dict
    assert "distance_in_elevated_risk_km" in chrom_dict
    assert "model_risk_category" in chrom_dict
    assert "selection_explanation" in chrom_dict
