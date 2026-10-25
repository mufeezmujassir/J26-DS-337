import urllib.request
import json

url = "http://127.0.0.1:8000/api/routes/multimodal-plan?start=6.9389,79.8542&end=6.0328,80.2150&start_name=Colombo&end_name=Galle&modes=train,bus,car,bike,walking"
req = urllib.request.Request(url, headers={"User-Agent": "WandarayaAudit/1.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print("COLOMBO -> GALLE OBJECTIVES COMPARISON:")
print("=" * 80)
print(f"{'OBJECTIVE':<10} | {'DIST (km)':<9} | {'TIME':<8} | {'FARE':<10} | {'RISK /100':<10} | {'SAFETY':<8} | {'MODES'}")
print("-" * 80)
comp = data.get("objectives_comparison", {})
for obj in ["shortest", "fastest", "cheapest", "slower", "scenic", "safety"]:
    v = comp.get(obj)
    if v:
        d = v.get("distance_km", 0.0)
        t = v.get("travel_time_formatted", "")
        f = v.get("fare_cost_lkr", 0.0)
        risk = v.get("environmental_risk_score", 0.0)
        safe = v.get("safety_indicator", 100.0)
        modes = ", ".join(v.get("modes", []))
        print(f"{obj.upper():<10} | {d:>9.2f} | {t:<8} | {f:>10.2f} | {risk:>10.1f} | {safe:>7.1f}% | {modes}")
print("=" * 80)
print("Recommended Route:", data.get("recommended_route_id"))
