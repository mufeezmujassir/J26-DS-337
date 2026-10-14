import sys
import os
import argparse
import asyncio
import json

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
    if not os.environ.get("ROUTE_API_KEY") and hasattr(settings, "effective_route_api_key"):
        os.environ["ROUTE_API_KEY"] = settings.effective_route_api_key
except Exception:
    pass

os.environ.setdefault("ROUTE_API_BASE_URL", "https://api.openrouteservice.org")

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter
from app.services.spatial import find_nearest_routable_node
from app.schemas.route import RouteRequest, Coordinate
from app.services.route_validation import RouteValidationService
from app.services.route_api_client import RouteAPIClient

async def build_focused_corridor_graph(session, min_lat, max_lat, min_lon, max_lon, padding_deg=0.08):
    """
    Loads real roads and train stations from PostgreSQL database within a bounding box.
    This ensures ultra-fast sub-second graph loading from the 1.28M roads table.
    """
    bbox_min_lat = min_lat - padding_deg
    bbox_max_lat = max_lat + padding_deg
    bbox_min_lon = min_lon - padding_deg
    bbox_max_lon = max_lon + padding_deg

    graph = MultimodalGraph()

    # 1. Load real road segments from PostgreSQL 'roads' table in bounding box
    road_query = text("""
        SELECT 
            road_id,
            total_length_km,
            ST_X(ST_StartPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as start_lon,
            ST_Y(ST_StartPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as start_lat,
            ST_X(ST_EndPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as end_lon,
            ST_Y(ST_EndPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as end_lat
        FROM roads
        WHERE geometry IS NOT NULL
          AND ST_Intersects(geometry, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))
        LIMIT 25000;
    """)

    result = await session.execute(road_query, {
        "min_lon": bbox_min_lon,
        "min_lat": bbox_min_lat,
        "max_lon": bbox_max_lon,
        "max_lat": bbox_max_lat
    })
    rows = result.fetchall()

    for r_id, length, slon, slat, elon, elat in rows:
        if None in (slon, slat, elon, elat):
            continue
        n1 = f"road_{round(slon, 6)}_{round(slat, 6)}"
        n2 = f"road_{round(elon, 6)}_{round(elat, 6)}"
        graph.add_node(Node(node_id=n1, lat=slat, lon=slon))
        graph.add_node(Node(node_id=n2, lat=elat, lon=elon))
        edge = Edge(
            from_node=n1,
            to_node=n2,
            mode=GraphMode.ROAD,
            directed=False,
            attributes={"distance_km": float(length or 0.0), "source_id": str(r_id)}
        )
        try:
            graph.add_edge(edge)
        except ValueError:
            pass

    # 2. Load real train stations in bounding box
    station_query = text("""
        SELECT id, name, lat, lon 
        FROM train_stations 
        WHERE lat BETWEEN :min_lat AND :max_lat 
          AND lon BETWEEN :min_lon AND :max_lon;
    """)
    s_result = await session.execute(station_query, {
        "min_lat": bbox_min_lat,
        "max_lat": bbox_max_lat,
        "min_lon": bbox_min_lon,
        "max_lon": bbox_max_lon
    })
    s_rows = s_result.fetchall()

    for st_id, name, lat, lon in s_rows:
        if lat is None or lon is None:
            continue
        node_id = f"station_{st_id}"
        graph.add_node(Node(node_id=node_id, lat=lat, lon=lon, properties={"name": name}))

    # 3. Add walking transfers between stations and nearest road nodes (max 0.8 km)
    from app.services.transfer_loader import build_transfers
    build_transfers(graph, max_walk_km=0.8)

    return graph

async def run_pipeline(orig_lat: float, orig_lon: float, dest_lat: float, dest_lon: float):
    print("=" * 70)
    print("    WANDARAYA COMPONENT 2: LIVE END-TO-END ROUTING PIPELINE")
    print("=" * 70)
    print(f"\n[INPUT COORDINATES]")
    print(f"  Origin      : Latitude = {orig_lat}, Longitude = {orig_lon}")
    print(f"  Destination : Latitude = {dest_lat}, Longitude = {dest_lon}")

    # Step 1: Connect to Real Database & Load Focused Corridor Graph
    print(f"\n[STEP 1: DATABASE INTEGRATION]")
    min_lat = min(orig_lat, dest_lat)
    max_lat = max(orig_lat, dest_lat)
    min_lon = min(orig_lon, dest_lon)
    max_lon = max(orig_lon, dest_lon)

    print(f"  Connecting to PostgreSQL at {os.environ.get('DATABASE_URL')}...")
    async with AsyncSessionLocal() as session:
        graph = await build_focused_corridor_graph(session, min_lat, max_lat, min_lon, max_lon)

    stats = graph.get_statistics()
    total_edges = sum(stats["edges_by_mode"].values())
    print(f"  Graph Nodes Loaded : {stats['total_nodes']:,}")
    print(f"  Graph Edges Loaded : {total_edges:,}")
    for mode, count in stats["edges_by_mode"].items():
        if count > 0:
            print(f"    - Mode {mode.value.upper():<10}: {count:,} edges")

    # Step 2: Spatial Snapping (Coordinates -> Nearest Routable Graph Node)
    print(f"\n[STEP 2: SPATIAL SNAPPING]")
    orig_node, orig_dist = find_nearest_routable_node(graph, orig_lat, orig_lon, direction="outgoing", max_radius_km=10.0)
    dest_node, dest_dist = find_nearest_routable_node(graph, dest_lat, dest_lon, direction="incoming", max_radius_km=10.0)

    print(f"  Origin Snapped to      : '{orig_node}' (snap distance: {orig_dist:.3f} km)")
    print(f"  Destination Snapped to : '{dest_node}' (snap distance: {dest_dist:.3f} km)")

    if not orig_node or not dest_node:
        print("  [ERROR] Input coordinates could not be snapped to routable network.")
        return

    # Step 3: Run Dijkstra Shortest Path Router (Step 4 Component)
    print(f"\n[STEP 3: LOCAL DIJKSTRA BASELINE ROUTER]")
    router = DijkstraRouter(graph)
    try:
        dijkstra_result = router.route(orig_node, dest_node)
        print(f"  Status        : SUCCESS")
        print(f"  Distance      : {dijkstra_result.total_distance_km:.2f} km")
        print(f"  Modes Used    : {', '.join(dijkstra_result.modes_used)}")
        print(f"  Transfers     : {dijkstra_result.transfers_count}")
        print(f"  Nodes Count   : {dijkstra_result.node_count}")
        print(f"  Edges Count   : {dijkstra_result.edge_count}")
        if dijkstra_result.warnings:
            for w in dijkstra_result.warnings:
                print(f"  Notice        : {w}")
    except ValueError as e:
        print(f"  Dijkstra Result: {e}")
        dijkstra_result = None

    # Step 4: Run Live OpenRouteService (ORS) API Client
    print(f"\n[STEP 4: LIVE OPENROUTESERVICE API QUERY]")
    req = RouteRequest(
        origin=Coordinate(latitude=orig_lat, longitude=orig_lon),
        destination=Coordinate(latitude=dest_lat, longitude=dest_lon)
    )
    client = RouteAPIClient()
    ors_result = await client.get_route(req)

    print(f"  ORS Source    : {ors_result.source}")
    if ors_result.distance is not None:
        print(f"  ORS Distance  : {ors_result.distance:.2f} km")
        print(f"  ORS Duration  : {ors_result.duration / 60.0:.1f} minutes")
        print(f"  Geometry Path : {len(ors_result.geometry or '')} polyline characters")
    else:
        print(f"  ORS Response  : Unable to retrieve road route from external provider.")

    # Step 5: Route Validation Service Comparison
    print(f"\n[STEP 5: VALIDATION & BENCHMARKING]")
    if dijkstra_result and ors_result.distance:
        diff_km = abs(dijkstra_result.total_distance_km - ors_result.distance)
        pct_diff = (diff_km / ors_result.distance) * 100.0
        print(f"  Local Dijkstra Distance : {dijkstra_result.total_distance_km:.2f} km")
        print(f"  External ORS Distance   : {ors_result.distance:.2f} km")
        print(f"  Difference (Delta)      : {diff_km:.2f} km ({pct_diff:.1f}%)")

        validator = RouteValidationService()
        val_result = await validator.validate_route(req, local_distance_km=dijkstra_result.total_distance_km)
        print(f"  Validation Selected     : {val_result.source}")

    # Step 6: Full JSON Output for API Consumers
    print(f"\n[STEP 6: FINAL API JSON RESPONSE PAYLOAD]")
    if dijkstra_result:
        d_dict = dijkstra_result.to_dict()
        # Display clean summary JSON (trim large edge array for readability)
        d_dict["edges_preview"] = d_dict["edges"][:3]
        d_dict["total_edges_omitted_from_preview"] = max(0, len(d_dict["edges"]) - 3)
        del d_dict["edges"]
        print(json.dumps(d_dict, indent=2))

    print("\n" + "=" * 70)
    print("                      TEST EXECUTION COMPLETE")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Live End-to-End Route Pipeline Test")
    # Defaults: Colombo Fort Station area to Maradana Station area
    parser.add_argument("--orig-lat", type=float, default=6.9344, help="Origin Latitude (default: Colombo Fort 6.9344)")
    parser.add_argument("--orig-lon", type=float, default=79.8428, help="Origin Longitude (default: Colombo Fort 79.8428)")
    parser.add_argument("--dest-lat", type=float, default=6.9271, help="Destination Latitude (default: Maradana 6.9271)")
    parser.add_argument("--dest-lon", type=float, default=79.8612, help="Destination Longitude (default: Maradana 79.8612)")

    args = parser.parse_args()
    asyncio.run(run_pipeline(args.orig_lat, args.orig_lon, args.dest_lat, args.dest_lon))

if __name__ == "__main__":
    main()
