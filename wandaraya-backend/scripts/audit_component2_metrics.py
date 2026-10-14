"""
Audit script for Step 4 & 5:
Extracts exact counts and statistics from PostgreSQL and MultimodalGraph.
"""
import os
import psycopg
import json
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.transfer_loader import build_transfers

def audit_database():
    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5432/wandaraya").replace("+psycopg", "")
    conn = psycopg.connect(db_url)
    cur = conn.cursor()
    
    stats = {}
    
    # 1. Roads table
    cur.execute("SELECT count(*), count(geometry), count(CASE WHEN total_length_km IS NULL THEN 1 END), count(CASE WHEN total_length_km <= 0 THEN 1 END), min(total_length_km), max(total_length_km) FROM roads;")
    r_total, r_geom, r_null_len, r_zero_len, r_min_len, r_max_len = cur.fetchone()
    stats["roads"] = {
        "total_rows": r_total,
        "valid_geometry_rows": r_geom,
        "missing_distance_rows": r_null_len,
        "zero_or_negative_distance_rows": r_zero_len,
        "min_length_km": float(r_min_len) if r_min_len is not None else None,
        "max_length_km": float(r_max_len) if r_max_len is not None else None,
    }
    
    # Roads duplicate check on road_id
    cur.execute("SELECT count(*) FROM (SELECT road_id FROM roads WHERE road_id IS NOT NULL GROUP BY road_id HAVING count(*) > 1) dups;")
    stats["roads"]["duplicate_road_id_groups"] = cur.fetchone()[0]
    
    # 2. Train stations table
    cur.execute("SELECT count(*), count(CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN 1 END), count(CASE WHEN lat IS NULL OR lon IS NULL THEN 1 END) FROM train_stations;")
    ts_total, ts_valid_coords, ts_null_coords = cur.fetchone()
    stats["train_stations"] = {
        "total_rows": ts_total,
        "valid_coordinates": ts_valid_coords,
        "missing_coordinates": ts_null_coords
    }
    
    # 3. Bus tables
    for tbl in ["bus_fares", "bus_routes", "bus_stops"]:
        try:
            cur.execute(f"SELECT count(*) FROM {tbl};")
            stats[tbl] = {"exists": True, "count": cur.fetchone()[0]}
        except Exception:
            conn.rollback()
            stats[tbl] = {"exists": False, "count": 0}

    # 4. In-memory graph sample load & component inspection
    # Query 5000 connected road segments and train stations to inspect graph structure
    cur.execute("""
        SELECT 
            road_id,
            total_length_km,
            ST_X(ST_StartPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as start_lon,
            ST_Y(ST_StartPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as start_lat,
            ST_X(ST_EndPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as end_lon,
            ST_Y(ST_EndPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as end_lat
        FROM roads
        WHERE geometry IS NOT NULL AND total_length_km > 0
        LIMIT 5000;
    """)
    rows = cur.fetchall()
    
    g = MultimodalGraph()
    missing_dist_edges = 0
    missing_cost_edges = 0
    missing_time_edges = 0
    
    for r_id, length, slon, slat, elon, elat in rows:
        if None in (slon, slat, elon, elat):
            continue
        n1 = f"road_{slon:.6f}_{slat:.6f}"
        n2 = f"road_{elon:.6f}_{elat:.6f}"
        g.add_node(Node(n1, lat=slat, lon=slon))
        g.add_node(Node(n2, lat=elat, lon=elon))
        edge = Edge(
            n1, n2, GraphMode.ROAD, directed=False,
            attributes={"distance_km": float(length) if length else None, "source_id": str(r_id)}
        )
        try:
            g.add_edge(edge)
            if edge.attributes.get("distance_km") is None:
                missing_dist_edges += 1
            if edge.attributes.get("cost_lkr") is None:
                missing_cost_edges += 1
            if edge.attributes.get("travel_time_min") is None:
                missing_time_edges += 1
        except ValueError:
            pass
            
    # Add station nodes
    cur.execute("SELECT name, lat, lon FROM train_stations WHERE lat IS NOT NULL LIMIT 50;")
    st_rows = cur.fetchall()
    for name, lat, lon in st_rows:
        g.add_node(Node(f"station_{name}", lat=lat, lon=lon))
        
    transfers_built = build_transfers(g, max_walk_km=2.0)
    
    graph_stats = g.get_statistics()
    
    # Calculate connected components using BFS
    visited = set()
    components = []
    for node_id in g.nodes:
        if node_id not in visited:
            comp = []
            queue = [node_id]
            visited.add(node_id)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for neighbor in g.edges.get(curr, {}):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            components.append(len(comp))
            
    stats["sample_graph"] = {
        "nodes_loaded": graph_stats["total_nodes"],
        "edges_by_mode": {m.value: cnt for m, cnt in graph_stats["edges_by_mode"].items()},
        "walking_transfers_built": transfers_built,
        "missing_distance_edges": missing_dist_edges,
        "missing_cost_edges": missing_cost_edges,
        "missing_time_edges": missing_time_edges,
        "total_connected_components": len(components),
        "largest_component_size": max(components) if components else 0,
        "isolated_components_count": sum(1 for c in components if c == 1)
    }
    
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    audit_database()
