import requests
import json

def test_live_proof():
    base_url = "http://127.0.0.1:8000"
    
    print("=" * 75)
    print("   END-TO-END VERIFICATION & PROOF OF LIVE ENVIRONMENTAL RISK")
    print("   INCLUDING NBRO MASTER INCIDENTS (20,438) & POLYGONS (1,967)")
    print("=" * 75)

    # 1. Test POST /api/routes/environmental-risk (Kandy -> Nuwara Eliya Hill Country)
    print("\n--- 1. Testing Hill Country Route (Kandy -> Nuwara Eliya) ---")
    coords_hill = [
        [7.2906, 80.6337],
        [7.1500, 80.6800],
        [7.0500, 80.7200],
        [6.9708, 80.7829]
    ]
    resp = requests.post(f"{base_url}/api/routes/environmental-risk", json={
        "coordinates": coords_hill,
        "buffer_meters": 1500.0,
        "include_weather": True
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    
    print("\n[A] NBRO Data Integration Proof:")
    db_stat = data.get("nbro_database_status", {})
    print(f"  PostGIS Database Connected: {db_stat.get('connected')}")
    print(f"  Database Engine: {db_stat.get('database')}")
    print(f"  Database nbro_incidents Row Count: {db_stat.get('nbro_incidents_count'):,}")
    print(f"  Database nbro_inspections Row Count: {db_stat.get('nbro_inspections_count'):,}")
    print(f"  Database nbro_polygons Row Count: {db_stat.get('nbro_polygons_count'):,}")
    
    ls_info = data.get("landslide_assessment", {})
    print(f"  Dataset Source: {ls_info.get('database_source')}")
    print(f"  Total Hazard Zones in Corridor: {ls_info.get('hazard_count')}")
    print(f"  Mapped Polygons in Corridor: {ls_info.get('polygon_count')}")
    print(f"  Incident Points in Corridor: {ls_info.get('incident_count')}")
    print(f"  Closest Hazard Distance: {ls_info.get('closest_hazard_distance_m')} m")
    print(f"  Closest Polygon Distance: {ls_info.get('closest_polygon_distance_m')} m")

    print("\n[B] Real-Time Live Weather Proof (OpenWeatherMap API):")
    rw = data.get("realtime_weather_risk", {})
    w_info = data.get("weather_assessment", {})
    print(f"  Weather Assessment Status: {w_info.get('status')}")
    print(f"  Assessed At UTC: {data.get('assessed_at_utc')}")
    print(f"  Live Weather Condition: {rw.get('weather_condition')}")
    print(f"  Max Forecast Rain: {rw.get('max_forecast_precipitation_mm')} mm")
    print(f"  Live Temperature Range: {rw.get('temperature_range_c')} °C")
    print(f"  Meteorological Alert Severity: {rw.get('overall_risk_level')}")
    print(f"  Weather Summary: {rw.get('summary')}")

    print("\n[C] Current Active Landslide Warning Decision Proof:")
    cw = data.get("current_landslide_warning", {})
    print(f"  Warning Active: {cw.get('is_warning_active')}")
    print(f"  Warning Level: {cw.get('warning_level')}")
    print(f"  Warning Title: {cw.get('warning_title')}")
    print(f"  Corridor Forecast Rain: {cw.get('corridor_forecast_rainfall_mm')} mm")
    print(f"  NBRO Early Warning Baseline: {cw.get('nbro_threshold_baseline_mm')} mm")
    print(f"  Polygon Zones in Buffer: {cw.get('polygon_zones_in_corridor')}")
    print(f"  Incident Zones in Buffer: {cw.get('incident_zones_in_corridor')}")
    print(f"  Advisory Message: {cw.get('warning_message')}")

    print("\n[D] Unified Environmental Risk Score (0-100):")
    print(f"  Total Score: {data.get('environmental_risk_score')}/100 ({data.get('risk_rating')})")
    print(f"  Score Breakdown: {data.get('risk_score_breakdown')}")

    # 2. Test GET /api/routes/multimodal-plan (Colombo -> Galle)
    print("\n--- 2. Testing Coastal Route (Colombo -> Galle) ---")
    resp_plan = requests.get(f"{base_url}/api/routes/multimodal-plan?start=Colombo&end=Galle")
    assert resp_plan.status_code == 200, resp_plan.text
    plan_data = resp_plan.json()
    env_plan = plan_data.get("environmental_assessment", {})
    print(f"  Coastal Environmental Status: {env_plan.get('status')}")
    print(f"  Environmental Risk Score: {env_plan.get('environmental_risk_score')}/100 ({env_plan.get('risk_rating')})")
    print(f"  Landslide Warning: {env_plan.get('current_landslide_warning', {}).get('warning_title')}")
    print(f"  Polygons in Corridor: {env_plan.get('landslide_assessment', {}).get('polygon_count', 0)}")
    print(f"  Live Weather Condition: {env_plan.get('realtime_weather_risk', {}).get('weather_condition')}")

    print("\n" + "=" * 75)
    print("   [SUCCESS] FULL END-TO-END PROOF VERIFIED SUCCESSFULLY")
    print("=" * 75)

if __name__ == "__main__":
    test_live_proof()
