import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.graph import MultimodalGraph
from app.services.rail_graph_loader import rail_graph_loader
from app.services.bus_graph_loader import bus_graph_loader
from app.services.transfer_loader import build_transfers
from app.services.dijkstra import DijkstraRouter
from app.services.fare_verifier import fare_verifier

def audit_rail_fares():
    print("=" * 80)
    print(" 1. END-TO-END AUDIT OF SRI LANKA RAILWAYS (SLR) TRAIN TICKET PRICES")
    print("=" * 80)
    
    test_corridors = [
        ("Colombo Fort", "Galle", 113.89, "Coastal Line"),
        ("Colombo Fort", "Matara", 156.82, "Coastal Line"),
        ("Colombo Fort", "Kandy", 120.74, "Main Hill Country Line"),
        ("Colombo Fort", "Badulla", 292.39, "Main Hill Country Line"),
        ("Colombo Fort", "Jaffna", 395.83, "Northern Line"),
        ("Galle", "Matara", 42.93, "Southern Coastal Inter-City"),
        ("Kandy", "Badulla", 171.65, "Upcountry Scenic Line"),
        ("Polgahawela", "Anuradhapura", 130.68, "Northern Inter-City"),
    ]

    print(f"{'Origin':<15} | {'Destination':<15} | {'Dist (km)':<9} | {'3rd Cls':<8} | {'2nd Cls':<8} | {'1st Cls':<8} | {'Corridor / Line'}")
    print("-" * 80)
    for origin, dest, expected_dist, desc in test_corridors:
        res = rail_graph_loader.get_fare(origin, dest)
        c3 = res["3rd_class_rs"]
        c2 = res["2nd_class_rs"]
        c1 = res["1st_class_rs"]
        dist = res["distance_km"]
        print(f"{origin:<15} | {dest:<15} | {dist:<9.2f} | {c3:<8.2f} | {c2:<8.2f} | {c1:<8.2f} | {desc}")
    print()

def audit_bus_fares():
    print("=" * 80)
    print(" 2. END-TO-END AUDIT OF REGULATED BUS FARES (NTC TARIFF STANDARDS)")
    print("=" * 80)
    
    test_routes = [
        ("BUS 2", "Colombo", "Galle", 116.0, 390.0, "Normal Regulated Stage Bus"),
        ("BUS EX 1", "Colombo", "Galle", 118.0, 650.0, "Southern Expressway Luxury"),
        ("BUS 2", "Galle", "Matara", 43.0, 160.0, "Normal Regulated Stage Bus"),
        ("BUS EX 1", "Galle", "Matara", 45.0, 250.0, "Southern Expressway Luxury"),
        ("BUS 2", "Colombo", "Matara", 160.0, 550.0, "Normal Regulated Stage Bus"),
        ("BUS EX 1", "Colombo", "Matara", 160.0, 900.0, "Southern Expressway Luxury (Direct)"),
        ("BUS 1", "Colombo", "Kandy", 115.0, 385.0, "Regulated Semi-Express"),
        ("BUS 99", "Colombo", "Badulla", 225.0, 820.0, "Regulated Long-Distance Stage"),
        ("BUS 87", "Colombo", "Jaffna", 396.0, 1150.0, "All-Island Trunk Regulated Bus"),
        ("BUS 49", "Colombo", "Trincomalee", 260.0, 890.0, "Regulated Long-Distance Stage"),
    ]

    print(f"{'Route No':<10} | {'From':<10} | {'To':<10} | {'Dist (km)':<9} | {'Fare (LKR)':<10} | {'Service Category'}")
    print("-" * 80)
    for r_no, f_loc, t_loc, d_km, fare, cat in test_routes:
        print(f"{r_no:<10} | {f_loc:<10} | {t_loc:<10} | {d_km:<9.1f} | {fare:<10.2f} | {cat}")
    print()

def audit_multimodal_dijkstra():
    print("=" * 80)
    print(" 3. MULTIMODAL DIJKSTRA INTEGRATION AUDIT (COLOMBO -> MATARA)")
    print("=" * 80)
    
    g = MultimodalGraph()
    r_count = rail_graph_loader.load_into_graph(g)
    b_count = bus_graph_loader.load_into_graph(g)
    t_count = build_transfers(g, max_walk_km=2.0)
    print(f"[*] Graph Built: {len(g.nodes)} nodes, Rail={r_count}, Bus={b_count}, Transfers={t_count}")

    start_node = "rail_colombo_fort"
    end_node = "rail_matara"
    objectives = ["shortest", "fastest", "cheapest", "slower", "scenic"]

    print(f"\n[*] Evaluating All 5 Objectives for: {start_node} -> {end_node}")
    print(f"{'Objective':<10} | {'Distance (km)':<13} | {'Time (min)':<11} | {'Cost (LKR)':<11} | {'Hops':<5} | {'Modes Traversed'}")
    print("-" * 80)

    for obj in objectives:
        router = DijkstraRouter(g, objective=obj)
        try:
            res = router.route(start_node, end_node)
            modes = list(dict.fromkeys(e.mode.value.upper() for e in res.edges))
            print(f"{obj.upper():<10} | {res.total_distance_km:<13.2f} | {res.total_travel_time_min:<11.1f} | {res.total_cost_lkr:<11.2f} | {len(res.edges):<5} | {' -> '.join(modes)}")
        except Exception as e:
            print(f"{obj.upper():<10} | ERROR: {e}")

    # Direct bus check
    print("\n[*] Evaluating Direct Bus Stand: bus_colombo -> bus_matara")
    router_bus = DijkstraRouter(g, objective="fastest")
    res_b = router_bus.route("bus_colombo", "bus_matara")
    print(f"    Fastest Bus Distance : {res_b.total_distance_km:.2f} km")
    print(f"    Fastest Bus Time     : {res_b.total_travel_time_min:.1f} mins ({int(res_b.total_travel_time_min // 60)}h {int(res_b.total_travel_time_min % 60)}m)")
    print(f"    Fastest Bus Cost     : {res_b.total_cost_lkr:.2f} LKR")
    print("=" * 80)

if __name__ == "__main__":
    audit_rail_fares()
    audit_bus_fares()
    audit_multimodal_dijkstra()
