import pytest
import math
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import (
    DijkstraRouter,
    DistanceCostModel,
    CostCostModel,
    TimeCostModel,
    DijkstraPathResult
)
from app.services.route_metrics import RouteMetricsService

# ---------------------------------------------------------------------------
# Test 1: Route with two bus edges
# ---------------------------------------------------------------------------
def test_1_two_bus_edges():
    """
    Test 1: A route with two consecutive bus edges.
    Expected:
    - distance: 5.0 + 7.0 = 12.0 km
    - cost: 50.0 + 70.0 = 120.0 LKR (complete)
    - travel time: 15.0 + 20.0 = 35.0 min (complete)
    - mode changes: 0 (same mode)
    - transfers count: 0
    - modes used: ['bus']
    """
    g = MultimodalGraph()
    for n in ["A", "B", "C"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("A", "B", GraphMode.BUS, directed=True, attributes={"distance_km": 5.0, "cost_lkr": 50.0, "travel_time_min": 15.0}))
    g.add_edge(Edge("B", "C", GraphMode.BUS, directed=True, attributes={"distance_km": 7.0, "cost_lkr": 70.0, "travel_time_min": 20.0}))

    router = DijkstraRouter(g, objective="distance")
    result = router.route("A", "C")

    assert result.nodes == ["A", "B", "C"]
    assert result.total_distance_km == 12.0
    assert result.total_cost_lkr == 120.0
    assert result.cost_complete is True
    assert result.total_travel_time_min == 35.0
    assert result.travel_time_complete is True
    assert result.mode_changes_count == 0
    assert result.transfers_count == 0
    assert result.modes_used == ["bus"]

# ---------------------------------------------------------------------------
# Test 2: Bus-to-walking-to-train route
# ---------------------------------------------------------------------------
def test_2_bus_to_walking_to_train():
    """
    Test 2: Bus -> Walking -> Train.
    Example fixture data:
    - Bus: 4.0 km, 20 min, LKR 100
    - Walking: 0.5 km, 10 min, LKR 0.0 (explicitly free)
    - Train: 15.0 km, 40 min, LKR 150
    Expected:
    - distance: 4.0 + 0.5 + 15.0 = 19.5 km
    - cost: 100 + 0 + 150 = 250.0 LKR (complete)
    - travel time: 20 + 10 + 40 = 70.0 min (complete)
    - mode changes: 1 (bus to train across the walking link)
    - transfers count: 1 (walking transfer edge)
    - modes used: ['bus', 'walking', 'rail']
    """
    g = MultimodalGraph()
    for n in ["bus_stop_1", "bus_stop_2", "station_A", "station_B"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("bus_stop_1", "bus_stop_2", GraphMode.BUS, directed=True, attributes={"distance_km": 4.0, "cost_lkr": 100.0, "travel_time_min": 20.0}))
    g.add_edge(Edge("bus_stop_2", "station_A", GraphMode.WALKING, directed=True, attributes={"distance_km": 0.5, "cost_lkr": 0.0, "travel_time_min": 10.0, "transfer_type": "stop_to_station"}))
    g.add_edge(Edge("station_A", "station_B", GraphMode.RAIL, directed=True, attributes={"distance_km": 15.0, "cost_lkr": 150.0, "travel_time_min": 40.0}))

    router = DijkstraRouter(g, objective="distance")
    result = router.route("bus_stop_1", "station_B")

    assert result.nodes == ["bus_stop_1", "bus_stop_2", "station_A", "station_B"]
    assert result.total_distance_km == 19.5
    assert result.total_cost_lkr == 250.0
    assert result.cost_complete is True
    assert result.total_travel_time_min == 70.0
    assert result.travel_time_complete is True
    assert result.mode_changes_count == 1
    assert result.transfers_count == 1
    assert "bus_stop_2" in result.transfer_locations or "station_A" in result.transfer_locations

# ---------------------------------------------------------------------------
# Test 3: Two consecutive edges of the same mode
# ---------------------------------------------------------------------------
def test_3_two_consecutive_edges_same_mode():
    """
    Test 3: Consecutive road segments must NOT count as transfers or mode changes.
    Expected:
    - transfers_count: 0
    - mode_changes_count: 0
    - modes_used: ['road']
    """
    g = MultimodalGraph()
    for n in ["r1", "r2", "r3"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("r1", "r2", GraphMode.ROAD, directed=True, attributes={"distance_km": 2.5}))
    g.add_edge(Edge("r2", "r3", GraphMode.ROAD, directed=True, attributes={"distance_km": 3.5}))

    router = DijkstraRouter(g)
    result = router.route("r1", "r3")

    assert result.total_distance_km == 6.0
    assert result.transfers_count == 0
    assert result.mode_changes_count == 0
    assert result.modes_used == ["road"]

# ---------------------------------------------------------------------------
# Test 4: Multiple actual mode changes
# ---------------------------------------------------------------------------
def test_4_multiple_actual_mode_changes():
    """
    Test 4: Road -> Bus -> Rail.
    Expected:
    - mode sequence: ['road', 'bus', 'rail']
    - mode changes count: 2 (road->bus, bus->rail)
    - transfers count: 2
    """
    g = MultimodalGraph()
    for n in ["n1", "n2", "n3", "n4"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("n1", "n2", GraphMode.ROAD, directed=True, attributes={"distance_km": 1.0, "cost_lkr": 0.0, "travel_time_min": 3.0}))
    g.add_edge(Edge("n2", "n3", GraphMode.BUS, directed=True, attributes={"distance_km": 5.0, "cost_lkr": 50.0, "travel_time_min": 15.0}))
    g.add_edge(Edge("n3", "n4", GraphMode.RAIL, directed=True, attributes={"distance_km": 10.0, "cost_lkr": 100.0, "travel_time_min": 25.0}))

    router = DijkstraRouter(g)
    result = router.route("n1", "n4")

    assert result.mode_changes_count == 2
    assert result.transfers_count == 2
    assert result.modes_used == ["road", "bus", "rail"]
    assert result.total_distance_km == 16.0
    assert result.total_cost_lkr == 150.0

# ---------------------------------------------------------------------------
# Test 5: Route with a missing fare
# ---------------------------------------------------------------------------
def test_5_route_with_missing_fare():
    """
    Test 5: One edge has unknown fare.
    Expected:
    - total_cost_lkr is None (do not fabricate 0 or label partial sum as complete)
    - cost_complete is False
    - known_cost_lkr reports partial known sum
    - warning is emitted
    """
    g = MultimodalGraph()
    for n in ["s1", "s2", "s3"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("s1", "s2", GraphMode.BUS, directed=True, attributes={"distance_km": 4.0, "cost_lkr": 40.0}))
    g.add_edge(Edge("s2", "s3", GraphMode.BUS, directed=True, attributes={"distance_km": 6.0, "cost_lkr": None}))

    router = DijkstraRouter(g)
    result = router.route("s1", "s3")

    assert result.total_distance_km == 10.0
    assert result.total_cost_lkr is None
    assert result.cost_complete is False
    assert result.known_cost_lkr == 40.0
    assert any("Travel cost unavailable" in w for w in result.warnings)

# ---------------------------------------------------------------------------
# Test 6: Route with a missing travel-time attribute
# ---------------------------------------------------------------------------
def test_6_route_with_missing_travel_time():
    """
    Test 6: One edge has unknown travel_time_min.
    Expected:
    - total_travel_time_min is None (zero speed fabrication)
    - travel_time_complete is False
    - known_travel_time_min reports partial sum
    - warning is emitted
    """
    g = MultimodalGraph()
    for n in ["t1", "t2", "t3"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("t1", "t2", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 10.0}))
    g.add_edge(Edge("t2", "t3", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "travel_time_min": None}))

    router = DijkstraRouter(g)
    result = router.route("t1", "t3")

    assert result.total_distance_km == 10.0
    assert result.total_travel_time_min is None
    assert result.travel_time_complete is False
    assert result.known_travel_time_min == 10.0
    assert any("Travel time unavailable" in w for w in result.warnings)

# ---------------------------------------------------------------------------
# Test 7: Route with known journey and waiting times
# ---------------------------------------------------------------------------
def test_7_known_journey_and_waiting_times():
    """
    Test 7: Edge with known in-vehicle travel time and waiting time.
    Expected:
    - in-vehicle travel time: 60.0 min
    - waiting time: 15.0 min
    - total journey time: 60.0 + 15.0 = 75.0 min
    """
    g = MultimodalGraph()
    for n in ["dep", "arr"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("dep", "arr", GraphMode.RAIL, directed=True, attributes={
        "distance_km": 45.0,
        "travel_time_min": 60.0,
        "waiting_time_min": 15.0,
        "cost_lkr": 180.0
    }))

    router = DijkstraRouter(g)
    result = router.route("dep", "arr")

    assert result.total_travel_time_min == 60.0
    assert result.total_waiting_time_min == 15.0
    assert result.total_journey_time_min == 75.0
    assert result.journey_time_complete is True

# ---------------------------------------------------------------------------
# Test 8: Route where transfer time must not be counted twice
# ---------------------------------------------------------------------------
def test_8_transfer_time_not_double_counted():
    """
    Test 8: Distinct accounting of transfer time without double-counting.
    A transfer edge has transfer_time_min = 5.0 min.
    In-vehicle transit edges have 20.0 and 40.0 min.
    Expected:
    - total_travel_time_min: 20.0 + 40.0 = 60.0 min
    - total_transfer_time_min: 5.0 min
    - total_journey_time_min: 60.0 + 5.0 = 65.0 min (not 70.0)
    """
    g = MultimodalGraph()
    for n in ["orig", "stop_1", "station_1", "dest"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    g.add_edge(Edge("orig", "stop_1", GraphMode.BUS, directed=True, attributes={"distance_km": 5.0, "travel_time_min": 20.0, "cost_lkr": 50.0}))
    g.add_edge(Edge("stop_1", "station_1", GraphMode.TRANSFER, directed=True, attributes={"distance_km": 0.3, "travel_time_min": 0.0, "transfer_time_min": 5.0, "cost_lkr": 0.0, "transfer_type": "walk"}))
    g.add_edge(Edge("station_1", "dest", GraphMode.RAIL, directed=True, attributes={"distance_km": 15.0, "travel_time_min": 40.0, "cost_lkr": 120.0}))

    router = DijkstraRouter(g)
    result = router.route("orig", "dest")

    assert result.total_travel_time_min == 60.0
    assert result.total_transfer_time_min == 5.0
    assert result.total_journey_time_min == 65.0

# ---------------------------------------------------------------------------
# Test 9: Invalid transfer with no connecting graph edge
# ---------------------------------------------------------------------------
def test_9_invalid_transfer_no_connecting_edge():
    """
    Test 9: Modes that lack connecting transfer edges cannot route across the gap.
    """
    g = MultimodalGraph()
    # Bus network: B1 -> B2
    g.add_node(Node("B1", lat=6.9, lon=79.8))
    g.add_node(Node("B2", lat=6.9, lon=79.8))
    g.add_edge(Edge("B1", "B2", GraphMode.BUS, directed=True, attributes={"distance_km": 5.0}))

    # Rail network: R1 -> R2 (disconnected from bus network)
    g.add_node(Node("R1", lat=6.91, lon=79.81))
    g.add_node(Node("R2", lat=6.91, lon=79.81))
    g.add_edge(Edge("R1", "R2", GraphMode.RAIL, directed=True, attributes={"distance_km": 10.0}))

    router = DijkstraRouter(g)
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("B1", "R2")

# ---------------------------------------------------------------------------
# Test 10: Disconnected destination
# ---------------------------------------------------------------------------
def test_10_disconnected_destination():
    """
    Test 10: Destination in isolated component raises unreachable error.
    """
    g = MultimodalGraph()
    g.add_node(Node("isolated_A", lat=6.0, lon=80.0))
    g.add_node(Node("isolated_B", lat=7.0, lon=81.0))

    router = DijkstraRouter(g)
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("isolated_A", "isolated_B")

# ---------------------------------------------------------------------------
# Test 11: Cheapest path differs from shortest-distance path
# ---------------------------------------------------------------------------
def test_11_cheapest_differs_from_shortest_distance():
    """
    Test 11:
    Path 1 (Highway): 10.0 km, cost LKR 300
    Path 2 (Local):   15.0 km, cost LKR 100
    - Under objective="distance": Path 1 is chosen (10.0 km, 300 LKR)
    - Under objective="cost":     Path 2 is chosen (15.0 km, 100 LKR)
    """
    g = MultimodalGraph()
    for n in ["start", "mid_highway", "mid_local", "end"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Path 1 (Highway)
    g.add_edge(Edge("start", "mid_highway", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "cost_lkr": 150.0}))
    g.add_edge(Edge("mid_highway", "end", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0, "cost_lkr": 150.0}))

    # Path 2 (Local)
    g.add_edge(Edge("start", "mid_local", GraphMode.BUS, directed=True, attributes={"distance_km": 7.5, "cost_lkr": 50.0}))
    g.add_edge(Edge("mid_local", "end", GraphMode.BUS, directed=True, attributes={"distance_km": 7.5, "cost_lkr": 50.0}))

    # 1. Distance router
    dist_router = DijkstraRouter(g, objective="distance")
    dist_res = dist_router.route("start", "end")
    assert dist_res.nodes == ["start", "mid_highway", "end"]
    assert dist_res.total_distance_km == 10.0
    assert dist_res.total_cost_lkr == 300.0

    # 2. Cost router
    cost_router = DijkstraRouter(g, objective="cost")
    cost_res = cost_router.route("start", "end")
    assert cost_res.nodes == ["start", "mid_local", "end"]
    assert cost_res.total_distance_km == 15.0
    assert cost_res.total_cost_lkr == 100.0

# ---------------------------------------------------------------------------
# Test 12: Fastest path differs from cheapest path
# ---------------------------------------------------------------------------
def test_12_fastest_differs_from_cheapest():
    """
    Test 12:
    Path 1 (Express Rail): 50 min, LKR 500
    Path 2 (Slow Bus):     120 min, LKR 100
    - Under objective="time": Express Rail is chosen (50 min, LKR 500)
    - Under objective="cost": Slow Bus is chosen (120 min, LKR 100)
    """
    g = MultimodalGraph()
    for n in ["orig", "dest"]:
        g.add_node(Node(n, lat=6.9, lon=79.8))

    # Path 1: Express Rail
    g.add_edge(Edge("orig", "dest", GraphMode.RAIL, directed=True, attributes={
        "distance_km": 80.0,
        "travel_time_min": 50.0,
        "cost_lkr": 500.0
    }))

    # Path 2: Slow Bus
    g.add_edge(Edge("orig", "dest", GraphMode.BUS, directed=True, attributes={
        "distance_km": 80.0,
        "travel_time_min": 120.0,
        "cost_lkr": 100.0
    }))

    # 1. Time Router
    time_router = DijkstraRouter(g, objective="time")
    time_res = time_router.route("orig", "dest")
    assert time_res.total_travel_time_min == 50.0
    assert time_res.total_cost_lkr == 500.0
    assert time_res.edges[0].mode == GraphMode.RAIL

    # 2. Cost Router
    cost_router = DijkstraRouter(g, objective="cost")
    cost_res = cost_router.route("orig", "dest")
    assert cost_res.total_cost_lkr == 100.0
    assert cost_res.total_travel_time_min == 120.0
    assert cost_res.edges[0].mode == GraphMode.BUS
