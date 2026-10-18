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
from typing import Dict, Any, Optional, List, Tuple
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
import os

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.routers import route_validation
from app.routers import routes

# Multimodal Core Services
from app.schemas.route import DijkstraRouteRequest, DijkstraRouteResponse, RouteRequest, Coordinate
from app.services.route_validation import RouteValidationService
from app.services.graph import MultimodalGraph, GraphMode, Node, Edge
from app.services.dijkstra import DijkstraRouter
from app.services.rail_graph_loader import rail_graph_loader
from app.services.bus_graph_loader import bus_graph_loader
from app.services.transfer_loader import build_transfers, haversine as haversine_km
from app.services.scenic_service import scenic_service
from app.services.fare_verifier import fare_verifier
from app.services.environmental_risk_service import environmental_risk_service

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

# Mount static assets (Local Leaflet CSS/JS, icons) for zero-latency offline loading
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Predefined coordinates for common Sri Lankan destinations
POPULAR_LOCATIONS = {
    # Capital & Western Coast Hubs
    "colombo": (6.9389, 79.8542),
    "colombo fort": (6.9344, 79.8428),
    "pettah": (6.9366, 79.8525),
    "mount lavinia": (6.8378, 79.8656),
    "dehiwala": (6.8528, 79.8647),
    "moratuwa": (6.7730, 79.8816),
    "panadura": (6.7132, 79.9074),
    "wadduwa": (6.6667, 79.9333),
    "kalutara": (6.5854, 79.9607),
    "beruwala": (6.4789, 79.9828),
    "bentota": (6.4256, 79.9958),
    "ambalangoda": (6.2361, 80.0542),
    "hikkaduwa": (6.1395, 80.1063),
    # Southern Coastal & Surf Tourism Corridors
    "galle": (6.0328, 80.2150),
    "galle fort": (6.0270, 80.2175),
    "unawatuna": (6.0104, 80.2492),
    "weligama": (5.9723, 80.4289),
    "mirissa": (5.9483, 80.4578),
    "matara": (5.9496, 80.5469),
    "dickwella": (5.9678, 80.6922),
    "hiriketiya": (5.9622, 80.6975),
    "tangalle": (6.0244, 80.7941),
    "hambantota": (6.1246, 81.1185),
    # Wildlife & Safari National Parks
    "tissamaharama": (6.2806, 81.2878),
    "kataragama": (6.4136, 81.3325),
    "yala": (6.3719, 81.5204),
    "udawalawe": (6.4746, 80.8986),
    "wilpattu": (8.4550, 80.0388),
    "minneriya": (8.0336, 80.8942),
    "sinharaja": (6.4170, 80.4167),
    # Hill Country Scenic Vistas & Tea Country
    "kandy": (7.2906, 80.6337),
    "peradeniya": (7.2608, 80.5960),
    "pinnawala": (7.3013, 80.3867),
    "matale": (7.4675, 80.6234),
    "hatton": (6.8916, 80.5960),
    "adams peak": (6.8096, 80.4994),
    "sri pada": (6.8096, 80.4994),
    "kitulgala": (6.9906, 80.4139),
    "nanu oya": (6.9392, 80.7417),
    "nuwara eliya": (6.9708, 80.7829),
    "horton plains": (6.8028, 80.8044),
    "worlds end": (6.7869, 80.7936),
    "haputale": (6.7686, 80.9503),
    "bandarawela": (6.8259, 80.9982),
    "ella": (6.8667, 81.0466),
    "badulla": (6.9900, 81.0570),
    # Cultural Triangle & Ancient Cities
    "kurunegala": (7.4863, 80.3623),
    "dambulla": (7.8742, 80.6511),
    "sigiriya": (7.9570, 80.7603),
    "habarana": (8.0336, 80.7511),
    "polonnaruwa": (7.9403, 81.0188),
    "anuradhapura": (8.3114, 80.4037),
    # Eastern Coast & Uva Province Hubs
    "trincomalee": (8.5874, 81.2152),
    "nilaveli": (8.6875, 81.1892),
    "batticaloa": (7.7170, 81.7000),
    "kattankudy": (7.6805, 81.7290),
    "ampara": (7.2978, 81.6790),
    "kalmunai": (7.4167, 81.8333),
    "monaragala": (6.8728, 81.3507),
    "wellawaya": (6.7410, 81.1017),
    "pottuvil": (6.8711, 81.8286),
    "arugam bay": (6.8422, 81.8290),
    "pasikuda": (7.9256, 81.5644),
    # Northern Peninsula & Mannar
    "vavuniya": (8.7542, 80.4982),
    "mannar": (8.9810, 79.9044),
    "kilinochchi": (9.3803, 80.3992),
    "jaffna": (9.6651, 80.0093),
    "point pedro": (9.8241, 80.2362),
    # Airport & Commercial Corridors
    "negombo": (7.2088, 79.8358),
    "katunayake": (7.1690, 79.8860),
    "ratnapura": (6.6828, 80.3992),
    "avissawella": (6.9536, 80.2081),
}

def parse_location(loc_str: str):
    if not loc_str:
        return 6.9389, 79.8542, "Colombo"

    cleaned = loc_str.strip().lower()

    # 1. Decimal coordinates: "6.0367, 80.2170" or "6.0367 80.2170"
    if "," in loc_str or " " in loc_str:
        parts = [p.strip() for p in loc_str.replace(",", " ").split() if p.strip()]
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                if 5.0 <= lat <= 10.5 and 79.0 <= lon <= 82.5:
                    return lat, lon, f"Coord ({lat:.4f}, {lon:.4f})"
            except ValueError:
                pass

    # 2. Direct exact match in POPULAR_LOCATIONS
    if cleaned in POPULAR_LOCATIONS:
        lat, lon = POPULAR_LOCATIONS[cleaned]
        return lat, lon, loc_str.strip().title()

    # 3. Substring match in POPULAR_LOCATIONS
    for k, v in POPULAR_LOCATIONS.items():
        if k in cleaned or cleaned in k:
            return v[0], v[1], k.title()

    # 4. Railway station coordinates lookup
    try:
        from app.services.rail_graph_loader import rail_graph_loader
        st_norm = cleaned.replace(" railway station", "").replace(" station", "").strip()
        if st_norm in rail_graph_loader.station_coords:
            lat, lon = rail_graph_loader.station_coords[st_norm]
            return lat, lon, f"{st_norm.title()} Station"
    except Exception:
        pass

    # 5. IslandGeocoder 6,900+ places gazetteer
    try:
        from app.services.island_geocoder import geocoder
        lat, lon, label = geocoder.resolve(cleaned, allow_network=False)
        if lat is not None and lon is not None:
            return lat, lon, label or loc_str.strip().title()
    except Exception:
        pass

    return 6.9389, 79.8542, loc_str.strip().title()

_GRAPH: Optional[MultimodalGraph] = None

def get_graph() -> MultimodalGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = MultimodalGraph()
        rail_graph_loader.load_into_graph(_GRAPH)
        bus_graph_loader.load_into_graph(_GRAPH)

        # Regional trunk bus corridors connecting provinces across Sri Lanka
        regional_corridors = [
            ("bus_batticaloa", "bus_kattankudy", "Batticaloa Bus Stand", "Kattankudy Bus Stop", 7.7170, 81.7000, 7.6805, 81.7290, 5.2, 12.0, 35.0, "BUS 22", "Main Road"),
            ("bus_kattankudy", "bus_ampara", "Kattankudy Bus Stop", "Ampara Bus Stand", 7.6805, 81.7290, 7.2978, 81.6790, 48.0, 70.0, 125.0, "BUS 22", "Kalmunai"),
            ("bus_batticaloa", "bus_ampara", "Batticaloa Bus Stand", "Ampara Bus Stand", 7.7170, 81.7000, 7.2978, 81.6790, 52.0, 75.0, 130.0, "BUS 22", "Kalmunai"),
            ("bus_ampara", "bus_pottuvil", "Ampara Bus Stand", "Pottuvil / Arugam Bay Bus Stand", 7.2978, 81.6790, 6.8711, 81.8286, 54.0, 75.0, 135.0, "BUS 35", "Akkaraipattu"),
            ("bus_pottuvil", "bus_monaragala", "Pottuvil / Arugam Bay Bus Stand", "Monaragala Bus Stand", 6.8711, 81.8286, 6.8728, 81.3507, 78.0, 110.0, 195.0, "BUS 35", "Siyambalanduwa"),
            ("bus_ampara", "bus_hambantota", "Ampara Bus Stand", "Hambantota Bus Stand", 7.2978, 81.6790, 6.1246, 81.1185, 135.0, 180.0, 360.0, "BUS 35/32", "Monaragala, Thanamalwila"),
            ("bus_hambantota", "bus_tangalle", "Hambantota Bus Stand", "Tangalle Bus Stand", 6.1246, 81.1185, 6.0244, 80.7941, 37.0, 50.0, 135.0, "BUS 32", "Ambalantota"),
            ("bus_tangalle", "bus_matara", "Tangalle Bus Stand", "Matara Bus Stand", 6.0244, 80.7941, 5.9496, 80.5469, 38.0, 55.0, 140.0, "BUS 32", "Dickwella"),
            ("bus_hambantota", "bus_matara", "Hambantota Bus Stand", "Matara Bus Stand", 6.1246, 81.1185, 5.9496, 80.5469, 75.0, 110.0, 290.0, "BUS 32", "Tangalle"),
            ("bus_matara", "bus_mirissa", "Matara Bus Stand", "Mirissa Bus Stop", 5.9496, 80.5469, 5.9483, 80.4578, 11.0, 20.0, 50.0, "BUS 2", "Coast Road"),
            ("bus_mirissa", "bus_galle", "Mirissa Bus Stop", "Galle Bus Stand", 5.9483, 80.4578, 6.0328, 80.2150, 32.0, 50.0, 120.0, "BUS 2", "Weligama, Ahangama"),
            ("bus_badulla", "bus_ella", "Badulla Bus Stand", "Ella Bus Stop", 6.9900, 81.0570, 6.8667, 81.0466, 23.0, 40.0, 75.0, "BUS 10", "Hali-Ela"),
            ("bus_ella", "bus_wellawaya", "Ella Bus Stop", "Wellawaya Bus Stand", 6.8667, 81.0466, 6.7410, 81.1017, 27.0, 45.0, 90.0, "BUS 99", "Ravana Falls"),
            ("bus_wellawaya", "bus_hambantota", "Wellawaya Bus Stand", "Hambantota Bus Stand", 6.7410, 81.1017, 6.1246, 81.1185, 75.0, 95.0, 210.0, "BUS 32", "Thanamalwila"),
            ("bus_badulla", "bus_ampara", "Badulla Bus Stand", "Ampara Bus Stand", 6.9900, 81.0570, 7.2978, 81.6790, 95.0, 150.0, 250.0, "BUS 35", "Bibile"),
            ("bus_badulla", "bus_hambantota", "Badulla Bus Stand", "Hambantota Bus Stand", 6.9900, 81.0570, 6.1246, 81.1185, 115.0, 160.0, 310.0, "BUS 32", "Ella, Wellawaya"),
            ("bus_kandy", "bus_dambulla", "Kandy Bus Stand", "Dambulla Bus Stand", 7.2906, 80.6337, 7.8742, 80.6511, 72.0, 110.0, 210.0, "BUS 43", "Matale"),
            ("bus_dambulla", "bus_sigiriya", "Dambulla Bus Stand", "Sigiriya Bus Stop", 7.8742, 80.6511, 7.9570, 80.7603, 16.0, 25.0, 60.0, "BUS 490", "Inamaluwa"),
            ("bus_dambulla", "bus_polonnaruwa", "Dambulla Bus Stand", "Polonnaruwa Bus Stand", 7.8742, 80.6511, 7.9403, 81.0188, 67.0, 90.0, 180.0, "BUS 48", "Habarana"),
            ("bus_polonnaruwa", "bus_batticaloa", "Polonnaruwa Bus Stand", "Batticaloa Bus Stand", 7.9403, 81.0188, 7.7170, 81.7000, 105.0, 150.0, 320.0, "BUS 48", "Valaichchenai"),
            ("bus_trincomalee", "bus_batticaloa", "Trincomalee Bus Stand", "Batticaloa Bus Stand", 8.5874, 81.2152, 7.7170, 81.7000, 138.0, 195.0, 420.0, "BUS 89", "Valaichchenai"),
            ("bus_anuradhapura", "bus_trincomalee", "Anuradhapura Bus Stand", "Trincomalee Bus Stand", 8.3114, 80.4037, 8.5874, 81.2152, 110.0, 150.0, 310.0, "BUS 42", "Horowupotana"),
        ]
        for f_id, t_id, f_name, t_name, lat1, lon1, lat2, lon2, dist, time_m, fare, r_no, via in regional_corridors:
            if f_id not in _GRAPH.nodes:
                _GRAPH.add_node(Node(f_id, lat=lat1, lon=lon1, properties={"name": f_name, "mode": "bus"}))
            if t_id not in _GRAPH.nodes:
                _GRAPH.add_node(Node(t_id, lat=lat2, lon=lon2, properties={"name": t_name, "mode": "bus"}))
            _GRAPH.add_edge(Edge(f_id, t_id, GraphMode.BUS, False, {"distance_km": dist, "travel_time_min": time_m, "cost_lkr": fare, "route_no": r_no, "via": via}))

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
    start: Optional[str] = Field(default=None, description="Origin city name or coordinates (e.g. 'Colombo' or '6.9389, 79.8542')")
    end: Optional[str] = Field(default=None, description="Destination city name or coordinates (e.g. 'Badulla' or '6.9900, 81.0570')")
    origin: Optional[str] = Field(default=None, description="Alias for start")
    destination: Optional[str] = Field(default=None, description="Alias for end")
    start_name: Optional[str] = None
    end_name: Optional[str] = None
    modes: Optional[str] = Field(default="train,bus,car,bike,walking", description="Selected transport modes (comma-separated: train, bus, car, bike, walking)")

_SWAGGER_ROAD_BENCHMARK_CACHE = {}

def enrich_corridor_coords(coords: List[Tuple[float, float]], graph: MultimodalGraph) -> List[Tuple[float, float]]:
    """
    Enriches a 2-point direct coordinate line by sampling intermediate transport nodes
    along the transport corridor ellipse, ensuring polylines curve naturally with Sri Lanka's geography.
    """
    if len(coords) != 2:
        return coords
    p_start, p_end = coords[0], coords[1]
    tot_d = haversine_km(p_start[0], p_start[1], p_end[0], p_end[1])
    if tot_d < 8.0:
        return coords

    corridor = []
    for nid, node in graph.nodes.items():
        if node.lat is None or node.lon is None or nid in ("origin_point", "destination_point"):
            continue
        d1 = haversine_km(p_start[0], p_start[1], node.lat, node.lon)
        d2 = haversine_km(node.lat, node.lon, p_end[0], p_end[1])
        if (d1 + d2) < tot_d * 1.15:
            corridor.append((d1, (round(node.lat, 5), round(node.lon, 5))))

    corridor.sort(key=lambda x: x[0])
    if len(corridor) > 1:
        step = max(1, len(corridor) // 30)
        subsampled = [c[1] for c in corridor[::step]]
        return [p_start] + subsampled + [p_end]
    return coords


@app.post(
    "/api/routes/multimodal",
    tags=["Component 2 - High Level Plan"],
    summary="Complete Multimodal Plan with Environmental Risk (5 Objectives)"
)
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
async def plan_journey(
    payload: Optional[MultimodalPlanRequest] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    start_name: Optional[str] = None,
    end_name: Optional[str] = None,
    modes: Optional[str] = "train,bus,car,bike,walking"
):
    """
    Computes complete all-island multimodal journey plans:
    * **5 Routing Objectives**: Shortest, Fastest, Cheapest, Slower, Scenic
    * **Multi-Modal Transport Modes**: Train, Bus, Car, Bike, Walking
    * **Selective Fare Calculation**: ONLY Bus and Train Have Ticket Fares (Car/Bike/Walk = 0 LKR)
    * **External Route API Benchmark**: Live OpenRouteService driving distance & geometry validation
    * **Unified Environmental Risk Assessment**: Real-time NBRO Landslide + Weather API
    * **Sri Lanka Railways 1st, 2nd, and 3rd Class Fares & NTC Regulated Bus Fares**
    * **Live Groq AI Fare Audit Verification (`openai/gpt-oss-20b`)**
    * **Decoupled Railway vs. Bus Scenic Scores** & Landmark Highlights
    """
    try:
        req_start = (payload.start or payload.origin) if payload else None
        req_end = (payload.end or payload.destination) if payload else None
        eff_start = req_start or start or "Colombo"
        eff_end = req_end or end or "Badulla"
        eff_start_name = (payload.start_name if payload else None) or start_name
        eff_end_name = (payload.end_name if payload else None) or end_name
        raw_modes = (payload.modes if payload and payload.modes else modes) or "train,bus,car,bike,walking"

        # Parse selected transport modes
        selected_modes = {m.strip().lower() for m in raw_modes.split(",") if m.strip()}
        allow_train = ("train" in selected_modes or "rail" in selected_modes)
        allow_bus = ("bus" in selected_modes)
        allow_car = ("car" in selected_modes or "road" in selected_modes or "driving" in selected_modes)
        allow_bike = ("bike" in selected_modes or "cycling" in selected_modes)
        allow_walk = ("walking" in selected_modes or "walk" in selected_modes)

        # Build allowed modes set for DijkstraRouter
        dijkstra_allowed = set()
        if allow_train:
            dijkstra_allowed.update(["rail", "train"])
        if allow_bus:
            dijkstra_allowed.update(["bus"])
        if allow_walk:
            dijkstra_allowed.update(["walking", "transfer"])
        if allow_car:
            dijkstra_allowed.update(["car", "road"])
        if allow_bike:
            dijkstra_allowed.update(["bike"])

        # Critical: In multimodal transit networks, walking transfers and station access links
        # MUST be allowed if public transit (train or bus) is active, otherwise travelers cannot board.
        if allow_train or allow_bus:
            dijkstra_allowed.update(["walking", "transfer"])

        start_lat, start_lon, parsed_start_label = parse_location(eff_start)
        end_lat, end_lon, parsed_end_label = parse_location(eff_end)
        start_label = eff_start_name if eff_start_name and not eff_start_name.startswith("(") else parsed_start_label
        end_label = eff_end_name if eff_end_name and not eff_end_name.startswith("(") else parsed_end_label
        direct_dist = haversine_km(start_lat, start_lon, end_lat, end_lon)

        # 1. External Route API (OpenRouteService) driving benchmark (cached in-memory for fast mode switching)
        b_key = (round(start_lat, 3), round(start_lon, 3), round(end_lat, 3), round(end_lon, 3))
        if b_key in _SWAGGER_ROAD_BENCHMARK_CACHE:
            car_api_res = _SWAGGER_ROAD_BENCHMARK_CACHE[b_key]
        else:
            route_val_service = RouteValidationService()
            approx_road_km = round(direct_dist * 1.18, 2)
            approx_road_duration_s = (approx_road_km / 50.0) * 3600.0
            car_api_res = await route_val_service.validate_route(
                RouteRequest(
                    origin=Coordinate(latitude=start_lat, longitude=start_lon),
                    destination=Coordinate(latitude=end_lat, longitude=end_lon)
                ),
                local_distance_km=approx_road_km,
                local_duration=approx_road_duration_s
            )
            _SWAGGER_ROAD_BENCHMARK_CACHE[b_key] = car_api_res

        driving_distance_km = round(car_api_res.distance, 2) if car_api_res.distance else approx_road_km
        driving_duration_min = round(car_api_res.duration / 60.0, 1) if car_api_res.duration else round((driving_distance_km / 50.0) * 60.0, 1)
        h_drive = int(driving_duration_min // 60)
        m_drive = int(driving_duration_min % 60)

        graph = get_graph()

        # Purge any virtual nodes from previous queries
        for v in ["origin_point", "destination_point"]:
            if v in graph.nodes:
                del graph.nodes[v]
            if v in graph.edges:
                del graph.edges[v]
            for u in list(graph.edges.keys()):
                if v in graph.edges[u]:
                    del graph.edges[u][v]

        s_nodes = find_transit_access(start_lat, start_lon, graph)
        e_nodes = find_transit_access(end_lat, end_lon, graph)

        v_start = "origin_point"
        v_end = "destination_point"

        graph.add_node(Node(v_start, lat=start_lat, lon=start_lon, properties={"name": start_label, "label": start_label}))
        graph.add_node(Node(v_end, lat=end_lat, lon=end_lon, properties={"name": end_label, "label": end_label}))

        # Add private/direct edges based on mode selection:
        # Car Driving edge: Ticket fare is strictly 0.0 LKR (private vehicle)
        if allow_car:
            graph.add_edge(Edge(v_start, v_end, GraphMode.CAR, True, {
                "distance_km": driving_distance_km,
                "travel_time_min": driving_duration_min,
                "cost_lkr": 0.0,  # Zero ticket fare for car
                "route_no": "Car Driving Route",
                "via": f"Road Network ({car_api_res.source})"
            }))
            graph.add_edge(Edge(v_end, v_start, GraphMode.CAR, True, {
                "distance_km": driving_distance_km,
                "travel_time_min": driving_duration_min,
                "cost_lkr": 0.0,
                "route_no": "Car Driving Route",
                "via": f"Road Network ({car_api_res.source})"
            }))

        # Bicycle edge: Ticket fare is strictly 0.0 LKR (personal cycling)
        if allow_bike:
            bike_km = round(direct_dist * 1.08, 2)
            bike_duration_min = round((bike_km / 16.0) * 60.0, 1)
            graph.add_edge(Edge(v_start, v_end, GraphMode.BIKE, True, {
                "distance_km": bike_km,
                "travel_time_min": bike_duration_min,
                "cost_lkr": 0.0,  # Zero ticket fare for bike
                "route_no": "Bicycle Route",
                "via": "Cycling Road Network"
            }))
            graph.add_edge(Edge(v_end, v_start, GraphMode.BIKE, True, {
                "distance_km": bike_km,
                "travel_time_min": bike_duration_min,
                "cost_lkr": 0.0,
                "route_no": "Bicycle Route",
                "via": "Cycling Road Network"
            }))

        # Pure walking edge: Ticket fare is strictly 0.0 LKR.
        # Only add a direct walking edge across the entire trip if the trip is short (<= 5.0 km)
        # or if walking is the ONLY selected transport mode!
        is_walk_only = allow_walk and not (allow_train or allow_bus or allow_car or allow_bike)
        if allow_walk and (direct_dist <= 5.0 or is_walk_only):
            walk_km = round(direct_dist * 1.05, 2)
            walk_duration_min = round((walk_km / 4.5) * 60.0, 1)
            graph.add_edge(Edge(v_start, v_end, GraphMode.WALKING, True, {
                "distance_km": walk_km,
                "travel_time_min": walk_duration_min,
                "cost_lkr": 0.0,  # Zero ticket fare for walking
                "route_no": "Pedestrian Path",
                "via": "Direct Walking Trail"
            }))
            graph.add_edge(Edge(v_end, v_start, GraphMode.WALKING, True, {
                "distance_km": walk_km,
                "travel_time_min": walk_duration_min,
                "cost_lkr": 0.0,
                "route_no": "Pedestrian Path",
                "via": "Direct Walking Trail"
            }))

        # Add walking links to public transit access nodes if public transit is enabled
        if allow_train:
            s_rail, s_rail_d = s_nodes["rail"]
            e_rail, e_rail_d = e_nodes["rail"]
            if s_rail and s_rail_d <= 35.0:
                graph.add_edge(Edge(v_start, s_rail, GraphMode.WALKING, True, {"distance_km": s_rail_d, "travel_time_min": (s_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(s_rail, v_start, GraphMode.WALKING, True, {"distance_km": s_rail_d, "travel_time_min": (s_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))
            if e_rail and e_rail_d <= 35.0:
                graph.add_edge(Edge(e_rail, v_end, GraphMode.WALKING, True, {"distance_km": e_rail_d, "travel_time_min": (e_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, e_rail, GraphMode.WALKING, True, {"distance_km": e_rail_d, "travel_time_min": (e_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))

        if allow_bus:
            s_bus, s_bus_d = s_nodes["bus"]
            e_bus, e_bus_d = e_nodes["bus"]
            if s_bus and s_bus_d <= 35.0:
                graph.add_edge(Edge(v_start, s_bus, GraphMode.WALKING, True, {"distance_km": s_bus_d, "travel_time_min": (s_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(s_bus, v_start, GraphMode.WALKING, True, {"distance_km": s_bus_d, "travel_time_min": (s_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))
            if e_bus and e_bus_d <= 35.0:
                graph.add_edge(Edge(e_bus, v_end, GraphMode.WALKING, True, {"distance_km": e_bus_d, "travel_time_min": (e_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, e_bus, GraphMode.WALKING, True, {"distance_km": e_bus_d, "travel_time_min": (e_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))

            # Safety fallback for bus transit
            best_s_bus, best_s_dist = s_nodes["bus"]
            if best_s_bus and (v_start not in graph.edges or not graph.edges[v_start]):
                graph.add_edge(Edge(v_start, best_s_bus, GraphMode.WALKING, True, {"distance_km": best_s_dist, "travel_time_min": (best_s_dist / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(best_s_bus, v_start, GraphMode.WALKING, True, {"distance_km": best_s_dist, "travel_time_min": (best_s_dist / 4.5) * 60.0, "cost_lkr": 0.0}))

            best_e_bus, best_e_dist = e_nodes["bus"]
            if best_e_bus and (v_end not in graph.edges or not graph.edges[v_end]):
                graph.add_edge(Edge(best_e_bus, v_end, GraphMode.WALKING, True, {"distance_km": best_e_dist, "travel_time_min": (best_e_dist / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, best_e_bus, GraphMode.WALKING, True, {"distance_km": best_e_dist, "travel_time_min": (best_e_dist / 4.5) * 60.0, "cost_lkr": 0.0}))

        rail_s, rail_s_dist = s_nodes["rail"]
        rail_e, rail_e_dist = e_nodes["rail"]
        bus_s, bus_s_dist = s_nodes["bus"]
        bus_e, bus_e_dist = e_nodes["bus"]

        objectives = ["shortest", "fastest", "cheapest", "slower", "scenic"]
        objectives_comparison = {}
        scenic_results = {}

        for obj in objectives:
            router = DijkstraRouter(graph, objective=obj, allowed_modes=dijkstra_allowed)
            try:
                res = router.route(v_start, v_end)
                if res:
                    coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    coords = enrich_corridor_coords(coords, graph)
                    scenic_info = scenic_service.calculate_scenic_score(coords, res.total_distance_km, corridor_radius_km=7.5, objective=obj)
                    scenic_results[obj] = scenic_info
                    h = int(res.total_travel_time_min // 60) if res.total_travel_time_min else 0
                    m = int(res.total_travel_time_min % 60) if res.total_travel_time_min else 0

                    # Calibrated Fare Calculation Rule: ONLY Bus and Train Have Fares!
                    # For Rail: calculate official SLR tariff for total rail track distance
                    total_rail_km = sum(
                        float(e.attributes.get("distance_km") or 0.0)
                        for e in res.edges
                        if (e.mode.value if hasattr(e.mode, "value") else str(e.mode)).lower() == "rail"
                    )
                    rail_ticket_fare = 0.0
                    if total_rail_km > 0.0:
                        rf = rail_graph_loader.lookup_distance_tariff(total_rail_km)
                        rail_ticket_fare = rf["3rd_class_rs"]

                    legs_data = []
                    total_journey_fare = 0.0
                    modes_present = set()

                    for e in res.edges:
                        m_str = (e.mode.value if hasattr(e.mode, "value") else str(e.mode)).lower()
                        leg_dist = float(e.attributes.get("distance_km") or 0.0)
                        leg_time = float(e.attributes.get("travel_time_min") or 0.0)
                        r_no = e.attributes.get("route_no", "")
                        line = e.attributes.get("line_name", "") or e.attributes.get("line", "")
                        via = e.attributes.get("via", "")
                        lbl = r_no or line
                        if via:
                            lbl += f" (via {via})"
                        fn = graph.get_node(e.from_node)
                        tn = graph.get_node(e.to_node)
                        fn_name = fn.properties.get("name", e.from_node) if fn else e.from_node
                        tn_name = tn.properties.get("name", e.to_node) if tn else e.to_node

                        # Clean human-friendly waypoint names for virtual terminal nodes
                        if e.from_node in ("origin_point", v_start) or fn_name == "origin_point":
                            fn_name = f"{start_label} (Start Point)"
                        if e.to_node in ("destination_point", v_end) or tn_name == "destination_point":
                            tn_name = f"{end_label} (Destination)"
                        if fn_name == "destination_point":
                            fn_name = f"{end_label} (Destination)"
                        if tn_name == "origin_point":
                            tn_name = f"{start_label} (Start Point)"

                        from_c = [fn.lat, fn.lon] if (fn and fn.lat is not None and fn.lon is not None) else [start_lat, start_lon]
                        to_c = [tn.lat, tn.lon] if (tn and tn.lat is not None and tn.lon is not None) else [end_lat, end_lon]
                        if e.from_node in ("origin_point", v_start):
                            from_c = [start_lat, start_lon]
                        if e.to_node in ("destination_point", v_end):
                            to_c = [end_lat, end_lon]

                        # Calibrated Fare Assignment: ONLY rail and bus get ticket fares!
                        leg_fare = 0.0
                        display_mode = e.mode.value if hasattr(e.mode, "value") else str(e.mode)

                        if m_str == "rail":
                            leg_fare = round((leg_dist / max(1.0, total_rail_km)) * rail_ticket_fare, 2) if total_rail_km > 0 else 0.0
                            modes_present.add("Train")
                            display_mode = "rail"
                        elif m_str == "bus":
                            leg_fare = float(e.attributes.get("cost_lkr") or max(35.0, round(leg_dist * 2.25, 2)))
                            modes_present.add("Bus")
                            display_mode = "bus"
                        elif m_str in ("road", "car"):
                            leg_fare = 0.0  # Private Car: Free
                            if "bike" in lbl.lower() or "bicycle" in via.lower():
                                modes_present.add("Bike")
                                display_mode = "bike"
                            else:
                                modes_present.add("Car")
                                display_mode = "car"
                        elif m_str == "bike":
                            leg_fare = 0.0  # Private Bike: Free
                            modes_present.add("Bike")
                            display_mode = "bike"
                        elif m_str in ("walking", "transfer"):
                            leg_fare = 0.0  # Walking: Free
                            display_mode = "walking"
                            if len(res.edges) == 1:
                                modes_present.add("Walking")

                        total_journey_fare += leg_fare

                        # Provide rich corridor polyline coordinates for map drawing
                        leg_coords = [from_c, to_c]
                        if m_str in ("road", "car", "bike") and leg_dist > 10.0:
                            leg_coords = enrich_corridor_coords([from_c, to_c], graph)

                        legs_data.append({
                            "from_node": e.from_node,
                            "to_node": e.to_node,
                            "from_name": fn_name,
                            "to_name": tn_name,
                            "mode": display_mode,
                            "distance_km": round(leg_dist, 2),
                            "travel_time_min": round(leg_time, 1),
                            "fare_lkr": round(leg_fare, 2),
                            "label": lbl,
                            "from_coord": from_c,
                            "to_coord": to_c,
                            "coords": leg_coords
                        })

                    # If only private transport (car, bike, walking) is used, fare is strictly 0.0 LKR
                    if not any(m in ("Train", "Bus") for m in modes_present):
                        total_journey_fare = 0.0
                    else:
                        total_journey_fare = round(total_journey_fare, 2)

                    obj_env = environmental_risk_service.assess_route(coords, route_id=f"objective_{obj}")
                    objectives_comparison[obj] = {
                        "distance_km": round(res.total_distance_km, 2),
                        "travel_time_min": round(res.total_travel_time_min, 1) if res.total_travel_time_min else 0,
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "fare_cost_lkr": total_journey_fare,
                        "modes": sorted(list(modes_present)) or ["Walking"],
                        "transfers": res.transfers_count,
                        "scenic_score": scenic_info["scenic_score"],
                        "scenic_rating": scenic_info["scenic_rating"],
                        "environmental_status": obj_env.status,
                        "environmental_assessment": obj_env.to_dict(),
                        "coordinates": coords,
                        "legs": legs_data,
                        "scenic_places": scenic_info.get("scenic_places", [])[:15]
                    }
                else:
                    objectives_comparison[obj] = None
            except Exception:
                objectives_comparison[obj] = None

        # Dedicated Railway Option (Available only if allow_train and track exists)
        rail_option = None
        rail_scenic = None
        if allow_train and rail_s and rail_e and rail_s != rail_e and rail_s_dist <= 35.0 and rail_e_dist <= 35.0:
            try:
                res_rail = DijkstraRouter(graph, objective="fastest", allowed_modes=["rail"]).route(rail_s, rail_e)
                if res_rail:
                    s_name = graph.get_node(rail_s).properties.get("name", rail_s)
                    e_name = graph.get_node(rail_e).properties.get("name", rail_e)
                    rail_fare = rail_graph_loader.lookup_distance_tariff(res_rail.total_distance_km)
                    direct_fare = rail_graph_loader.get_fare(s_name, e_name)
                    if direct_fare and abs(direct_fare.get("distance_km", 0) - res_rail.total_distance_km) < 15.0 and direct_fare.get("3rd_class_rs", 0) > 0:
                        rail_fare = direct_fare
                    r_coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res_rail.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    rail_scenic = scenic_service.calculate_scenic_score(r_coords, res_rail.total_distance_km, corridor_radius_km=6.0, objective="rail")
                    h = int(res_rail.total_travel_time_min // 60)
                    m = int(res_rail.total_travel_time_min % 60)
                    rail_option = {
                        "available": True,
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

        # Dedicated Bus Option (Available only if allow_bus)
        bus_option = None
        bus_scenic = None
        if allow_bus and bus_s and bus_e and bus_s != bus_e:
            try:
                res_bus = DijkstraRouter(graph, objective="fastest", allowed_modes=["bus"]).route(bus_s, bus_e)
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
                    bus_fare_val = res_bus.total_cost_lkr if (res_bus.total_cost_lkr and res_bus.total_cost_lkr > 0) else max(30.0, round(res_bus.total_distance_km * 2.20, 2))
                    road_km = round(res_bus.total_distance_km, 2)
                    travel_time_m = res_bus.total_travel_time_min or (road_km / 40.0) * 60.0

                    if direct_dist >= 20.0 and road_km > direct_dist * 2.2:
                        road_km = round(direct_dist * 1.25, 2)
                        travel_time_m = (road_km / 42.0) * 60.0
                        bus_fare_val = max(40.0, round(road_km * 2.25, 2))
                        bus_name = "Inter-Provincial Highway Stage Service"

                    h = int(travel_time_m // 60)
                    m = int(travel_time_m % 60)
                    bus_option = {
                        "available": True,
                        "service_route": bus_name,
                        "road_distance_km": road_km,
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "scenic_score": bus_scenic["scenic_score"] if bus_scenic else 65,
                        "regulated_fare_lkr": round(bus_fare_val, 2),
                        "fare_lkr": round(bus_fare_val, 2)
                    }
            except Exception:
                pass

        if allow_bus and not bus_option and direct_dist > 1.0:
            road_km = round(direct_dist * 1.25, 2)
            travel_time_m = (road_km / 40.0) * 60.0
            h = int(travel_time_m // 60)
            m = int(travel_time_m % 60)
            bus_fare_val = max(35.0, round(road_km * 2.25, 2))
            bus_option = {
                "available": True,
                "service_route": "National Regulated Highway Stage Service",
                "road_distance_km": road_km,
                "travel_time_formatted": f"{h}h {m:02d}m",
                "scenic_score": 65,
                "regulated_fare_lkr": bus_fare_val,
                "fare_lkr": bus_fare_val
            }

        # Dedicated Private Car Option (Route API / ORS benchmark)
        car_option = {
            "available": allow_car,
            "service_type": "Private Car Driving",
            "distance_km": driving_distance_km,
            "travel_time_formatted": f"{h_drive}h {m_drive:02d}m",
            "travel_time_min": driving_duration_min,
            "ticket_fare_lkr": 0.0,
            "fare_note": "Free / Private Vehicle (No Public Ticket)",
            "route_api_source": car_api_res.source,
            "fuel_estimate_lkr": round((driving_distance_km / 12.0) * 370.0, 2)
        }

        # Dedicated Bike Option
        bike_dist = round(direct_dist * 1.08, 2)
        bike_min = round((bike_dist / 16.0) * 60.0, 1)
        bike_option = {
            "available": allow_bike,
            "service_type": "Bicycle / Cycling Route",
            "distance_km": bike_dist,
            "travel_time_formatted": f"{int(bike_min // 60)}h {int(bike_min % 60):02d}m",
            "travel_time_min": bike_min,
            "ticket_fare_lkr": 0.0,
            "fare_note": "Free / Personal Cycling"
        }

        # Dedicated Walking Option
        walk_dist = round(direct_dist * 1.05, 2)
        walk_min = round((walk_dist / 4.5) * 60.0, 1)
        walking_option = {
            "available": allow_walk,
            "service_type": "Pedestrian Walking",
            "distance_km": walk_dist,
            "travel_time_formatted": f"{int(walk_min // 60)}h {int(walk_min % 60):02d}m",
            "travel_time_min": walk_min,
            "ticket_fare_lkr": 0.0,
            "fare_note": "Free / Pedestrian Path"
        }

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

        # Unified Environmental Risk Assessment along primary route corridor
        primary_coords = (
            objectives_comparison.get("fastest", {}).get("coordinates")
            if objectives_comparison.get("fastest") else None
        ) or (
            objectives_comparison.get("shortest", {}).get("coordinates")
            if objectives_comparison.get("shortest") else None
        ) or [(start_lat, start_lon), (end_lat, end_lon)]

        top_env = environmental_risk_service.assess_route(primary_coords, route_id=f"{start_label}->{end_label}")

        response_payload = {
            "origin": {"name": start_label, "lat": start_lat, "lon": start_lon},
            "destination": {"name": end_label, "lat": end_lat, "lon": end_lon},
            "haversine_distance_km": round(direct_dist, 2),
            "selected_modes": list(selected_modes),
            "environmental_assessment": top_env.to_dict(),
            "objectives_comparison": objectives_comparison,
            "railway_option": rail_option if allow_train else {"available": False, "note": "Train mode deselected by user"},
            "bus_option": bus_option if allow_bus else {"available": False, "note": "Bus mode deselected by user"},
            "car_option": car_option,
            "bike_option": bike_option,
            "walking_option": walking_option,
            "route_api_benchmark": {
                "source": car_api_res.source,
                "distance_km": car_api_res.distance,
                "duration_seconds": car_api_res.duration,
                "duration_formatted": f"{h_drive}h {m_drive:02d}m",
                "api_endpoint": "https://api.openrouteservice.org/v2/directions/driving-car",
                "status": "active_verified" if car_api_res.source == "route_api" else "fallback_active"
            },
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
        return response_payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            for v in ["origin_point", "destination_point"]:
                if v in graph.nodes:
                    del graph.nodes[v]
                if v in graph.edges:
                    del graph.edges[v]
                for u in list(graph.edges.keys()):
                    if v in graph.edges[u]:
                        del graph.edges[u][v]
        except Exception:
            pass

class EnvironmentalRiskRequest(BaseModel):
    coordinates: Optional[List[List[float]]] = Field(None, description="List of [latitude, longitude] pairs along route")
    origin_name: Optional[str] = None
    destination_name: Optional[str] = None
    buffer_meters: float = Field(default=1000.0, ge=100.0, le=5000.0)

@app.post("/api/routes/environmental-risk", tags=["Environmental Risk"])
async def evaluate_environmental_risk(payload: EnvironmentalRiskRequest):
    """
    Evaluates unified environmental risk (NBRO Landslide Data + OpenWeatherMap API + DMC Status)
    along a proposed route trajectory.
    """
    coords: List[Tuple[float, float]] = []
    if payload.coordinates:
        coords = [(c[0], c[1]) for c in payload.coordinates if len(c) >= 2]
    elif payload.origin_name and payload.destination_name:
        s_lat, s_lon, _ = parse_location(payload.origin_name)
        e_lat, e_lon, _ = parse_location(payload.destination_name)
        coords = [(s_lat, s_lon), (e_lat, e_lon)]
    else:
        raise HTTPException(status_code=400, detail="Either coordinates or origin_name + destination_name must be provided.")

    assessment = environmental_risk_service.assess_route(coords, landslide_buffer_m=payload.buffer_meters)
    return assessment.to_dict()

static_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html")

@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def serve_frontend():
    """Serves the single-file Component 2 Frontend UI directly at the root URL."""
    if os.path.exists(static_file_path):
        return FileResponse(static_file_path)
    return HTMLResponse("<h2>WANDARAYA Component 2 Engine Active. Access <a href='/docs'>/docs</a></h2>")

@app.get("/api/routes/geocode", tags=["Component 2 - High Level Plan"])
async def search_locations(q: str = ""):
    """Fast location autocomplete endpoint for Sri Lanka places, stations, and landmarks."""
    query = q.strip().lower()
    if not query:
        return {"results": []}

    results = []
    # 1. Check popular locations
    for name, coords in POPULAR_LOCATIONS.items():
        if query in name:
            results.append({"name": name.title(), "lat": coords[0], "lon": coords[1], "type": "Famous Destination"})

    # 2. Railway stations
    from app.services.rail_graph_loader import rail_graph_loader
    for k, v in rail_graph_loader.station_coords.items():
        if query in k and len(results) < 20:
            st_name = k.title() + " Station"
            if not any(r["name"].lower() == st_name.lower() for r in results):
                results.append({"name": st_name, "lat": v[0], "lon": v[1], "type": "Railway Station"})

    # 3. Query IslandGeocoder gazetteer
    try:
        from app.services.island_geocoder import geocoder
        for k, v in geocoder._gazetteer.items():
            if query in k and len(results) < 25:
                if not any(r["name"].lower() == v[2].lower() for r in results):
                    results.append({"name": v[2], "lat": v[0], "lon": v[1], "type": v[3].replace("_", " ").title()})
    except Exception:
        pass

    return {"results": results[:15]}

@app.get("/api/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "service": "WANDARAYA Component 2 Multimodal Engine",
        "docs": "/docs"
    }

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  LAUNCHING WANDARAYA COMPONENT 2 SWAGGER UI SERVER")
    print("=" * 70)
    print("  [*] Swagger Documentation : http://127.0.0.1:8000/docs")
    print("  [*] ReDoc Documentation   : http://127.0.0.1:8000/redoc")
    print("=" * 70 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
