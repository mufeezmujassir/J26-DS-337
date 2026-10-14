"""
Interactive Route CLI Tool for WANDARAYA Multimodal Routing
Allows users to enter origin and destination (by name or coordinates)
and test shortest, fastest, and cheapest routes from their local terminal.
"""
import sys
import os
import argparse
import asyncio
import json

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load environment securely from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from app.config import settings
    if not os.environ.get("DATABASE_URL") and hasattr(settings, "DATABASE_URL"):
        os.environ["DATABASE_URL"] = settings.DATABASE_URL
except Exception:
    pass

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter
from app.services.spatial import find_nearest_routable_node, haversine_km
from app.schemas.route import RouteRequest, Coordinate
from app.services.route_api_client import RouteAPIClient

KNOWN_LOCATIONS = {
    "colombo": (6.9344, 79.8428, "Colombo Fort"),
    "colombo fort": (6.9344, 79.8428, "Colombo Fort"),
    "galle": (6.0367, 80.2170, "Galle Station"),
    "matara": (5.9485, 80.5353, "Matara Station"),
    "kandy": (7.2906, 80.6337, "Kandy Station"),
    "negombo": (7.2083, 79.8358, "Negombo Station"),
    "kalutara": (6.5854, 79.9607, "Kalutara South"),
    "bentota": (6.4259, 79.9997, "Bentota"),
    "hikkaduwa": (6.1408, 80.1030, "Hikkaduwa"),
}

def parse_location(user_input: str):
    clean = user_input.strip().lower()
    if clean in KNOWN_LOCATIONS:
        lat, lon, label = KNOWN_LOCATIONS[clean]
        return lat, lon, label
    
    # Try parsing comma-separated lat, lon
    if "," in clean:
        parts = clean.split(",")
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lat, lon, f"Coord ({lat:.4f}, {lon:.4f})"
        except ValueError:
            pass
    
    print(f"\n[!] Location '{user_input}' not recognized.")
    print("    Supported names: Galle, Colombo, Matara, Kandy, Negombo, Kalutara, Bentota, Hikkaduwa")
    print("    Or enter as latitude, longitude (e.g., 6.0367, 80.2170)")
    sys.exit(1)

async def run_routing(start_input: str, end_input: str, objective: str):
    start_lat, start_lon, start_label = parse_location(start_input)
    end_lat, end_lon, end_label = parse_location(end_input)

    canonical_obj = objective.strip().lower()
    if canonical_obj in ["1", "short", "shortest", "dist", "distance"]:
        canonical_obj = "shortest"
    elif canonical_obj in ["2", "fast", "fastest", "time"]:
        canonical_obj = "fastest"
    elif canonical_obj in ["3", "cheap", "cheapest", "cost", "fare"]:
        canonical_obj = "cheapest"
    else:
        canonical_obj = "shortest"

    print("\n" + "=" * 70)
    print("       WANDARAYA MULTIMODAL ROUTING QUERY ENGINE")
    print("=" * 70)
    print(f"[*] Origin         : {start_label} (Lat: {start_lat:.4f}, Lon: {start_lon:.4f})")
    print(f"[*] Destination    : {end_label} (Lat: {end_lat:.4f}, Lon: {end_lon:.4f})")
    print(f"[*] Objective      : {canonical_obj.upper()}")
    
    direct_dist = haversine_km(start_lat, start_lon, end_lat, end_lon)
    print(f"[*] Direct Distance: {direct_dist:.2f} km")

    # 1. External Driving Route via OpenRouteService (if configured)
    print("\n[1] External Highway Driving Route (OpenRouteService):")
    req = RouteRequest(
        origin=Coordinate(latitude=start_lat, longitude=start_lon),
        destination=Coordinate(latitude=end_lat, longitude=end_lon)
    )
    api_client = RouteAPIClient()
    api_res = await api_client.get_route(req)
    if api_res.distance is not None:
        hours = int(api_res.duration // 3600)
        mins = int((api_res.duration % 3600) // 60)
        print(f"    - Source           : OpenRouteService API (Live)")
        print(f"    - Driving Distance : {api_res.distance:.2f} km")
        print(f"    - Driving Time     : {hours}h {mins}m ({api_res.duration / 60.0:.1f} mins)")
    else:
        print(f"    - Notice           : External driving route not available ({api_res.source})")

    # 2. Local Multimodal Graph & Dijkstra Routing
    print("\n[2] Multimodal Network Optimization (PostgreSQL & Dijkstra):")
    graph = MultimodalGraph()

    # Load connected transport stations and corridor
    async with AsyncSessionLocal() as session:
        # Load railway stations
        station_query = text("SELECT id, name, lat, lon FROM train_stations WHERE lat IS NOT NULL AND lon IS NOT NULL;")
        s_res = await session.execute(station_query)
        stations = s_res.fetchall()
        for s_id, s_name, lat, lon in stations:
            graph.add_node(Node(f"station_{s_id}", lat=lat, lon=lon, properties={"name": s_name}))

        # Load Coastal line links if present
        station_map = {s[1].lower(): f"station_{s[0]}" for s in stations}
        
        # Add primary railway corridor edges
        corridor_links = [
            ("colombo fort", "galle", 114.2, 125.0, 240.0, "Coastal Line Express"),
            ("galle", "matara", 44.5, 55.0, 100.0, "Coastal Line South"),
            ("colombo fort", "kandy", 120.5, 170.0, 280.0, "Main Line Upcountry"),
            ("colombo fort", "kalutara south", 42.1, 50.0, 120.0, "Coastal Line Suburban"),
        ]
        for src_name, dst_name, dist_km, time_min, fare_lkr, line_name in corridor_links:
            s_node = station_map.get(src_name)
            d_node = station_map.get(dst_name)
            if s_node and d_node:
                graph.add_edge(Edge(
                    s_node, d_node, GraphMode.RAIL, directed=False,
                    attributes={
                        "distance_km": dist_km,
                        "travel_time_min": time_min,
                        "cost_lkr": fare_lkr,
                        "line": line_name
                    }
                ))

    # Snap coordinates to nearest graph nodes
    start_node, snap_start_dist = find_nearest_routable_node(graph, start_lat, start_lon, max_radius_km=15.0)
    end_node, snap_end_dist = find_nearest_routable_node(graph, end_lat, end_lon, max_radius_km=15.0)

    if not start_node or not end_node:
        print("    [!] Could not snap to routable nodes within 15 km.")
        return

    print(f"    - Snapped Origin   : '{start_node}' (snap offset: {snap_start_dist:.2f} km)")
    print(f"    - Snapped Dest     : '{end_node}' (snap offset: {snap_end_dist:.2f} km)")

    # Execute Dijkstra router
    router = DijkstraRouter(graph, objective=canonical_obj)
    try:
        result = router.route(start_node, end_node)
    except ValueError as e:
        print(f"    [!] Routing error: {e}")
        return

    # 3. Print Results
    print("\n" + "=" * 70)
    print("                    OPTIMIZED ROUTE SUMMARY")
    print("=" * 70)
    print(f"  Selected Objective     : {result.objective.upper()}")
    print(f"  Optimized Weight Metric: {result.optimized_weight:.2f}")
    print(f"  Total Distance         : {result.total_distance_km:.2f} km")
    if result.total_travel_time_min is not None:
        h = int(result.total_travel_time_min // 60)
        m = int(result.total_travel_time_min % 60)
        print(f"  Total Travel Time      : {h}h {m}m ({result.total_travel_time_min:.1f} minutes)")
    else:
        print(f"  Total Travel Time      : Unavailable (incomplete)")
    print(f"  Total Transport Cost   : {result.total_cost_lkr if result.total_cost_lkr is not None else 'N/A'} LKR")
    print(f"  Modes Utilized         : {', '.join(result.modes_used)}")
    print(f"  Transfers Count        : {result.transfers_count}")
    print(f"  Nodes Traversed        : {result.node_count} nodes")
    print(f"  Completeness Flags     : Cost Complete: {result.cost_complete} | Time Complete: {result.travel_time_complete}")
    if result.warnings:
        print("\n  Notices & Warnings:")
        for w in result.warnings:
            print(f"   * {w}")

    print("\n" + "=" * 70)
    print("  Detailed Route Segments:")
    for idx, e in enumerate(result.edges, 1):
        dist = e.attributes.get("distance_km", "N/A")
        time = e.attributes.get("travel_time_min", "N/A")
        cost = e.attributes.get("cost_lkr", "N/A")
        line = e.attributes.get("line", "")
        print(f"   [{idx}] {e.from_node} -> {e.to_node}")
        print(f"       Mode: {e.mode.value.upper()} | Distance: {dist} km | Time: {time} min | Fare: {cost} LKR {f'| Line: {line}' if line else ''}")
    print("=" * 70 + "\n")

def main():
    parser = argparse.ArgumentParser(description="WANDARAYA Interactive Route Query CLI")
    parser.add_argument("--start", type=str, help="Start location name or lat,lon (e.g. Galle)")
    parser.add_argument("--end", type=str, help="Destination location name or lat,lon (e.g. Colombo)")
    parser.add_argument("--objective", type=str, default="shortest", help="Objective: shortest, fastest, or cheapest")
    args = parser.parse_args()

    start = args.start
    end = args.end
    objective = args.objective

    if not start or not end:
        print("\n=======================================================")
        print("   WANDARAYA COMPONENT 2 - INTERACTIVE ROUTE QUERY")
        print("=======================================================")
        print("Quick options: Galle, Colombo, Matara, Kandy, Negombo, Kalutara")
        print("Or enter GPS coordinates directly: latitude, longitude\n")
        try:
            start = input("Enter Start Location (e.g. Galle): ").strip()
            if not start:
                start = "Galle"
            end = input("Enter End Location (e.g. Colombo): ").strip()
            if not end:
                end = "Colombo"
            print("\nSelect Objective:")
            print("  1 = Shortest (minimize distance in km)")
            print("  2 = Fastest (minimize travel time in minutes)")
            print("  3 = Cheapest (minimize transport fare in LKR)")
            obj_choice = input("Enter choice [1/2/3] (default 1): ").strip()
            if obj_choice == "2":
                objective = "fastest"
            elif obj_choice == "3":
                objective = "cheapest"
            else:
                objective = "shortest"
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

    asyncio.run(run_routing(start, end, objective))

if __name__ == "__main__":
    main()
