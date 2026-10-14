"""
WANDARAYA Component 2 - Dedicated Swagger UI Runner
====================================================
Runs interactive Swagger UI documentation exclusively for Component 2:
- Multimodal Dijkstra Routing (Shortest, Fastest, Cheapest, Slower, Scenic)
- Sri Lanka Railways (SLR) 1st, 2nd, and 3rd Class Fares
- National Transport Commission (NTC) Regulated Bus Fares
- Live Groq AI Fare Audit Verification
- Continuous Polyline Scenic Scoring (Railway vs Bus)
- External ORS Driving Route Benchmark & Fallback

No database, Redis, Qdrant, or Airflow dependencies required.
Does NOT modify app/main.py or any other existing project files.
"""

import sys
import uvicorn
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.routers import route_validation
from app.routers import routes

# Multimodal Core Services
from app.schemas.route import DijkstraRouteRequest, DijkstraRouteResponse
from app.services.graph import MultimodalGraph, GraphMode, Node, Edge
from app.services.dijkstra import DijkstraRouter
from app.services.rail_graph_loader import rail_graph_loader
from app.services.bus_graph_loader import bus_graph_loader
from app.services.transfer_loader import build_transfers, haversine as haversine_km
from app.services.scenic_service import scenic_service
from app.services.fare_verifier import fare_verifier

app = FastAPI(
    title="WANDARAYA Component 2: Multimodal Routing & Scenic Intelligence",
    description="""
## All-Island Multimodal Routing, Fare Verification & Scenic Scoring Engine

This interactive Swagger UI exposes all Component 2 services:
* **All 5 Routing Objectives**: Shortest (km), Fastest (min), Cheapest (LKR), Slower (Leisure), and Scenic (Picturesque Landscapes).
* **Official Public Transit Tariffs**: Sri Lanka Railways (1st/2nd/3rd class) & NTC Regulated Bus Fares.
* **Live AI Audit**: Real-time fare verification via Groq Cloud (`openai/gpt-oss-20b`).
* **Continuous Corridor Scenic Scoring**: Decoupled Railway vs. Bus scenic ratings & journey progress landmarks.
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include existing Component 2 routers
app.include_router(routes.router)
app.include_router(route_validation.router, prefix="/api")

# Predefined coordinates for common Sri Lankan destinations
POPULAR_LOCATIONS = {
    "colombo": (6.9389, 79.8542),
    "badulla": (6.9900, 81.0570),
    "galle": (6.0328, 80.2150),
    "kandy": (7.2906, 80.6337),
    "jaffna": (9.6651, 80.0093),
    "matara": (5.9496, 80.5469),
    "negombo": (7.2088, 79.8358),
    "anuradhapura": (8.3114, 80.4037),
    "polonnaruwa": (7.9403, 81.0188),
    "trincomalee": (8.5874, 81.2152),
    "batticaloa": (7.7170, 81.7000),
    "nuwara eliya": (6.9708, 80.7829),
    "ella": (6.8667, 81.0466),
    "hikkaduwa": (6.1395, 80.1063),
    "bentota": (6.4256, 79.9958),
    "kalutara": (6.5854, 79.9607),
    "kurunegala": (7.4863, 80.3623),
    "dambulla": (7.8742, 80.6511),
    "sigiriya": (7.9570, 80.7603),
    "hambantota": (6.1246, 81.1185),
    "ratnapura": (6.6828, 80.3992),
    "vavuniya": (8.7542, 80.4982),
    "mannar": (8.9810, 79.9044),
    "kilinochchi": (9.3803, 80.3992),
    "avissawella": (6.9536, 80.2081),
    "hatton": (6.8916, 80.5960),
    "nanu oya": (6.9392, 80.7417),
}

def parse_location(loc_str: str):
    cleaned = loc_str.strip().lower()
    if cleaned in POPULAR_LOCATIONS:
        lat, lon = POPULAR_LOCATIONS[cleaned]
        return lat, lon, loc_str.strip().title()

    if "," in loc_str:
        parts = loc_str.split(",")
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lat, lon, f"({lat:.4f}, {lon:.4f})"
        except ValueError:
            pass

    for k, v in POPULAR_LOCATIONS.items():
        if k in cleaned or cleaned in k:
            return v[0], v[1], k.title()

    return 6.9389, 79.8542, loc_str.strip().title()

_GRAPH: Optional[MultimodalGraph] = None

def get_graph() -> MultimodalGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = MultimodalGraph()
        rail_graph_loader.load_into_graph(_GRAPH)
        bus_graph_loader.load_into_graph(_GRAPH)
        build_transfers(_GRAPH, max_walk_km=2.0)
    return _GRAPH

def find_transit_access(lat: float, lon: float, graph: MultimodalGraph):
    min_rail_d = float("inf")
    nearest_rail = None
    min_bus_d = float("inf")
    nearest_bus = None

    for n_id, n in graph.nodes.items():
        if n.lat is None or n.lon is None:
            continue
        d = haversine_km(lat, lon, n.lat, n.lon)
        if n_id.startswith("rail_") and d < min_rail_d:
            min_rail_d = d
            nearest_rail = n_id
        elif n_id.startswith("bus_") and d < min_bus_d:
            min_bus_d = d
            nearest_bus = n_id

    return {
        "rail": (nearest_rail, min_rail_d),
        "bus": (nearest_bus, min_bus_d)
    }

class MultimodalPlanRequest(BaseModel):
    start: str = Field(default="Colombo", example="Colombo", description="Origin city name or coordinates (e.g. 'Colombo' or '6.9389, 79.8542')")
    end: str = Field(default="Badulla", example="Badulla", description="Destination city name or coordinates (e.g. 'Badulla' or '6.9900, 81.0570')")

@app.post(
    "/api/routes/multimodal-plan",
    tags=["Component 2 - High Level Plan"],
    summary="Complete Multimodal Plan (5 Objectives, Rail & Bus Fares, Groq AI & Scenic Scores)"
)
@app.get(
    "/api/routes/multimodal-plan",
    tags=["Component 2 - High Level Plan"],
    summary="Complete Multimodal Plan (GET via Query Parameters)"
)
async def plan_journey(start: str = "Colombo", end: str = "Badulla"):
    """
    Computes complete all-island multimodal journey plans:
    * **5 Routing Objectives**: Shortest, Fastest, Cheapest, Slower, Scenic
    * **Sri Lanka Railways 1st, 2nd, and 3rd Class Fares**
    * **National Transport Commission Regulated Bus Fares**
    * **Live Groq AI Fare Audit Verification (`openai/gpt-oss-20b`)**
    * **Decoupled Railway vs. Bus Scenic Scores** & Landmark Highlights
    """
    try:
        start_lat, start_lon, start_label = parse_location(start)
        end_lat, end_lon, end_label = parse_location(end)
        direct_dist = haversine_km(start_lat, start_lon, end_lat, end_lon)

        graph = get_graph()
        s_nodes = find_transit_access(start_lat, start_lon, graph)
        e_nodes = find_transit_access(end_lat, end_lon, graph)

        v_start = "origin_point"
        v_end = "destination_point"

        graph.add_node(Node(v_start, lat=start_lat, lon=start_lon, properties={"label": start_label}))
        graph.add_node(Node(v_end, lat=end_lat, lon=end_lon, properties={"label": end_label}))

        # Add walking links to transit access nodes
        for mode_key in ["rail", "bus"]:
            s_target, s_d = s_nodes[mode_key]
            if s_target and s_d <= 25.0:
                graph.add_edge(Edge(v_start, s_target, GraphMode.WALKING, True, {"distance_km": s_d, "travel_time_min": (s_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(s_target, v_start, GraphMode.WALKING, True, {"distance_km": s_d, "travel_time_min": (s_d / 4.5) * 60.0, "cost_lkr": 0.0}))

            e_target, e_d = e_nodes[mode_key]
            if e_target and e_d <= 25.0:
                graph.add_edge(Edge(e_target, v_end, GraphMode.WALKING, True, {"distance_km": e_d, "travel_time_min": (e_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, e_target, GraphMode.WALKING, True, {"distance_km": e_d, "travel_time_min": (e_d / 4.5) * 60.0, "cost_lkr": 0.0}))

        rail_s, rail_s_dist = s_nodes["rail"]
        rail_e, rail_e_dist = e_nodes["rail"]
        bus_s, bus_s_dist = s_nodes["bus"]
        bus_e, bus_e_dist = e_nodes["bus"]

        objectives = ["shortest", "fastest", "cheapest", "slower", "scenic"]
        objectives_comparison = {}
        scenic_results = {}

        for obj in objectives:
            router = DijkstraRouter(graph, objective=obj)
            try:
                res = router.route(v_start, v_end)
                if res:
                    coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    scenic_info = scenic_service.calculate_scenic_score(coords, res.total_distance_km, corridor_radius_km=7.5, objective=obj)
                    scenic_results[obj] = scenic_info
                    h = int(res.total_travel_time_min // 60) if res.total_travel_time_min else 0
                    m = int(res.total_travel_time_min % 60) if res.total_travel_time_min else 0
                    modes = [mod.capitalize() for mod in res.modes_used if mod.lower() != "walking"]
                    objectives_comparison[obj] = {
                        "distance_km": round(res.total_distance_km, 2),
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "fare_cost_lkr": round(res.total_cost_lkr, 2) if res.total_cost_lkr is not None else None,
                        "modes": modes or ["Walking"],
                        "transfers": res.transfers_count,
                        "scenic_score": scenic_info["scenic_score"],
                        "scenic_rating": scenic_info["scenic_rating"]
                    }
                else:
                    objectives_comparison[obj] = None
            except Exception:
                objectives_comparison[obj] = None

        # Railway Specific Option
        rail_option = None
        rail_scenic = None
        if rail_s and rail_e and rail_s != rail_e:
            try:
                res_rail = DijkstraRouter(graph, objective="fastest").route(rail_s, rail_e)
                if res_rail:
                    s_name = graph.get_node(rail_s).properties.get("name", rail_s)
                    e_name = graph.get_node(rail_e).properties.get("name", rail_e)
                    rail_fare = rail_graph_loader.get_fare(s_name, e_name)
                    r_coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res_rail.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    rail_scenic = scenic_service.calculate_scenic_score(r_coords, res_rail.total_distance_km, corridor_radius_km=6.0, objective="rail")
                    h = int(res_rail.total_travel_time_min // 60)
                    m = int(res_rail.total_travel_time_min % 60)
                    rail_option = {
                        "stations": f"{s_name} -> {e_name}",
                        "track_distance_km": round(res_rail.total_distance_km, 2),
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "scenic_score": rail_scenic["scenic_score"],
                        "scenic_rating": rail_scenic["scenic_rating"],
                        "fares_lkr": {
                            "third_class": rail_fare["3rd_class_rs"],
                            "second_class": rail_fare["2nd_class_rs"],
                            "first_class": rail_fare["1st_class_rs"]
                        }
                    }
            except Exception:
                pass

        # Bus Specific Option
        bus_option = None
        bus_scenic = None
        if bus_s and bus_e and bus_s != bus_e:
            try:
                res_bus = DijkstraRouter(graph, objective="fastest").route(bus_s, bus_e)
                if res_bus:
                    labels = [e.attributes.get("route_no") for e in res_bus.edges if e.attributes.get("route_no")]
                    bus_name = ", ".join(set(labels)) if labels else "Direct / Trunk Bus Service"
                    b_coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res_bus.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    bus_scenic = scenic_service.calculate_scenic_score(b_coords, res_bus.total_distance_km, corridor_radius_km=6.0, objective="fastest")
                    h = int(res_bus.total_travel_time_min // 60)
                    m = int(res_bus.total_travel_time_min % 60)
                    bus_option = {
                        "service_route": bus_name,
                        "road_distance_km": round(res_bus.total_distance_km, 2),
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "scenic_score": bus_scenic["scenic_score"],
                        "scenic_rating": bus_scenic["scenic_rating"],
                        "regulated_fare_lkr": round(res_bus.total_cost_lkr, 2)
                    }
            except Exception:
                pass

        # Groq AI Audit
        audit = fare_verifier.verify_fares(
            origin=start_label,
            destination=end_label,
            distance_km=direct_dist,
            train_fares=rail_option["fares_lkr"] if rail_option else None,
            bus_fare=bus_option["regulated_fare_lkr"] if bus_option else None,
            bus_service_name=bus_option["service_route"] if bus_option else None
        )

        best_scenic = rail_scenic or max((sc for sc in scenic_results.values() if sc), key=lambda x: x["scenic_score"], default=None)

        return {
            "origin": {"name": start_label, "lat": start_lat, "lon": start_lon},
            "destination": {"name": end_label, "lat": end_lat, "lon": end_lon},
            "haversine_distance_km": round(direct_dist, 2),
            "objectives_comparison": objectives_comparison,
            "railway_option": rail_option,
            "bus_option": bus_option,
            "groq_fare_audit": {
                "source": audit.get("source"),
                "status": audit.get("status"),
                "analysis_text": audit.get("analysis_text")
            },
            "scenic_intelligence": {
                "railway_scenic_score": rail_scenic["scenic_score"] if rail_scenic else None,
                "bus_scenic_score": bus_scenic["scenic_score"] if bus_scenic else None,
                "corridor_scenic_score": best_scenic["scenic_score"] if best_scenic else 25,
                "scenic_rating": best_scenic["scenic_rating"] if best_scenic else "Standard Transit Corridor",
                "attractions_count": best_scenic["total_scenic_places"] if best_scenic else 0,
                "notable_highlights": best_scenic["scenic_places"][:10] if best_scenic and best_scenic["scenic_places"] else []
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", tags=["Health"])
def root():
    return {
        "message": "WANDARAYA Component 2 Swagger Server is Running",
        "swagger_docs": "/docs",
        "redoc_docs": "/redoc"
    }

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  LAUNCHING WANDARAYA COMPONENT 2 SWAGGER UI SERVER")
    print("=" * 70)
    print("  [*] Swagger Documentation : http://127.0.0.1:8000/docs")
    print("  [*] ReDoc Documentation   : http://127.0.0.1:8000/redoc")
    print("=" * 70 + "\n")
    uvicorn.run("run_swagger:app", host="127.0.0.1", port=8000, reload=True)
