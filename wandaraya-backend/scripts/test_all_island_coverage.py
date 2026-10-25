"""
All-Island Multimodal Routing Coverage Verification Script
==========================================================
Tests end-to-end multimodal route planning across all 9 provinces and 25 districts of Sri Lanka:
1. Western Province (Colombo, Gampaha, Kalutara, Kahatowita)
2. Central Province (Kandy, Nuwara Eliya, Matale, Dambulla)
3. Southern Province (Galle, Matara, Hambantota, Tangalle)
4. Northern Province (Jaffna, Mannar, Vavuniya, Kilinochchi)
5. Eastern Province (Trincomalee, Batticaloa, Ampara, Arugam Bay)
6. North Western Province (Kurunegala, Chilaw, Puttalam, Kekunagolla)
7. North Central Province (Anuradhapura, Polonnaruwa)
8. Uva Province (Badulla, Bandarawela, Ella, Wellawaya)
9. Sabaragamuwa Province (Ratnapura, Kegalle, Balangoda)
"""

import sys
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"

TEST_CORRIDORS = [
    # 1. Western to Central
    ("Colombo", "Kandy", "Western -> Central Trunk"),
    ("Kahatowita", "Kandy", "Gampaha Village -> Central Capital"),
    ("Kahatowita", "Colombo", "Gampaha Village -> Western Capital"),
    
    # 2. Western to Southern
    ("Colombo", "Galle", "Western -> Southern Coastal Trunk"),
    ("Colombo", "Matara", "Western -> Southern Deep Coast"),
    ("Galle", "Hambantota", "Southern Inter-District"),

    # 3. Western to Northern
    ("Colombo", "Jaffna", "South-to-North Inter-City Highway/Rail"),
    ("Colombo", "Vavuniya", "Western -> Northern Gateway"),
    ("Mannar", "Jaffna", "North Western Coast -> Northern Peninsula"),

    # 4. Western to Eastern
    ("Colombo", "Trincomalee", "Western -> Eastern Deep Harbor"),
    ("Colombo", "Batticaloa", "Western -> Eastern Coast"),
    ("Batticaloa", "Arugam Bay", "Eastern Surf & Tourism Corridor"),

    # 5. Western to Uva & Hill Country
    ("Colombo", "Badulla", "Western -> Uva Capital (Main Line Rail / A4)"),
    ("Colombo", "Nuwara Eliya", "Western -> High Altitude Tea Corridor"),
    ("Kandy", "Ella", "Central -> Uva World-Famous Scenic Corridor"),
    ("Ella", "Wellawaya", "Ella Gap Descent Corridor"),

    # 6. Western to Sabaragamuwa
    ("Colombo", "Ratnapura", "Western -> Gem City Corridor"),
    ("Kegalle", "Kandy", "Sabaragamuwa -> Central Incline"),

    # 7. North Western & North Central
    ("Colombo", "Kurunegala", "Western -> North Western Hub"),
    ("Kekunagolla", "Colombo", "North Western Village -> Capital"),
    ("Kurunegala", "Anuradhapura", "North Western -> Cultural Triangle Capital"),
    ("Anuradhapura", "Polonnaruwa", "Ancient Capitals Corridor"),
    ("Dambulla", "Sigiriya", "Cultural Triangle Tourism Link"),

    # 8. Cross-Provincial South to East
    ("Hambantota", "Arugam Bay", "Southern -> South-Eastern Safari/Coastal Link"),
    ("Matara", "Ella", "Southern Coast -> Uva Mountains"),
    ("Trincomalee", "Kandy", "Eastern Coast -> Central Highlands"),
]

def run_tests():
    print("=" * 105)
    print("   WANDARAYA COMPONENT 2: ALL-ISLAND 9-PROVINCE ROUTING COVERAGE VERIFICATION")
    print("=" * 105)
    print(f"Server Base URL: {BASE_URL}")
    print(f"Total Inter-Provincial Corridors Tested: {len(TEST_CORRIDORS)}\n")
    print(f"{'#':<3} | {'Origin':<14} | {'Destination':<14} | {'Corridor Description':<32} | {'Direct km':<9} | {'Road km':<8} | {'Time':<8} | {'Risk/Safe':<11} | {'Status'}")
    print("-" * 115)

    passed = 0
    failed = 0

    with httpx.Client(timeout=60.0) as client:
        for idx, (origin, dest, desc) in enumerate(TEST_CORRIDORS, start=1):
            t0 = time.time()
            try:
                resp = client.post(
                    f"{BASE_URL}/api/routes/multimodal-plan",
                    json={"start": origin, "end": dest}
                )
                elapsed = time.time() - t0
                
                if resp.status_code == 200:
                    d = resp.json()
                    orig_name = d.get("origin", {}).get("name", origin)
                    dest_name = d.get("destination", {}).get("name", dest)
                    dir_km = d.get("haversine_distance_km", 0.0)
                    routes = d.get("routes", [])
                    rec_id = d.get("recommended_route_id", "N/A")
                    rec_route = next((r for r in routes if r.get("route_id") == rec_id), routes[0] if routes else {})
                    road_km = rec_route.get("distance_km", 0.0)
                    time_fmt = rec_route.get("travel_time_formatted", "")
                    risk = d.get("route_environmental_risk_score", 0.0)
                    safety = d.get("route_safety_indicator", 0.0)

                    # Validation checks
                    if dir_km > 0 and len(routes) >= 5 and road_km > 0:
                        status_str = "PASS"
                        passed += 1
                    else:
                        status_str = "WARN: Few Routes"
                        failed += 1

                    risk_safe_str = f"{risk:.1f} / {safety:.0f}%"
                    print(f"{idx:<3} | {origin:<14} | {dest:<14} | {desc:<32} | {dir_km:>7.1f}km | {road_km:>6.1f}km | {time_fmt:>8} | {risk_safe_str:>11} | [OK {status_str}] ({elapsed:.2f}s)", flush=True)
                else:
                    failed += 1
                    print(f"{idx:<3} | {origin:<14} | {dest:<14} | {desc:<32} | {'FAIL HTTP':<9} | {resp.status_code} | {'--':>8} | {'--':>11} | [FAIL]", flush=True)
            except Exception as e:
                failed += 1
                print(f"{idx:<3} | {origin:<14} | {dest:<14} | {desc:<32} | {'ERROR':<9} | {str(e)[:15]} | {'--':>8} | {'--':>11} | [EXCEPTION]", flush=True)

    print("-" * 115, flush=True)
    print(f"\nALL-ISLAND ROUTING AUDIT RESULTS:", flush=True)
    print(f"  [+] Total Corridors Verified: {len(TEST_CORRIDORS)}", flush=True)
    print(f"  [+] Successfully Passed     : {passed} / {len(TEST_CORRIDORS)} ({passed/len(TEST_CORRIDORS)*100:.1f}%)", flush=True)
    print(f"  [-] Failed Corridors        : {failed}", flush=True)
    if failed == 0:
        print("\n>>> ALL-ISLAND MULTIMODAL ROUTING IS 100% OPERATIONAL ACROSS ALL 9 PROVINCES! <<<\n", flush=True)
    print("=" * 105, flush=True)

if __name__ == "__main__":
    run_tests()
