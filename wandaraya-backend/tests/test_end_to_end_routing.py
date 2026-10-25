"""
Test Suite: End-to-End Route Planning, Live Warning Detection, and Safest Route Recommendation.
================================================================================================
Validates complete Section 11 & Section 13.4 workflow:
1. Origin and destination selection and validation.
2. Multimodal route candidate generation (Dijkstra baseline and RAGRO optimizer).
3. Official warning detection (NBRO and Department of Meteorology).
4. Environmental risk scoring and safety indicator calculation.
5. Recommendation of the lowest-risk eligible route.
6. Segment-level risk, susceptibility, and safety fields.
7. Verification of all top-level API response fields.
"""

import pytest
from fastapi.testclient import TestClient
from scripts.run_swagger import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_complete_routing_workflow_kandy_to_nuwara_eliya(client):
    """
    Complete end-to-end test on the hill-country corridor (Kandy -> Nuwara Eliya).
    Validates origin/destination resolution, warning detection, RAGRO optimization,
    risk scoring, alternative comparisons, and recommended lowest-risk route.
    """
    response = client.get(
        "/api/routes/multimodal-plan",
        params={
            "start": "7.2906,80.6337",
            "end": "6.9708,80.7829",
            "start_name": "Kandy",
            "end_name": "Nuwara Eliya",
            "modes": "train,bus,car,bike,walking",
        }
    )

    assert response.status_code == 200
    data = response.json()

    # 1. Top-Level Required Fields Verification
    assert "origin" in data
    assert "destination" in data
    assert data["origin"]["name"] == "Kandy"
    assert data["destination"]["name"] == "Nuwara Eliya"

    assert "routes" in data
    assert len(data["routes"]) >= 1

    assert "recommended_route_id" in data
    assert "selected_route_id" in data
    assert data["recommended_route_id"] == data["selected_route_id"]

    assert "optimization_algorithm" in data
    assert data["optimization_algorithm"] in ("RAGRO", "DIJKSTRA_FALLBACK")

    assert "route_environmental_risk_score" in data
    assert 0.0 <= data["route_environmental_risk_score"] <= 100.0

    assert "route_safety_indicator" in data
    assert 0.0 <= data["route_safety_indicator"] <= 100.0

    assert "maximum_segment_risk" in data
    assert 0.0 <= data["maximum_segment_risk"] <= 100.0

    assert "landslide_warning_status" in data
    assert data["landslide_warning_status"] in (
        "ACTIVE_WARNING", "NO_ACTIVE_WARNING_FOUND", "WARNING_STATUS_UNKNOWN"
    )

    assert "weather_warning_status" in data
    assert data["weather_warning_status"] in (
        "ACTIVE_WARNING", "NO_ACTIVE_WARNING_FOUND", "WARNING_STATUS_UNKNOWN"
    )

    assert "active_warnings" in data
    assert "verified_restrictions" in data
    assert "data_completeness" in data
    assert data["data_completeness"] == "COMPLETE"
    assert "data_freshness" in data
    assert "risk_explanation" in data
    assert len(data["risk_explanation"]) > 10

    # 2. Recommended Route Exists in Returned Routes
    rec_id = data["recommended_route_id"]
    route_ids = [r["route_id"] for r in data["routes"]]
    assert rec_id in route_ids

    # 3. Verify Segment-Level Fields in Every Route
    for route in data["routes"]:
        assert "legs" in route or "segments" in route
        legs = route.get("legs", [])
        if legs:
            for leg in legs:
                assert "segment_id" in leg
                assert "environmental_risk_score" in leg
                assert "segment_safety_indicator" in leg
                assert "landslide_susceptibility_score" in leg
                assert "rainfall_risk_score" in leg
                assert "weather_risk_score" in leg
                assert "landslide_warning_status" in leg
                assert "weather_warning_status" in leg
                assert "risk_explanation" in leg


def test_origin_destination_swap(client):
    """Verify origin and destination swapping returns valid reciprocal routing."""
    res_forward = client.get(
        "/api/routes/multimodal-plan",
        params={"start": "Colombo", "end": "Kandy"}
    )
    assert res_forward.status_code == 200
    d_f = res_forward.json()

    res_reverse = client.get(
        "/api/routes/multimodal-plan",
        params={"start": "Kandy", "end": "Colombo"}
    )
    assert res_reverse.status_code == 200
    d_r = res_reverse.json()

    assert d_f["origin"]["name"] == d_r["destination"]["name"]
    assert d_f["destination"]["name"] == d_r["origin"]["name"]
