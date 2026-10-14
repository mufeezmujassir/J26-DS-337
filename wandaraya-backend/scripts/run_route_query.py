import sys
import os
import math
import argparse
import asyncio
from typing import Tuple, List, Optional, Dict, Any

# Ensure UTF-8 output encoding across Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.schemas.route import RouteRequest, Coordinate
from app.services.route_api_client import RouteAPIClient
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter
from app.services.transfer_loader import build_transfers, haversine
from app.services.island_geocoder import geocoder as island_geocoder
from app.services.bus_graph_loader import bus_graph_loader
from app.services.rail_graph_loader import rail_graph_loader
from app.services.scenic_service import scenic_service
from app.services.fare_verifier import fare_verifier

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine(lat1, lon1, lat2, lon2)

def parse_location(user_input: str) -> Tuple[float, float, str]:
    """
    Parses user input into (lat, lon, label) using IslandGeocoder with coordinates,
    gazetteer, stations, and Nominatim fallback.
    """
    cleaned = user_input.strip()

    # 1. Decimal coordinates: "6.9271, 79.8612"
    if "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return lat, lon, f"Coordinates ({lat:.4f}, {lon:.4f})"
            except ValueError:
                pass

    # 2. Island-wide geocoder lookup
    lat, lon, label = island_geocoder.resolve(cleaned, allow_network=True, fuzzy=True)
    if lat is not None and lon is not None:
        return lat, lon, label or cleaned.title()

    print(f"\n[!] Location '{user_input}' could not be resolved.")
    print("    Supported: Any town, village, or station in Sri Lanka (e.g. Colombo, Jaffna, Galle, Kandy, Badulla, Trincomalee)")
    print("    Or enter as decimal coordinates: latitude, longitude (e.g. 6.0367, 80.2170)\n")
    sys.exit(1)

def find_nearest_nodes(graph: MultimodalGraph, lat: float, lon: float, max_radius_km: float = 40.0) -> Dict[str, Tuple[str, float]]:
    """
    Finds the nearest rail node, nearest bus node, and overall nearest node.
    """
    nearest_rail = None
    min_rail_d = max_radius_km
    nearest_bus = None
    min_bus_d = max_radius_km
    nearest_any = None
    min_any_d = max_radius_km

    for n_id, n in graph.nodes.items():
        if n.lat is None or n.lon is None:
            continue
        d = haversine_km(lat, lon, n.lat, n.lon)
        if d < min_any_d:
            min_any_d = d
            nearest_any = n_id

        if n_id.startswith("rail_") and d < min_rail_d:
            min_rail_d = d
            nearest_rail = n_id
        elif n_id.startswith("bus_") and d < min_bus_d:
            min_bus_d = d
            nearest_bus = n_id

    return {
        "any": (nearest_any, min_any_d),
        "rail": (nearest_rail, min_rail_d),
        "bus": (nearest_bus, min_bus_d)
    }

async def evaluate_all_objectives(start_input: str, end_input: str):
    start_lat, start_lon, start_label = parse_location(start_input)
    end_lat, end_lon, end_label = parse_location(end_input)

    print("\n" + "=" * 80)
    print("      WANDARAYA ALL-ISLAND MULTIMODAL ROUTING & SCENIC OPTIMIZATION ENGINE")
    print("=" * 80)
    print(f"[*] Origin Location     : {start_label} (Lat: {start_lat:.4f}, Lon: {start_lon:.4f})")
    print(f"[*] Destination Location: {end_label} (Lat: {end_lat:.4f}, Lon: {end_lon:.4f})")

    direct_dist = haversine_km(start_lat, start_lon, end_lat, end_lon)
    print(f"[*] Haversine Distance  : {direct_dist:.2f} km")

    # 1. OpenRouteService Driving Reference
    print("\n" + "-" * 80)
    print(" 1. EXTERNAL ROAD DRIVING REFERENCE (OpenRouteService API)")
    print("-" * 80)
    req = RouteRequest(
        origin=Coordinate(latitude=start_lat, longitude=start_lon),
        destination=Coordinate(latitude=end_lat, longitude=end_lon)
    )
    api_client = RouteAPIClient()
    try:
        api_res = await api_client.get_route(req)
        if api_res.distance is not None:
            h = int(api_res.duration // 3600)
            m = int((api_res.duration % 3600) // 60)
            print(f"  Driving Road Distance : {api_res.distance:.2f} km")
            print(f"  Driving Travel Time   : {h}h {m}m ({api_res.duration / 60.0:.1f} minutes)")
            print(f"  Data Source           : {api_res.source.upper()} (Live Key Configured)")
        else:
            print(f"  Notice                : Driving route unavailable ({api_res.source})")
    except Exception as e:
        print(f"  Driving Route Notice  : Fallback road model used ({e})")

    # 2. Local All-Island Multimodal Network Construction
    print("\n" + "-" * 80)
    print(" 2. LOCAL ALL-ISLAND MULTIMODAL NETWORK INITIALIZATION")
    print("-" * 80)
    print("  [*] Building island-wide multimodal network (Rail, Bus, Walking Transfers)...")

    graph = MultimodalGraph()

    # Load complete railway network with official ticket prices
    rail_edges_count = rail_graph_loader.load_into_graph(graph)

    # Load all-island bus routes and fares
    bus_edges_count = bus_graph_loader.load_into_graph(graph)

    # Build walking transfer edges between railway and bus hubs within 2.0 km
    transfer_edges_count = build_transfers(graph, max_walk_km=2.0)

    stats = graph.get_statistics()
    total_edges = sum(stats['edges_by_mode'].values())
    rail_edges = sum(v for k, v in stats['edges_by_mode'].items() if 'rail' in str(k).lower())
    bus_edges = sum(v for k, v in stats['edges_by_mode'].items() if 'bus' in str(k).lower())
    trans_edges = sum(v for k, v in stats['edges_by_mode'].items() if 'transfer' in str(k).lower() or 'walk' in str(k).lower())

    print(f"  [*] Multimodal Graph   : {stats['total_nodes']} nodes, {total_edges} edges")
    print(f"      Mode Breakdown     : Rail={rail_edges}, Bus={bus_edges}, Walking Transfers={trans_edges}")

    # Find nearest nodes
    s_nodes = find_nearest_nodes(graph, start_lat, start_lon, max_radius_km=45.0)
    e_nodes = find_nearest_nodes(graph, end_lat, end_lon, max_radius_km=45.0)

    # Connect virtual origin and destination nodes to multimodal graph
    v_start = "origin_point"
    v_end = "destination_point"

    graph.add_node(Node(v_start, lat=start_lat, lon=start_lon, properties={"name": start_label}))
    graph.add_node(Node(v_end, lat=end_lat, lon=end_lon, properties={"name": end_label}))

    # Link origin to nearby rail and bus nodes
    for mode_key in ["rail", "bus", "any"]:
        n_target, dist_km = s_nodes[mode_key]
        if n_target and dist_km <= 40.0:
            walk_time = round((dist_km / 4.5) * 60.0, 1)
            graph.add_edge(Edge(
                v_start, n_target, GraphMode.WALKING, directed=False,
                attributes={"distance_km": dist_km, "travel_time_min": walk_time, "cost_lkr": 0.0, "transfer_type": "access"}
            ))

    # Link destination from nearby rail and bus nodes
    for mode_key in ["rail", "bus", "any"]:
        n_target, dist_km = e_nodes[mode_key]
        if n_target and dist_km <= 40.0:
            walk_time = round((dist_km / 4.5) * 60.0, 1)
            graph.add_edge(Edge(
                n_target, v_end, GraphMode.WALKING, directed=False,
                attributes={"distance_km": dist_km, "travel_time_min": walk_time, "cost_lkr": 0.0, "transfer_type": "egress"}
            ))

    rail_s, rail_s_dist = s_nodes["rail"]
    rail_e, rail_e_dist = e_nodes["rail"]
    bus_s, bus_s_dist = s_nodes["bus"]
    bus_e, bus_e_dist = e_nodes["bus"]

    print(f"  Origin Transit Access  : Rail -> {rail_s} ({rail_s_dist:.2f} km) | Bus -> {bus_s} ({bus_s_dist:.2f} km)")
    print(f"  Dest. Transit Access   : Rail -> {rail_e} ({rail_e_dist:.2f} km) | Bus -> {bus_e} ({bus_e_dist:.2f} km)")

    # 3. Side-by-Side Comparison Table for ALL 4 Objectives with SCENIC SCORE
    objectives = ["shortest", "fastest", "cheapest", "slower"]
    results = {}
    scenic_results = {}

    for obj in objectives:
        router = DijkstraRouter(graph, objective=obj)
        try:
            res = router.route(v_start, v_end)
            results[obj] = res
            if res:
                # Extract path coordinates for scenic analysis
                path_coords = []
                for n_id in res.nodes:
                    node = graph.get_node(n_id)
                    if node and node.lat is not None and node.lon is not None:
                        path_coords.append((node.lat, node.lon))
                scenic_info = scenic_service.calculate_scenic_score(
                    path_coords, res.total_distance_km, corridor_radius_km=8.5, objective=obj
                )
                scenic_results[obj] = scenic_info
            else:
                scenic_results[obj] = None
        except ValueError as e:
            results[obj] = None
            scenic_results[obj] = None

    print("\n" + "=" * 80)
    print("                     ALL 4 OBJECTIVES COMPARISON TABLE")
    print("=" * 80)
    header = f"{'Objective':<10} | {'Distance':<11} | {'Travel Time':<15} | {'Fare Cost':<12} | {'Modes':<14} | {'Transfers':<9} | {'Scenic Score'}"
    print(header)
    print("-" * 80)
    for obj in objectives:
        res = results.get(obj)
        sc = scenic_results.get(obj)
        if res:
            dist_str = f"{res.total_distance_km:.2f} km"
            if res.total_travel_time_min is not None:
                h = int(res.total_travel_time_min // 60)
                m = int(res.total_travel_time_min % 60)
                time_str = f"{h}h {m:02d}m ({res.total_travel_time_min:.0f}m)"
            else:
                time_str = "N/A"
            cost_str = f"{res.total_cost_lkr:.1f} LKR" if res.total_cost_lkr is not None else "N/A"
            # Filter out walking for major transit mode label
            transit_modes = [m.capitalize() for m in res.modes_used if m.lower() != "walking"]
            modes_str = ", ".join(transit_modes) if transit_modes else "Walking"
            trans_str = str(res.transfers_count)
            sc_str = f"{sc['scenic_score']}/100" if sc else "N/A"
            print(f"{obj.upper():<10} | {dist_str:<11} | {time_str:<15} | {cost_str:<12} | {modes_str:<14} | {trans_str:<9} | {sc_str}")
        else:
            print(f"{obj.upper():<10} | {'UNREACHABLE':<11} | {'-':<15} | {'-':<12} | {'-':<14} | {'-':<9} | -")

    # 4. Specific Mode Breakdown (Rail Options, Bus Options, Multimodal)
    print("\n" + "=" * 80)
    print("                     TRANSPORT MODE BREAKDOWN & TARIFFS")
    print("=" * 80)

    verified_rail_fares = None
    verified_bus_fare = None
    verified_bus_service = None
    rail_scenic = None
    bus_scenic = None

    # A. Rail Mode Evaluation
    if rail_s and rail_e and rail_s != rail_e:
        router_rail = DijkstraRouter(graph, objective="fastest")
        try:
            res_rail = router_rail.route(rail_s, rail_e)
            if res_rail:
                s_name = graph.get_node(rail_s).properties.get("name", rail_s)
                e_name = graph.get_node(rail_e).properties.get("name", rail_e)
                rail_fare = rail_graph_loader.get_fare(s_name, e_name)
                verified_rail_fares = rail_fare
                h = int(res_rail.total_travel_time_min // 60)
                m = int(res_rail.total_travel_time_min % 60)

                rail_coords = []
                for n_id in res_rail.nodes:
                    node = graph.get_node(n_id)
                    if node and node.lat is not None and node.lon is not None:
                        rail_coords.append((node.lat, node.lon))
                rail_scenic = scenic_service.calculate_scenic_score(
                    rail_coords, res_rail.total_distance_km, corridor_radius_km=6.0, objective="rail"
                )

                print("\n[*] RAILWAY JOURNEY OPTION (Sri Lanka Railways):")
                print(f"    Line Stations        : {s_name} -> {e_name}")
                print(f"    Track Distance       : {res_rail.total_distance_km:.2f} km")
                print(f"    Train Travel Time    : {h}h {m:02d}m ({res_rail.total_travel_time_min:.1f} mins)")
                print(f"    Railway Scenic Score : {rail_scenic['scenic_score']}/100 ({rail_scenic['scenic_rating']})")
                print("    Official Fares       :")
                print(f"      - 3rd Class        : {rail_fare['3rd_class_rs']:.2f} LKR (Most Affordable)")
                print(f"      - 2nd Class        : {rail_fare['2nd_class_rs']:.2f} LKR (Reserved/Semi-Express)")
                print(f"      - 1st Class        : {rail_fare['1st_class_rs']:.2f} LKR (Air-Conditioned / Observation)")
        except ValueError:
            print("\n[*] RAILWAY JOURNEY OPTION : Direct rail connection unavailable for this corridor.")

    # B. Bus Mode Evaluation
    if bus_s and bus_e and bus_s != bus_e:
        router_bus = DijkstraRouter(graph, objective="fastest")
        try:
            res_bus = router_bus.route(bus_s, bus_e)
            if res_bus:
                h = int(res_bus.total_travel_time_min // 60)
                m = int(res_bus.total_travel_time_min % 60)
                bus_labels = [e.attributes.get("route_no") for e in res_bus.edges if e.attributes.get("route_no")]
                bus_name = ", ".join(set(bus_labels)) if bus_labels else "Standard / Expressway Service"
                verified_bus_fare = res_bus.total_cost_lkr
                verified_bus_service = bus_name

                bus_coords = []
                for n_id in res_bus.nodes:
                    node = graph.get_node(n_id)
                    if node and node.lat is not None and node.lon is not None:
                        bus_coords.append((node.lat, node.lon))
                bus_scenic = scenic_service.calculate_scenic_score(
                    bus_coords, res_bus.total_distance_km, corridor_radius_km=6.0, objective="fastest"
                )

                print("\n[*] BUS TRANSIT OPTION (National Transport Commission Regulated):")
                print(f"    Service Route        : {bus_name}")
                print(f"    Bus Road Distance    : {res_bus.total_distance_km:.2f} km")
                print(f"    Bus Travel Time      : {h}h {m:02d}m ({res_bus.total_travel_time_min:.1f} mins)")
                print(f"    Bus Scenic Score     : {bus_scenic['scenic_score']}/100 ({bus_scenic['scenic_rating']})")
                print(f"    Regulated Bus Fare   : {res_bus.total_cost_lkr:.2f} LKR")
        except ValueError:
            pass

    # 5. Groq AI Fare Verification Report (Live AI Audit)
    print("\n" + "=" * 80)
    print("          GROQ AI FARE VERIFICATION REPORT (LIVE AI AUDIT)")
    print("=" * 80)
    audit = fare_verifier.verify_fares(
        origin=start_label,
        destination=end_label,
        distance_km=direct_dist,
        train_fares=verified_rail_fares,
        bus_fare=verified_bus_fare,
        bus_service_name=verified_bus_service
    )
    print(f"[*] Audit Source : {audit['source']} ({audit['model']})")
    print(f"[*] Status       : {audit['status']}\n")
    for line in audit["analysis_text"].split("\n"):
        if line.strip():
            print(f"    {line.strip()}")

    # 6. Scenic Highlights and Attractions List
    print("\n" + "=" * 80)
    print("                     SCENIC HIGHLIGHTS & ATTRACTIONS REPORT")
    print("=" * 80)

    if rail_scenic or bus_scenic:
        print("[*] TRANSIT MODE SCENIC SCORE BREAKDOWN:")
        if rail_scenic:
            print(f"    - Railway (Train) Scenic Score : {rail_scenic['scenic_score']}/100 ({rail_scenic['scenic_rating']})")
        if bus_scenic:
            print(f"    - Bus Transit Scenic Score     : {bus_scenic['scenic_score']}/100 ({bus_scenic['scenic_rating']})")
        print()

    best_scenic = rail_scenic or max((sc for sc in scenic_results.values() if sc), key=lambda x: x["scenic_score"], default=None)
    if best_scenic:
        print(f"[*] Corridor Scenic Score : {best_scenic['scenic_score']}/100")
        print(f"[*] Scenic Rating         : {best_scenic['scenic_rating']}")
        print(f"[*] Attractions Passed    : {best_scenic['total_scenic_places']} scenic sites across traversed corridor")
        if best_scenic["scenic_places"]:
            print("\n  Notable Scenic Places Along the Route:")
            for p in best_scenic["scenic_places"]:
                dist_info = f"({p['distance_km']:.1f} km from transit corridor)"
                distr = f"[{p['district']}]" if p['district'] else ""
                prog_pct = f"[{int(p.get('progress', 0.0) * 100)}%]"
                print(f"   * {prog_pct:<7} {p['name']} {distr} — {p['category']} {dist_info}")
    else:
        print("  No designated scenic attractions identified directly along this corridor.")

    # 6. Detailed Route Legs / Segments
    print("\n" + "=" * 80)
    print("                     DETAILED ROUTE LEGS / SEGMENTS")
    print("=" * 80)
    for obj in objectives:
        res = results.get(obj)
        if not res:
            continue
        print(f"\n[>>> {obj.upper()} ROUTE DETAILS <<<]")
        print(f"  Path Sequence: {' -> '.join(res.nodes)}")
        for idx, e in enumerate(res.edges, 1):
            dist = e.attributes.get("distance_km", "N/A")
            time = e.attributes.get("travel_time_min", "N/A")
            cost = e.attributes.get("cost_lkr", "N/A")
            route_no = e.attributes.get("route_no", "")
            line = e.attributes.get("line_name", "") or e.attributes.get("line", "")
            via = e.attributes.get("via", "")
            label = route_no or line
            if via:
                label += f" (via {via})"
            print(f"   Leg {idx}: {e.from_node} -> {e.to_node}")
            print(f"          Mode: {e.mode.value.upper():<7} | Dist: {dist} km | Time: {time} min | Fare: {cost} LKR {f'| {label}' if label else ''}")

        if res.warnings:
            print("  Notices & Data Integrity Warnings:")
            for w in res.warnings:
                print(f"   * {w}")

    print("=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="WANDARAYA All-Island Multi-Objective Route Evaluation CLI")
    parser.add_argument("--start", type=str, help="Start location name or lat,lon (e.g. Colombo or Jaffna)")
    parser.add_argument("--end", type=str, help="Destination location name or lat,lon (e.g. Jaffna or Galle)")
    args = parser.parse_args()

    start = args.start
    end = args.end

    if not start or not end:
        print("\n" + "=" * 70)
        print("   WANDARAYA COMPONENT 2 - ALL-ISLAND MULTIMODAL ROUTING")
        print("=" * 70)
        print("Enter ANY city, town, or place in Sri Lanka (e.g. Colombo, Jaffna, Galle, Kandy, Badulla, Trincomalee)")
        print("Or enter decimal latitude, longitude coordinates (e.g. 9.6651, 80.0093)\n")
        try:
            start = input("Enter Start Location (e.g. 'Colombo'): ").strip()
            if not start:
                start = "Colombo"
            end = input("Enter End Location   (e.g. 'Jaffna'): ").strip()
            if not end:
                end = "Jaffna"
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

    asyncio.run(evaluate_all_objectives(start, end))

if __name__ == "__main__":
    main()
