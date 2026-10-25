import json
import os

filepath = os.path.join(os.path.dirname(__file__), "..", "wandaraya-backend", "scripts", "evaluation_results.json")
if not os.path.exists(filepath):
    filepath = "c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/evaluation_results.json"

with open(filepath, "r") as f:
    data = json.load(f)

print(f"Total Component 2 Benchmark Records: {len(data)}")

strategies = {}
for r in data:
    s = r["strategy"]
    strategies.setdefault(s, []).append(r)

print("\n" + "=" * 125)
print(f"{'Strategy':<40} | {'Time (min)':<11} | {'Dist (km)':<10} | {'Risk (/100)':<12} | {'Risk Red %':<11} | {'Detour %':<10} | {'Elevated Min':<13} | {'Runtime (ms)'}")
print("=" * 125)

for s, rows in strategies.items():
    valid = [r for r in rows if r["success"]]
    if not valid:
        continue
    avg_t = sum(r["total_travel_time_min"] for r in valid) / len(valid)
    avg_d = sum(r["total_distance_km"] for r in valid) / len(valid)
    avg_r = sum(r["route_average_risk"] for r in valid) / len(valid)
    avg_red = sum(r["risk_reduction_pct"] for r in valid) / len(valid)
    avg_det = sum(r["time_detour_pct"] for r in valid) / len(valid)
    avg_elev = sum(r["time_spent_in_elevated_risk_min"] for r in valid) / len(valid)
    avg_cpu = sum(r["runtime_ms"] for r in valid) / len(valid)
    print(f"{s:<40} | {avg_t:>9.1f}m | {avg_d:>8.1f}km | {avg_r:>10.1f}/100 | {avg_red:>9.1f}% | {avg_det:>8.1f}% | {avg_elev:>11.1f}m | {avg_cpu:>10.2f}ms")
print("=" * 125)

print("\n" + "=" * 125)
print("EVALUATION BY SCENARIO:")
print("=" * 125)
scenarios = {}
for r in data:
    sc = r["scenario"]
    scenarios.setdefault(sc, []).append(r)

for sc, rows in scenarios.items():
    print(f"\n--- Scenario: {sc} ({len(rows)} trials) ---")
    d_rows = [r for r in rows if r["strategy"] == "Shortest-Time Dijkstra" and r["success"]]
    r_rows = [r for r in rows if "RAGRO" in r["strategy"] and r["success"]]
    if d_rows and r_rows:
        d_risk = sum(r["route_average_risk"] for r in d_rows) / len(d_rows)
        r_risk = sum(r["route_average_risk"] for r in r_rows) / len(r_rows)
        d_time = sum(r["total_travel_time_min"] for r in d_rows) / len(d_rows)
        r_time = sum(r["total_travel_time_min"] for r in r_rows) / len(r_rows)
        red = ((d_risk - r_risk) / d_risk) * 100 if d_risk > 0 else 0
        detour = ((r_time - d_time) / d_time) * 100 if d_time > 0 else 0
        print(f"  Baseline Risk: {d_risk:.1f}/100 -> RAGRO Risk: {r_risk:.1f}/100 (Risk Reduction: {red:.1f}%)")
        print(f"  Baseline Time: {d_time:.1f}m -> RAGRO Time: {r_time:.1f}m (Detour Ratio: {detour:+.1f}%)")
print("=" * 125)

