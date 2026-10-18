from datetime import date
from unittest.mock import MagicMock
import pytest

from app.services.environmental_risk_service import (
    EnvironmentalRiskService,
    DMCFutureAdapter,
)


def test_dmc_adapter_not_integrated_and_documented():
    """Section 8: DMC data is not currently integrated. Must return NOT_INTEGRATED and document prerequisites."""
    adapter = DMCFutureAdapter()
    status_info = adapter.get_status()

    assert status_info["status"] == "NOT_INTEGRATED"
    assert status_info["connected"] is False
    assert len(status_info["blocked_prerequisites"]) > 0
    assert "warning_id" in status_info["schema_contract"]["expected_fields"]

    # Verify no fake warnings returned
    warnings = adapter.fetch_active_warnings([(6.92, 79.86), (7.29, 80.63)])
    assert warnings == []


def test_status_risk_detected():
    """Requirement 8: A route with a detected environmental hazard returns the correct status."""
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "RISK_DETECTED",
        "hazard_count": 2,
        "closest_hazard_distance_m": 120.0,
        "hazards": [{"record": {"district": "Kandy"}}],
        "note": "Proximity to historical landslide zone.",
    }

    mock_w = MagicMock()
    mock_w.assess_route_weather.return_value = {
        "status": "NO_RISK_DETECTED",
        "available": True,
        "overall_risk_level": "NONE",
        "max_precipitation_forecast_mm": 5.0,
        "weather_points": [],
        "summary": "Normal conditions.",
    }

    service = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w)
    res = service.assess_route([(7.25, 80.52), (7.29, 80.63)], route_id="test_route_01")

    assert res.status == "RISK_DETECTED"
    assert len(res.detected_risks) == 1
    assert "LANDSLIDE_HAZARD_ZONE" in res.detected_risks[0]


def test_status_no_risk_detected_and_no_guaranteed_safety():
    """Requirement 10: A route with no detected configured risk does not receive an unsupported claim that it is guaranteed safe."""
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "NO_RISK_DETECTED",
        "hazard_count": 0,
        "closest_hazard_distance_m": None,
        "hazards": [],
        "note": "No recorded hazards.",
    }

    mock_w = MagicMock()
    mock_w.assess_route_weather.return_value = {
        "status": "NO_RISK_DETECTED",
        "available": True,
        "overall_risk_level": "NONE",
        "max_precipitation_forecast_mm": 2.0,
        "weather_points": [],
        "summary": "Clear.",
    }

    service = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w)
    res = service.assess_route([(6.92, 79.86), (6.93, 79.87)])

    assert res.status == "NO_RISK_DETECTED"
    assert res.detected_risks == []
    # Verify limitations statement does NOT falsely claim guaranteed safety
    evidence_lower = res.evidence_and_limitations.lower()
    assert "does not guarantee absolute safety" in evidence_lower
    assert "dmc" in evidence_lower


def test_status_partial_assessment_when_source_unavailable():
    """Requirement 9: An incomplete data source produces a partial or unavailable assessment."""
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "NO_RISK_DETECTED",
        "hazard_count": 0,
        "closest_hazard_distance_m": None,
        "hazards": [],
        "note": "Clear.",
    }

    mock_w = MagicMock()
    mock_w.assess_route_weather.return_value = {
        "status": "RISK_DATA_UNAVAILABLE",
        "available": False,
        "overall_risk_level": "UNKNOWN",
        "max_precipitation_forecast_mm": 0.0,
        "weather_points": [],
        "summary": "Weather API timed out.",
    }

    service = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w)
    res = service.assess_route([(6.92, 79.86), (6.93, 79.87)])

    # Because weather failed, cannot claim NO_RISK_DETECTED; must be RISK_ASSESSMENT_PARTIAL
    assert res.status == "RISK_ASSESSMENT_PARTIAL"


def test_status_all_sources_unavailable():
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "RISK_DATA_UNAVAILABLE",
        "hazard_count": 0,
        "hazards": [],
    }

    mock_w = MagicMock()
    mock_w.assess_route_weather.return_value = {
        "status": "RISK_DATA_UNAVAILABLE",
        "available": False,
        "overall_risk_level": "UNKNOWN",
        "weather_points": [],
    }

    service = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w)
    res = service.assess_route([(6.92, 79.86), (6.93, 79.87)])

    assert res.status == "RISK_DATA_UNAVAILABLE"


def test_status_data_stale():
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "NO_RISK_DETECTED",
        "hazard_count": 0,
        "hazards": [],
    }

    mock_w = MagicMock()
    mock_w.assess_route_weather.return_value = {
        "status": "DATA_STALE",
        "available": True,
        "overall_risk_level": "NONE",
        "weather_points": [],
    }

    service = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w)
    res = service.assess_route([(6.92, 79.86), (6.93, 79.87)])

    assert res.status == "DATA_STALE"


def test_historical_landslide_rainfall_trigger_comparison():
    """Requirement: Compare historical failure rainfall against current forecast rainfall to determine active landslide warning."""
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "RISK_DETECTED",
        "hazard_count": 1,
        "closest_hazard_distance_m": 150.0,
        "hazards": [{
            "record": {
                "latitude": 7.25,
                "longitude": 80.52,
                "district": "Kandy",
                "incident_type": "Landslide",
                "trigger_rainfall_mm": 100.0,
                "trigger_rainfall_source": "NBRO_EVENT_24H_RECORDED",
                "historical_rainfall_description": "Historically triggered by 100.0mm rainfall in 24h",
            },
            "distance_meters": 150.0,
            "proximity_zone": "CORRIDOR_DIRECT",
            "advisory": "Corridor intersects near historical landslide.",
        }],
        "note": "1 hazard in corridor.",
    }

    # Case 1: Forecast rain 15mm (< 50% of 100mm) -> NO ACTIVE WARNING
    mock_w1 = MagicMock()
    mock_w1.assess_route_weather.return_value = {
        "status": "NO_RISK_DETECTED",
        "available": True,
        "overall_risk_level": "NONE",
        "max_precipitation_forecast_mm": 15.0,
        "weather_points": [{
            "latitude": 7.25,
            "longitude": 80.52,
            "precipitation_mm": 15.0,
        }],
    }
    svc1 = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w1)
    res1 = svc1.assess_route([(7.24, 80.51), (7.26, 80.53)])

    h1 = res1.landslide_summary["hazards"][0]
    assert h1["historical_trigger_rainfall_mm"] == 100.0
    assert h1["current_forecast_rainfall_mm"] == 15.0
    assert h1["rainfall_trigger_percentage"] == 15.0
    assert h1["warning_level"] == "NONE"
    assert h1["is_warning_active"] is False
    assert h1["warning_status"] == "NO_CURRENT_WARNING"
    assert "NO ACTIVE WARNING" in h1["warning_message"]

    # Case 2: Forecast rain 110mm (> 100mm trigger) -> LEVEL 3 EVACUATION WARNING
    mock_w2 = MagicMock()
    mock_w2.assess_route_weather.return_value = {
        "status": "RISK_DETECTED",
        "available": True,
        "overall_risk_level": "HIGH",
        "max_precipitation_forecast_mm": 110.0,
        "weather_points": [{
            "latitude": 7.25,
            "longitude": 80.52,
            "precipitation_mm": 110.0,
        }],
    }
    svc2 = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w2)
    res2 = svc2.assess_route([(7.24, 80.51), (7.26, 80.53)])

    h2 = res2.landslide_summary["hazards"][0]
    assert h2["current_forecast_rainfall_mm"] == 110.0
    assert h2["rainfall_trigger_percentage"] == 110.0
    assert h2["warning_level"] == "LEVEL_3_EVACUATION"
    assert h2["is_warning_active"] is True
    assert h2["warning_status"] == "ACTIVE_LANDSLIDE_WARNING"
    assert "CRITICAL WARNING" in h2["warning_message"]
    assert res2.landslide_summary["active_warnings_count"] == 1
    assert res2.landslide_summary["highest_warning_level"] == "LEVEL_3_EVACUATION"
    assert any("ACTIVE_LANDSLIDE_LEVEL_3_EVACUATION" in r for r in res2.detected_risks)


def test_environmental_risk_score_and_breakdown():
    """Requirement: Route receives an environmental risk score (0-100) with rating and breakdown."""
    mock_ls = MagicMock()
    mock_ls.assess_route_summary.return_value = {
        "status": "RISK_DETECTED",
        "hazard_count": 2,
        "closest_hazard_distance_m": 180.0,
        "hazards": [
            {
                "record": {
                    "latitude": 7.25,
                    "longitude": 80.52,
                    "district": "Kandy",
                    "trigger_rainfall_mm": 80.0,
                },
                "distance_meters": 180.0,
                "proximity_zone": "CORRIDOR_DIRECT",
            }
        ],
    }

    mock_w = MagicMock()
    mock_w.assess_route_weather.return_value = {
        "status": "RISK_DETECTED",
        "available": True,
        "overall_risk_level": "MODERATE",
        "max_precipitation_forecast_mm": 65.0,
        "weather_points": [{
            "latitude": 7.25,
            "longitude": 80.52,
            "precipitation_mm": 65.0,
        }],
    }

    svc = EnvironmentalRiskService(landslide_svc=mock_ls, weather_svc=mock_w)
    res = svc.assess_route([(7.25, 80.52), (7.29, 80.63)])

    # 180m <= 250m -> score_ls = 25 + (2*3=6) = 31
    # MODERATE weather with 65mm -> score_w = 12 + 6 = 18
    # 65mm / 80mm = 81.2% -> LEVEL_2_ALERT -> score_compound = 20
    # total = 31 + 18 + 20 = 69 -> ELEVATED
    assert 0 <= res.environmental_risk_score <= 100
    assert res.environmental_risk_score == 69
    assert res.risk_rating == "ELEVATED"
    assert res.risk_score_breakdown["landslide_proximity_score"] == 31
    assert res.risk_score_breakdown["weather_severity_score"] == 18
    assert res.risk_score_breakdown["compound_trigger_score"] == 20
    assert res.risk_score_breakdown["total_score"] == 69

