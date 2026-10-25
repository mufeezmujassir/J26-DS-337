import urllib.request
import json

url = "http://127.0.0.1:8000/api/routes/multimodal-plan?start=7.2906,80.6337&end=6.9497,80.7891&start_name=Kandy&end_name=Nuwara+Eliya&modes=train,bus,car,bike,walking"
req = urllib.request.Request(url, headers={"User-Agent": "WandarayaAudit/1.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print("RECOMMENDED ROUTE ID:", data.get("recommended_route_id"))
print("TOP-LEVEL RISK SCORE:", data.get("route_environmental_risk_score"))
print("TOP-LEVEL SAFETY IND:", data.get("route_safety_indicator"))
print("-" * 85)
print(f"{'ROUTE ID':<20} | {'NAME':<25} | {'DIST (km)':<9} | {'TIME':<8} | {'RISK':<6} | {'REC'}")
print("-" * 85)
for r in data.get("routes", []):
    rid = r.get("route_id", "")
    rname = r.get("route_name", "")
    rd = r.get("distance_km", 0.0)
    rt = r.get("travel_time_formatted", "")
    rr = r.get("environmental_risk_score", 0.0)
    rec = r.get("is_recommended", False)
    print(f"{rid:<20} | {rname:<25} | {rd:>9.2f} | {rt:<8} | {rr:>6.1f} | {rec}")
print("-" * 85)
comp = data.get("objectives_comparison", {})
print("\nOBJECTIVES COMPARISON 'SAFETY':")
print(json.dumps(comp.get("safety", {}).get("environmental_assessment", {}), indent=2))
