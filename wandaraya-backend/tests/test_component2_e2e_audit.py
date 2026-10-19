"""
Comprehensive End-to-End Input and Output Verification Suite for WANDARAYA Component 2 (Steps 1–4).
Tests A through J covering:
- Test A: Valid route request (Colombo -> Kandy coordinates and snapped nodes)
- Test B: Another valid route (Galle -> Matara coordinates and snapped nodes)
- Test C: Same origin and destination (Colombo -> Colombo / node to same node)
- Test D: Invalid location (out of coverage coordinates / nonexistent node IDs)
- Test E: Unreachable destination (isolated components in controlled graph)
- Test F: Invalid request body (empty body, wrong data types, out of range coordinates)
- Test G: External API failure (timeout, HTTP 500, invalid auth on RouteAPIClient)
- Test H: Multimodal route (multi-mode path across walking, bus, rail, transfer)
- Test I: Dijkstra correctness on known graph (A->C->B->D = 4, unreachable, negative weights)
- Test J: Repeated requests (determinism and graph idempotency)
"""

import os
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "mock_key_for_unit_tests")

import math
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from app.routers import routes, route_validation
from app.routers.routes import get_multimodal_graph
from app.schemas.route import RouteRequest, Coordinate
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter, DistanceCostModel
from app.services.spatial import find_nearest_routable_node, haversine_km
from app.services.route_validation import RouteValidationService
from app.services.route_api_client import RouteAPIClient

test_app = FastAPI(title="WANDARAYA Component 2 Routing API")
test_app.include_router(routes.router)
test_app.include_router(route_validation.router, prefix="/api")


# =====================================================================
# Fixtures: Standard Multi-mode and Known Graph Fixtures
# =====================================================================

@pytest.fixture
def multimodal_audit_graph():
    """
    Standard multimodal fixture with Sri Lanka geographic nodes and known edges:
    - Colombo Fort Station (rail) (6.9344, 79.8428)
    - Pettah Central Bus Stand (bus) (6.9360, 79.8500)
    - Maradana Station (rail) (6.9271, 79.8612)
    - Colombo Fort Road Node (road) (6.9345, 79.8430)
    - Kandy Station (rail) (7.2906, 80.6337)
    - Kandy Bus Stand (bus) (7.2920, 80.6350)
    - Kandy Road Node (road) (7.2910, 80.6340)
    - Galle Station (rail) (6.0535, 80.2210)
    - Matara Station (rail) (5.9549, 80.5550)
    - Unreachable Island Node (0.0, 0.0)
    """
    g = MultimodalGraph()

    # Colombo cluster
    g.add_node(Node("colombo_fort_station", lat=6.9344, lon=79.8428, properties={"type": "station"}))
    g.add_node(Node("colombo_fort_road", lat=6.9345, lon=79.8430, properties={"type": "road"}))
    g.add_node(Node("pettah_bus_stand", lat=6.9360, lon=79.8500, properties={"type": "bus"}))
    g.add_node(Node("maradana_station", lat=6.9271, lon=79.8612, properties={"type": "station"}))

    # Kandy cluster
    g.add_node(Node("kandy_station", lat=7.2906, lon=80.6337, properties={"type": "station"}))
    g.add_node(Node("kandy_road", lat=7.2910, lon=80.6340, properties={"type": "road"}))
    g.add_node(Node("kandy_bus_stand", lat=7.2920, lon=80.6350, properties={"type": "bus"}))

    # Southern cluster (Galle - Matara)
    g.add_node(Node("galle_station", lat=6.0535, lon=80.2210, properties={"type": "station"}))
    g.add_node(Node("galle_road", lat=6.0536, lon=80.2212, properties={"type": "road"}))
    g.add_node(Node("matara_road", lat=5.9550, lon=80.5552, properties={"type": "road"}))
    g.add_node(Node("matara_station", lat=5.9549, lon=80.5550, properties={"type": "station"}))

    # Disconnected node
    g.add_node(Node("isolated_island_node", lat=1.0, lon=1.0, properties={"type": "isolated"}))

    # Colombo internal connections
    # Walking transfer from Colombo Fort Station to Fort Road (0.05 km)
    g.add_edge(Edge(
        "colombo_fort_station", "colombo_fort_road", GraphMode.WALKING, directed=False,
        attributes={"distance_km": 0.05, "travel_time_min": 1.0, "cost_lkr": 0.0, "transfer_type": "station_to_road"}
    ))
    # Road connection Fort Road to Pettah Bus Stand (0.85 km)
    g.add_edge(Edge(
        "colombo_fort_road", "pettah_bus_stand", GraphMode.ROAD, directed=False,
        attributes={"distance_km": 0.85, "travel_time_min": 3.0, "cost_lkr": 50.0}
    ))
    # Bus connection Pettah Bus Stand to Maradana (2.0 km)
    g.add_edge(Edge(
        "pettah_bus_stand", "maradana_station", GraphMode.BUS, directed=False,
        attributes={"distance_km": 2.0, "travel_time_min": 10.0, "cost_lkr": 30.0}
    ))

    # Inter-city Rail: Colombo Fort Station -> Kandy Station (115.5 km)
    g.add_edge(Edge(
        "colombo_fort_station", "kandy_station", GraphMode.RAIL, directed=False,
        attributes={"distance_km": 115.5, "travel_time_min": 150.0, "cost_lkr": 250.0}
    ))
    # Kandy Station -> Kandy Road (Walking Transfer, 0.1 km)
    g.add_edge(Edge(
        "kandy_station", "kandy_road", GraphMode.WALKING, directed=False,
        attributes={"distance_km": 0.1, "travel_time_min": 2.0, "cost_lkr": 0.0, "transfer_type": "station_to_road"}
    ))
    # Kandy Road -> Kandy Bus Stand (Road/Bus, 0.4 km)
    g.add_edge(Edge(
        "kandy_road", "kandy_bus_stand", GraphMode.BUS, directed=False,
        attributes={"distance_km": 0.4, "travel_time_min": 3.0, "cost_lkr": 20.0}
    ))

    # Inter-city Road: Colombo Fort Road -> Kandy Road (116.0 km)
    g.add_edge(Edge(
        "colombo_fort_road", "kandy_road", GraphMode.ROAD, directed=False,
        attributes={"distance_km": 116.0, "travel_time_min": 210.0, "cost_lkr": 1200.0}
    ))

    # Galle -> Matara cluster
    g.add_edge(Edge(
        "galle_station", "galle_road", GraphMode.WALKING, directed=False,
        attributes={"distance_km": 0.08, "travel_time_min": 1.5, "cost_lkr": 0.0, "transfer_type": "station_to_road"}
    ))
    g.add_edge(Edge(
        "galle_road", "matara_road", GraphMode.ROAD, directed=False,
        attributes={"distance_km": 42.5, "travel_time_min": 55.0, "cost_lkr": 400.0}
    ))
    g.add_edge(Edge(
        "matara_road", "matara_station", GraphMode.WALKING, directed=False,
        attributes={"distance_km": 0.12, "travel_time_min": 2.0, "cost_lkr": 0.0, "transfer_type": "road_to_station"}
    ))

    return g


@pytest.fixture
def client(multimodal_audit_graph):
    test_app.dependency_overrides[get_multimodal_graph] = lambda: multimodal_audit_graph
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


# =====================================================================
# Step 2: Test A — Valid Route Request (Colombo -> Kandy)
# =====================================================================

def test_a_valid_route_colombo_to_kandy(client, multimodal_audit_graph):
    """
    Test A: Valid route request between Colombo and Kandy.
    Verifies:
    1. Acceptance (HTTP 200).
    2. Origin and destination snapped correctly.
    3. Path continuity across valid graph edges.
    4. Distance matches independent sum of traversed edges.
    5. Modes used are accurately identified.
    6. Missing metrics or calculated metrics are valid.
    """
    payload = {
        "origin": {"latitude": 6.9344, "longitude": 79.8428},  # Colombo Fort Station
        "destination": {"latitude": 7.2906, "longitude": 80.6337},  # Kandy Station
        "max_snap_distance_km": 10.0
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    # Check origin/dest snapped nodes
    assert data["origin_node"] == "colombo_fort_station"
    assert data["destination_node"] == "kandy_station"
    assert data["source"] == "local_dijkstra"

    # Independent verification of path continuity
    nodes = data["nodes"]
    assert len(nodes) >= 2
    assert nodes[0] == data["origin_node"]
    assert nodes[-1] == data["destination_node"]

    edges = data["edges"]
    assert len(edges) == len(nodes) - 1

    # Verify each edge exists in graph and connects consecutive nodes
    independent_distance_sum = 0.0
    modes_seen = []
    for i, e in enumerate(edges):
        assert e["from_node"] == nodes[i]
        assert e["to_node"] == nodes[i+1]
        
        # Check edge exists in the audit graph
        graph_edges = multimodal_audit_graph.get_edges(e["from_node"], e["to_node"])
        assert len(graph_edges) > 0, f"No edge in graph between {e['from_node']} and {e['to_node']}"
        
        matched_edge = next((ge for ge in graph_edges if (ge.mode.value if hasattr(ge.mode, "value") else str(ge.mode)) == e["mode"]), None)
        assert matched_edge is not None
        
        edge_dist = matched_edge.attributes.get("distance_km")
        assert edge_dist is not None
        independent_distance_sum += edge_dist
        
        if e["mode"] not in modes_seen:
            modes_seen.append(e["mode"])

    # Verify reported distance matches edge sum within tolerance
    assert math.isclose(data["total_distance_km"], independent_distance_sum, rel_tol=1e-4)
    assert data["modes_used"] == modes_seen
    assert data["travel_time_complete"] is True
    assert data["total_travel_time_min"] is not None
    assert data["cost_complete"] is True
    assert data["total_cost_lkr"] is not None


# =====================================================================
# Step 2: Test B — Another Valid Route (Galle -> Matara)
# =====================================================================

def test_b_second_valid_route_galle_to_matara(client, multimodal_audit_graph):
    """
    Test B: Second valid route (Galle to Matara).
    Verifies that route changes appropriately and is not hard-coded.
    """
    payload = {
        "origin": {"latitude": 6.0535, "longitude": 80.2210},  # Galle
        "destination": {"latitude": 5.9549, "longitude": 80.5550},  # Matara
        "max_snap_distance_km": 10.0
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["origin_node"] == "galle_station"
    assert data["destination_node"] == "matara_station"
    assert data["nodes"] == ["galle_station", "galle_road", "matara_road", "matara_station"]

    # Verify distance independently: 0.08 + 42.5 + 0.12 = 42.7 km
    expected_dist = 0.08 + 42.5 + 0.12
    assert math.isclose(data["total_distance_km"], expected_dist, rel_tol=1e-4)
    assert data["modes_used"] == ["walking", "road"]
    assert data["transfers_count"] == 2  # Station to road + road to station


# =====================================================================
# Step 2: Test C — Same Origin and Destination
# =====================================================================

def test_c_same_origin_and_destination(client):
    """
    Test C: Origin and destination are identical.
    Verifies documented zero-length route with 0 distance and 1 node.
    """
    # 1. Coordinate-based identical points
    payload_coords = {
        "origin": {"latitude": 6.9344, "longitude": 79.8428},
        "destination": {"latitude": 6.9344, "longitude": 79.8428}
    }
    resp = client.post("/routes/dijkstra", json=payload_coords)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_distance_km"] == 0.0
    assert data["edges_count"] == 0
    assert data["edges"] == []
    assert len(data["nodes"]) == 1
    assert data["nodes"][0] == "colombo_fort_station"

    # 2. Node-id based identical points
    payload_nodes = {
        "origin_node_id": "colombo_fort_station",
        "destination_node_id": "colombo_fort_station"
    }
    resp_node = client.post("/routes/dijkstra", json=payload_nodes)
    assert resp_node.status_code == 200
    data_node = resp_node.json()
    assert data_node["total_distance_km"] == 0.0
    assert data_node["nodes"] == ["colombo_fort_station"]
    assert data_node["edges"] == []


# =====================================================================
# Step 2: Test D — Invalid Location
# =====================================================================

def test_d_invalid_location(client):
    """
    Test D: Request with an invalid location.
    Verifies that the API returns clear validation/not found error without silent fallback.
    """
    # Case 1: Non-existent node ID
    payload_invalid_id = {
        "origin_node_id": "Invalid_Test_Location_987654",
        "destination_node_id": "kandy_station"
    }
    resp_id = client.post("/routes/dijkstra", json=payload_invalid_id)
    assert resp_id.status_code == 404
    assert "Invalid_Test_Location_987654" in resp_id.json()["detail"]

    # Case 2: Location coordinates far outside coverage area (e.g., Antarctica)
    payload_out_of_bounds = {
        "origin": {"latitude": -75.0, "longitude": 0.0},
        "destination": {"latitude": 7.2906, "longitude": 80.6337},
        "max_snap_distance_km": 25.0
    }
    resp_coords = client.post("/routes/dijkstra", json=payload_out_of_bounds)
    assert resp_coords.status_code == 422
    assert "outside graph coverage" in resp_coords.json()["detail"].lower()


# =====================================================================
# Step 2: Test E — Unreachable Destination (Disconnected Components)
# =====================================================================

def test_e_unreachable_destination(client):
    """
    Test E: Controlled test graph containing disconnected components.
    Verifies Dijkstra reports unreachable destination (HTTP 404) and never invents an edge.
    """
    payload = {
        "origin_node_id": "colombo_fort_station",
        "destination_node_id": "isolated_island_node"
    }
    resp = client.post("/routes/dijkstra", json=payload)
    assert resp.status_code == 404
    assert "unreachable" in resp.json()["detail"].lower()


# =====================================================================
# Step 2: Test F — Invalid Request Body
# =====================================================================

def test_f_invalid_request_body(client):
    """
    Test F: Empty body, invalid types, and invalid schema fields.
    Verifies HTTP 422 Unprocessable Entity.
    """
    # Empty body
    resp_empty = client.post("/routes/dijkstra", json={})
    assert resp_empty.status_code == 422

    # Invalid latitude type (string)
    resp_bad_type = client.post("/routes/dijkstra", json={
        "origin": {"latitude": "invalid_latitude", "longitude": 79.84},
        "destination_node_id": "kandy_station"
    })
    assert resp_bad_type.status_code == 422

    # Latitude out of bounds (> 90.0)
    resp_out_of_range = client.post("/routes/dijkstra", json={
        "origin": {"latitude": 120.0, "longitude": 79.84},
        "destination_node_id": "kandy_station"
    })
    assert resp_out_of_range.status_code == 422

    # Missing destination
    resp_missing_dest = client.post("/routes/dijkstra", json={
        "origin_node_id": "colombo_fort_station"
    })
    assert resp_missing_dest.status_code == 422


# =====================================================================
# Step 2: Test G — External API Failure Handling
# =====================================================================

@pytest.mark.asyncio
async def test_g_external_api_failure_handling():
    """
    Test G: Mock external geocoding / directions API failure (timeout, HTTP error, no api key).
    Verifies backend handles failure gracefully, returns meaningful error / fallback,
    and exposes no secret credentials or stack traces.
    """
    req = RouteRequest(
        origin=Coordinate(latitude=6.9271, longitude=79.8612),
        destination=Coordinate(latitude=7.2906, longitude=80.6337)
    )

    # 1. Timeout simulation
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Mock ORS Timeout")):
        client = RouteAPIClient()
        client.api_key = "secret_ors_key_xyz_123"
        result = await client.get_route(req)
        assert result.source == "route_api_timeout"
        assert result.distance is None

    # 2. HTTP 500 error simulation
    mock_resp = httpx.Response(status_code=500, request=httpx.Request("POST", "https://api.openrouteservice.org"))
    with patch("httpx.AsyncClient.post", side_effect=httpx.HTTPStatusError("500 Internal", request=mock_resp.request, response=mock_resp)):
        client = RouteAPIClient()
        client.api_key = "secret_ors_key_xyz_123"
        result = await client.get_route(req)
        assert result.source == "route_api_http_error"

    # 3. Graceful fallback in RouteValidationService
    service = RouteValidationService()
    service.api_client.api_key = "secret_ors_key_xyz_123"
    with patch.object(service.api_client, "get_route", side_effect=httpx.TimeoutException("Timeout")):
        val_result = await service.validate_route(req, local_distance_km=115.5, local_duration=150.0)
        # Should gracefully return local database fallback without exposing secrets
        assert val_result.source == "local_database_fallback"
        assert val_result.distance == 115.5
        assert "secret_ors_key_xyz_123" not in str(val_result)


# =====================================================================
# Step 2: Test H — Multimodal Route Verification
# =====================================================================

def test_h_multimodal_route_and_transfers(client, multimodal_audit_graph):
    """
    Test H: Using an isolated multimodal graph with known road, bus, rail, walking, transfer edges.
    Verifies:
    1. Route crosses at least two transport modes.
    2. Consecutive edges connect correctly.
    3. Mode changes use valid transfer connections.
    4. Distance equals exact sum of actual edge weights.
    5. Reported modes match traversed edges.
    6. Invalid transfer has no connection.
    """
    # Colombo Fort Station -> Pettah Bus Stand -> Maradana Station
    # Path: colombo_fort_station -> colombo_fort_road (walking, 0.05 km)
    #       -> pettah_bus_stand (road, 0.85 km)
    #       -> maradana_station (bus, 2.0 km)
    payload = {
        "origin_node_id": "colombo_fort_station",
        "destination_node_id": "maradana_station"
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["nodes"] == ["colombo_fort_station", "colombo_fort_road", "pettah_bus_stand", "maradana_station"]
    assert data["modes_used"] == ["walking", "road", "bus"]
    assert len(data["modes_used"]) >= 2
    assert data["transfers_count"] == 2  # Walking->road + road->bus

    expected_distance = 0.05 + 0.85 + 2.0  # 2.9 km
    assert math.isclose(data["total_distance_km"], expected_distance, rel_tol=1e-4)

    # Verify edge connectivity
    for i in range(len(data["edges"])):
        assert data["edges"][i]["from_node"] == data["nodes"][i]
        assert data["edges"][i]["to_node"] == data["nodes"][i+1]

    # Verify that an invalid transfer cannot cross without a connecting edge
    g_no_transfer = MultimodalGraph()
    g_no_transfer.add_node(Node("train_platform", lat=6.93, lon=79.84))
    g_no_transfer.add_node(Node("bus_bay", lat=6.94, lon=79.85))
    # No transfer edge added between train_platform and bus_bay!
    router_no_transfer = DijkstraRouter(g_no_transfer)
    with pytest.raises(ValueError, match="unreachable"):
        router_no_transfer.route("train_platform", "bus_bay")


# =====================================================================
# Step 2: Test I — Dijkstra Correctness on Known-Answer Fixture
# =====================================================================

def test_i_dijkstra_known_graph_correctness():
    """
    Test I: Small graph with known edge weights:
      A -> B = 4
      A -> C = 1
      C -> B = 1
      B -> D = 2
      C -> D = 7
    Expected shortest path: A -> C -> B -> D
    Expected total weight: 1 + 1 + 2 = 4
    Also test:
    - Unreachable node
    - Invalid negative edge weight
    """
    graph = MultimodalGraph()
    for n in ["A", "B", "C", "D", "E"]:
        graph.add_node(Node(n, lat=7.0, lon=80.0))

    # Add edges with attributes
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, directed=True, attributes={"distance_km": 4.0}))
    graph.add_edge(Edge("A", "C", GraphMode.ROAD, directed=True, attributes={"distance_km": 1.0}))
    graph.add_edge(Edge("C", "B", GraphMode.ROAD, directed=True, attributes={"distance_km": 1.0}))
    graph.add_edge(Edge("B", "D", GraphMode.ROAD, directed=True, attributes={"distance_km": 2.0}))
    graph.add_edge(Edge("C", "D", GraphMode.ROAD, directed=True, attributes={"distance_km": 7.0}))
    # Note: E is unreachable from A

    router = DijkstraRouter(graph)
    result = router.route("A", "D")

    # 1. Correctness of path and weight
    assert result.nodes == ["A", "C", "B", "D"], f"Expected ['A', 'C', 'B', 'D'], got {result.nodes}"
    assert math.isclose(result.total_distance_km, 4.0, abs_tol=1e-6), f"Expected 4.0, got {result.total_distance_km}"
    assert len(result.edges) == 3

    # 2. Unreachable node E
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("A", "E")

    # 3. Rejection of invalid negative edge weight
    neg_graph = MultimodalGraph()
    neg_graph.add_node(Node("X"))
    neg_graph.add_node(Node("Y"))
    neg_graph.add_edge(Edge("X", "Y", GraphMode.ROAD, directed=True, attributes={"distance_km": -5.0}))
    neg_router = DijkstraRouter(neg_graph)
    with pytest.raises(ValueError, match="Destination is unreachable"):
        neg_router.route("X", "Y")

    # Rejection of NaN or infinity in cost model
    assert DistanceCostModel.get_weight(Edge("X", "Y", GraphMode.ROAD, attributes={"distance_km": float("nan")})) is None
    assert DistanceCostModel.get_weight(Edge("X", "Y", GraphMode.ROAD, attributes={"distance_km": float("inf")})) is None
    assert DistanceCostModel.get_weight(Edge("X", "Y", GraphMode.ROAD, attributes={"distance_km": "five"})) is None
    assert DistanceCostModel.get_weight(Edge("X", "Y", GraphMode.ROAD, attributes={"distance_km": True})) is None


# =====================================================================
# Step 2: Test J — Repeated Requests (Determinism & Idempotency)
# =====================================================================

def test_j_repeated_requests_determinism(client, multimodal_audit_graph):
    """
    Test J: Send the same valid request at least twice.
    Verifies that results are identical/deterministic and no graph corruption or record duplication occurs.
    """
    initial_stats = multimodal_audit_graph.get_statistics()
    initial_nodes_count = len(multimodal_audit_graph.nodes)
    
    payload = {
        "origin_node_id": "colombo_fort_station",
        "destination_node_id": "maradana_station"
    }

    # First request
    resp1 = client.post("/routes/dijkstra", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Second request
    resp2 = client.post("/routes/dijkstra", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Compare responses
    assert data1["nodes"] == data2["nodes"]
    assert data1["total_distance_km"] == data2["total_distance_km"]
    assert data1["modes_used"] == data2["modes_used"]
    assert data1["transfers_count"] == data2["transfers_count"]
    assert len(data1["edges"]) == len(data2["edges"])

    # Verify graph state was not modified
    after_stats = multimodal_audit_graph.get_statistics()
    after_nodes_count = len(multimodal_audit_graph.nodes)
    assert initial_nodes_count == after_nodes_count
    assert initial_stats == after_stats
