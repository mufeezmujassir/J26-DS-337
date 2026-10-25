import urllib.request
import json
import sys

url = "http://127.0.0.1:8000/api/routes/multimodal-plan?start=7.2906,80.6337&end=6.9708,80.7829&start_name=Kandy&end_name=Nuwara+Eliya"
print(f"Requesting: {url}")

try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("HTTP Status:", resp.status)
        print("Origin:", data.get("origin"))
        print("Destination:", data.get("destination"))
        print("Recommended Route ID:", data.get("recommended_route_id"))
        print("Optimization Algorithm:", data.get("optimization_algorithm"))
        print("Optimization Status:", data.get("optimization_status"))
        print("Route Environmental Risk Score:", data.get("route_environmental_risk_score"))
        print("Route Safety Indicator:", data.get("route_safety_indicator"))
        print("Maximum Segment Risk:", data.get("maximum_segment_risk"))
        print("Highest Risk Segment:", data.get("highest_risk_segment"))
        print("Landslide Warning Status:", data.get("landslide_warning_status"))
        print("Weather Warning Status:", data.get("weather_warning_status"))
        print("Risk Explanation:", data.get("risk_explanation"))
        print("Data Completeness:", data.get("data_completeness"))
        print("Data Freshness:", data.get("data_freshness"))
        routes = data.get("routes", [])
        print(f"Total Routes Returned: {len(routes)}")
        for r in routes:
            print(f"  [{r.get('route_id')}] {r.get('route_name')} | EnvRisk: {r.get('environmental_risk_score')} | Safety: {r.get('safety_indicator')}% | MaxSegRisk: {r.get('maximum_segment_risk')} | Time: {r.get('travel_time_formatted')} | Fare: {r.get('fare_cost_lkr')} LKR | Recommended: {r.get('is_recommended')}")
            segs = r.get("legs", [])
            print(f"    -> Segments: {len(segs)} segments. First seg: {segs[0].get('segment_id') if segs else 'None'} with risk: {segs[0].get('environmental_risk_score') if segs else 'N/A'}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
