import pytest
import math
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import routes
from app.routers.routes import get_multimodal_graph
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import (
    DijkstraRouter,
    DistanceCostModel,
    CostCostModel,
    TimeCostModel,
    DijkstraPathResult
)

# ---------------------------------------------------------------------------
# Test A — Shortest route
# ---------------------------------------------------------------------------
def test_a_shortest_route():
    """
    Test A: Construct a graph in which the shortest-distance path is different from alternatives.
    - Path 1 (Direct Road): 10.0 km, time 30 min, cost 200 LKR
    - Path 2 (Detour Highway): 18.0 km, time 15 min, cost 500 LKR
    Under objective='shortest' (or 'distance'), Path 1 MUST be selected.
    """
    g = MultimodalGraph()
    for n in ["A_start", "A_mid1", "A_mid2", "A_end"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Path 1: 10 km
    g.add_edge(Edge("A_start", "A_mid1", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 15.0, "cost_lkr": 100.0}))
    g.add_edge(Edge("A_mid1", "A_end", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 15.0, "cost_lkr": 100.0}))

    # Path 2: 18 km
    g.add_edge(Edge("A_start", "A_mid2", GraphMode.ROAD, directed=True, attributes={"distance_km": 9.0, "travel_time_min": 7.5, "cost_lkr": 250.0}))
    g.add_edge(Edge("A_mid2", "A_end", GraphMode.ROAD, directed=True, attributes={"distance_km": 9.0, "travel_time_min": 7.5, "cost_lkr": 250.0}))

    router = DijkstraRouter(g, objective="shortest")
    res = router.route("A_start", "A_end")

    assert res.nodes == ["A_start", "A_mid1", "A_end"]
    assert res.total_distance_km == 10.0
    assert res.optimized_weight == 10.0
    assert res.total_travel_time_min == 30.0
    assert res.total_cost_lkr == 200.0

# ---------------------------------------------------------------------------
# Test B — Fastest route
# ---------------------------------------------------------------------------
def test_b_fastest_route():
    """
    Test B: Construct a graph with valid travel times where a longer route is faster.
    - Path 1 (Local road): 10.0 km, travel_time 40.0 min
    - Path 2 (Expressway): 16.0 km, travel_time 15.0 min
    Under objective='fastest' (or 'time'), Path 2 MUST be selected.
    """
    g = MultimodalGraph()
    for n in ["B_start", "B_local", "B_express", "B_end"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Path 1: Local Road (10 km, 40 min)
    g.add_edge(Edge("B_start", "B_local", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 20.0, "cost_lkr": 50.0}))
    g.add_edge(Edge("B_local", "B_end", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 20.0, "cost_lkr": 50.0}))

    # Path 2: Expressway (16 km, 15 min)
    g.add_edge(Edge("B_start", "B_express", GraphMode.ROAD, directed=True, attributes={"distance_km": 8.0, "travel_time_min": 7.5, "cost_lkr": 300.0}))
    g.add_edge(Edge("B_express", "B_end", GraphMode.ROAD, directed=True, attributes={"distance_km": 8.0, "travel_time_min": 7.5, "cost_lkr": 300.0}))

    router = DijkstraRouter(g, objective="fastest")
    res = router.route("B_start", "B_end")

    assert res.nodes == ["B_start", "B_express", "B_end"]
    assert res.total_distance_km == 16.0
    assert res.total_travel_time_min == 15.0
    assert res.optimized_weight == 15.0
    assert any("timetable" in w.lower() for w in res.warnings)

# ---------------------------------------------------------------------------
# Test C — Cheapest route
# ---------------------------------------------------------------------------
def test_c_cheapest_route():
    """
    Test C: Construct a graph with valid fares where the shortest route costs more than an alternative.
    - Path 1 (Taxi/Toll): 8.0 km, fare 600 LKR
    - Path 2 (Public Bus): 14.0 km, fare 120 LKR
    Under objective='cheapest' (or 'cost'), Path 2 MUST be selected.
    """
    g = MultimodalGraph()
    for n in ["C_start", "C_taxi", "C_bus", "C_end"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Path 1 (Taxi/Toll)
    g.add_edge(Edge("C_start", "C_taxi", GraphMode.ROAD, directed=True, attributes={"distance_km": 4.0, "cost_lkr": 300.0, "travel_time_min": 10.0}))
    g.add_edge(Edge("C_taxi", "C_end", GraphMode.ROAD, directed=True, attributes={"distance_km": 4.0, "cost_lkr": 300.0, "travel_time_min": 10.0}))

    # Path 2 (Bus)
    g.add_edge(Edge("C_start", "C_bus", GraphMode.BUS, directed=True, attributes={"distance_km": 7.0, "cost_lkr": 60.0, "travel_time_min": 25.0}))
    g.add_edge(Edge("C_bus", "C_end", GraphMode.BUS, directed=True, attributes={"distance_km": 7.0, "cost_lkr": 60.0, "travel_time_min": 25.0}))

    router = DijkstraRouter(g, objective="cheapest")
    res = router.route("C_start", "C_end")

    assert res.nodes == ["C_start", "C_bus", "C_end"]
    assert res.total_distance_km == 14.0
    assert res.total_cost_lkr == 120.0
    assert res.optimized_weight == 120.0
    assert res.cost_complete is True

# ---------------------------------------------------------------------------
# Test D — Multimodal route
# ---------------------------------------------------------------------------
def test_d_multimodal_route():
    """
    Test D: Connected Bus -> Walking -> Rail path.
    Verify that each segment's mode, distance, cost and time are correct.
    """
    g = MultimodalGraph()
    for n in ["D_origin", "D_bus_stop", "D_station", "D_dest"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Segment 1: Bus (3.0 km, 50 LKR, 12 min)
    g.add_edge(Edge("D_origin", "D_bus_stop", GraphMode.BUS, directed=True, attributes={"distance_km": 3.0, "cost_lkr": 50.0, "travel_time_min": 12.0}))
    # Segment 2: Walking transfer (0.4 km, explicitly free 0.0 LKR, 6 min)
    g.add_edge(Edge("D_bus_stop", "D_station", GraphMode.WALKING, directed=True, attributes={"distance_km": 0.4, "cost_lkr": 0.0, "travel_time_min": 6.0, "transfer_type": "stop_to_station"}))
    # Segment 3: Rail (18.0 km, 160 LKR, 35 min)
    g.add_edge(Edge("D_station", "D_dest", GraphMode.RAIL, directed=True, attributes={"distance_km": 18.0, "cost_lkr": 160.0, "travel_time_min": 35.0}))

    router = DijkstraRouter(g, objective="shortest")
    res = router.route("D_origin", "D_dest")

    assert res.nodes == ["D_origin", "D_bus_stop", "D_station", "D_dest"]
    assert len(res.edges) == 3
    assert [e.mode.value for e in res.edges] == ["bus", "walking", "rail"]
    assert res.total_distance_km == 21.4
    assert res.total_cost_lkr == 210.0
    assert res.cost_complete is True
    assert res.total_travel_time_min == 53.0
    assert res.travel_time_complete is True
    assert res.mode_changes_count == 1  # bus -> rail across walking link

# ---------------------------------------------------------------------------
# Test E — Transfer calculation
# ---------------------------------------------------------------------------
def test_e_transfer_calculation():
    """
    Test E: Transfer counting and ensuring transfer time is not double-counted.
    Leg 1: Bus (travel_time: 20 min)
    Leg 2: Transfer link (travel_time: 0.0 min, transfer_time: 5.0 min)
    Leg 3: Rail (travel_time: 30 min)
    Expected:
    - total_travel_time_min: 50.0 min
    - total_transfer_time_min: 5.0 min
    - total_journey_time_min: 55.0 min (not 60.0 min)
    - transfers_count: 1
    """
    g = MultimodalGraph()
    for n in ["E1", "E2", "E3", "E4"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("E1", "E2", GraphMode.BUS, directed=True, attributes={"distance_km": 4.0, "travel_time_min": 20.0, "cost_lkr": 40.0}))
    g.add_edge(Edge("E2", "E3", GraphMode.TRANSFER, directed=True, attributes={"distance_km": 0.2, "travel_time_min": 0.0, "transfer_time_min": 5.0, "cost_lkr": 0.0, "transfer_type": "walk"}))
    g.add_edge(Edge("E3", "E4", GraphMode.RAIL, directed=True, attributes={"distance_km": 12.0, "travel_time_min": 30.0, "cost_lkr": 100.0}))

    router = DijkstraRouter(g, objective="fastest")
    res = router.route("E1", "E4")

    assert res.total_travel_time_min == 50.0
    assert res.total_transfer_time_min == 5.0
    assert res.total_journey_time_min == 55.0
    assert res.transfers_count == 1
    assert "E2" in res.transfer_locations or "E3" in res.transfer_locations

# ---------------------------------------------------------------------------
# Test F — Missing data
# ---------------------------------------------------------------------------
def test_f_missing_data():
    """
    Test F: Missing fare and missing travel time values.
    Confirm that the system does not invent values or claim complete totals.
    """
    g = MultimodalGraph()
    for n in ["F1", "F2", "F3"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("F1", "F2", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "cost_lkr": 50.0, "travel_time_min": 10.0}))
    # F2 -> F3 has distance, but missing fare and missing travel time
    g.add_edge(Edge("F2", "F3", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "cost_lkr": None, "travel_time_min": None}))

    # 1. Routing under distance succeeds (distance is known)
    router = DijkstraRouter(g, objective="shortest")
    res = router.route("F1", "F3")
    assert res.total_distance_km == 10.0
    assert res.total_cost_lkr is None
    assert res.cost_complete is False
    assert res.known_cost_lkr == 50.0
    assert res.total_travel_time_min is None
    assert res.travel_time_complete is False
    assert res.known_travel_time_min == 10.0
    assert any("Travel cost unavailable" in w for w in res.warnings)
    assert any("Travel time unavailable" in w for w in res.warnings)

    # 2. Routing under fastest or cheapest rejects edge because time/cost is missing
    fastest_router = DijkstraRouter(g, objective="fastest")
    with pytest.raises(ValueError, match="Destination is unreachable"):
        fastest_router.route("F1", "F3")

    cheapest_router = DijkstraRouter(g, objective="cheapest")
    with pytest.raises(ValueError, match="Destination is unreachable"):
        cheapest_router.route("F1", "F3")

# ---------------------------------------------------------------------------
# Test G — Unreachable destination
# ---------------------------------------------------------------------------
def test_g_unreachable_destination():
    """
    Test G: Unreachable destination reports clear error.
    """
    g = MultimodalGraph()
    g.add_node(Node("G_island_A", lat=6.0, lon=80.0))
    g.add_node(Node("G_island_B", lat=7.0, lon=81.0))

    router = DijkstraRouter(g, objective="shortest")
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("G_island_A", "G_island_B")

# ---------------------------------------------------------------------------
# Test H — Invalid weights
# ---------------------------------------------------------------------------
def test_h_invalid_weights():
    """
    Test H: Verify negative, NaN, infinite, or boolean weights are safely rejected.
    """
    g = MultimodalGraph()
    for n in ["H1", "H2", "H3"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Negative distance
    e_neg = Edge("H1", "H2", GraphMode.ROAD, directed=True, attributes={"distance_km": -5.0})
    assert DistanceCostModel.get_weight(e_neg) is None

    # NaN / Inf distance
    e_nan = Edge("H1", "H2", GraphMode.ROAD, directed=True, attributes={"distance_km": float("nan")})
    assert DistanceCostModel.get_weight(e_nan) is None
    e_inf = Edge("H1", "H2", GraphMode.ROAD, directed=True, attributes={"distance_km": float("inf")})
    assert DistanceCostModel.get_weight(e_inf) is None

    # Boolean value (in Python True == 1, but must not be treated as 1.0 km)
    e_bool = Edge("H1", "H2", GraphMode.ROAD, directed=True, attributes={"distance_km": True})
    assert DistanceCostModel.get_weight(e_bool) is None

    # Negative cost
    e_cost_neg = Edge("H1", "H2", GraphMode.BUS, directed=True, attributes={"cost_lkr": -20.0})
    assert CostCostModel.get_weight(e_cost_neg) is None

    # Negative time
    e_time_neg = Edge("H1", "H2", GraphMode.ROAD, directed=True, attributes={"travel_time_min": -15.0})
    assert TimeCostModel.get_weight(e_time_neg) is None

# ---------------------------------------------------------------------------
# Test I — Invalid objective
# ---------------------------------------------------------------------------
def test_i_invalid_objective():
    """
    Test I: Unsupported objective is rejected with a meaningful error.
    """
    g = MultimodalGraph()
    g.add_node(Node("I1", lat=6.9, lon=79.8))

    with pytest.raises(ValueError, match="Unsupported routing objective"):
        DijkstraRouter(g, objective="scenic")

    with pytest.raises(ValueError, match="Unsupported routing objective"):
        DijkstraRouter(g, objective="random_goal")

# ---------------------------------------------------------------------------
# Test J — End-to-end API
# ---------------------------------------------------------------------------
def test_j_end_to_end_api():
    """
    Test J: Send requests for all three objectives through the actual FastAPI test client.
    Verify returned path, response status, and metrics against independent calculations.
    """
    # Use isolated test app with routes.router
    g = MultimodalGraph()
    for n_id, (lat, lon) in [("api_A", (6.90, 79.85)), ("api_B", (6.92, 79.86)), ("api_C", (6.94, 79.87))]:
        g.add_node(Node(n_id, lat=lat, lon=lon))

    # Path 1: 5.0 km, 20 min, 100 LKR
    g.add_edge(Edge("api_A", "api_B", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 20.0, "cost_lkr": 100.0}))
    g.add_edge(Edge("api_B", "api_C", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 20.0, "cost_lkr": 100.0}))

    test_app = FastAPI()
    test_app.include_router(routes.router)
    test_app.dependency_overrides[get_multimodal_graph] = lambda: g
    client = TestClient(test_app)

    try:
        # 1. Objective: shortest
        req_shortest = {
            "origin_node_id": "api_A",
            "destination_node_id": "api_C",
            "objective": "shortest"
        }
        res_s = client.post("/routes/dijkstra", json=req_shortest)
        assert res_s.status_code == 200
        data_s = res_s.json()
        assert data_s["total_distance_km"] == 10.0
        assert data_s["objective"] == "shortest"
        assert data_s["nodes"] == ["api_A", "api_B", "api_C"]

        # 2. Objective: fastest
        req_fastest = {
            "origin_node_id": "api_A",
            "destination_node_id": "api_C",
            "objective": "fastest"
        }
        res_f = client.post("/routes/dijkstra", json=req_fastest)
        assert res_f.status_code == 200
        data_f = res_f.json()
        assert data_f["total_travel_time_min"] == 40.0
        assert data_f["objective"] == "fastest"

        # 3. Objective: cheapest
        req_cheapest = {
            "origin_node_id": "api_A",
            "destination_node_id": "api_C",
            "objective": "cheapest"
        }
        res_c = client.post("/routes/dijkstra", json=req_cheapest)
        assert res_c.status_code == 200
        data_c = res_c.json()
        assert data_c["total_cost_lkr"] == 200.0
        assert data_c["objective"] == "cheapest"

        # 4. Invalid objective
        req_invalid = {
            "origin_node_id": "api_A",
            "destination_node_id": "api_C",
            "objective": "unsupported_objective"
        }
        res_inv = client.post("/routes/dijkstra", json=req_invalid)
        assert res_inv.status_code == 422
    finally:
        test_app.dependency_overrides.clear()
