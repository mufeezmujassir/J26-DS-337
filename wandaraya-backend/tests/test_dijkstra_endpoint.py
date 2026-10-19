import os
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "mock_key_for_unit_tests")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.routers import routes
from app.routers.routes import get_multimodal_graph

test_app = FastAPI()
test_app.include_router(routes.router)

@pytest.fixture
def test_graph():
    graph = MultimodalGraph()
    # Coordinates in Sri Lanka (Colombo region)
    # Node 1: Fort (6.9344, 79.8428)
    graph.add_node(Node(node_id="fort_station", lat=6.9344, lon=79.8428))
    # Node 2: Maradana (6.9271, 79.8612) ~ 2.2 km away
    graph.add_node(Node(node_id="maradana_station", lat=6.9271, lon=79.8612))
    # Node 3: Pettah (6.9360, 79.8500)
    graph.add_node(Node(node_id="pettah_bus", lat=6.9360, lon=79.8500))
    # Node 4: Isolated Kandy node (7.2906, 80.6337) ~ 100 km away
    graph.add_node(Node(node_id="kandy_station", lat=7.2906, lon=80.6337))

    # Connect Fort -> Pettah (Walking, 0.9 km)
    graph.add_edge(Edge(
        "fort_station", "pettah_bus", GraphMode.WALKING,
        directed=False,
        attributes={"distance_km": 0.9, "travel_time_min": 10.0, "cost_lkr": 0.0}
    ))
    # Connect Pettah -> Maradana (Bus, 2.0 km)
    graph.add_edge(Edge(
        "pettah_bus", "maradana_station", GraphMode.BUS,
        directed=False,
        attributes={"distance_km": 2.0, "travel_time_min": 8.0, "cost_lkr": 30.0}
    ))

    return graph

@pytest.fixture
def client(test_graph):
    test_app.dependency_overrides[get_multimodal_graph] = lambda: test_graph
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()

def test_route_by_coordinates_success(client):
    payload = {
        "origin": {"latitude": 6.9340, "longitude": 79.8430}, # Very close to fort_station
        "destination": {"latitude": 6.9270, "longitude": 79.8610}, # Very close to maradana_station
        "max_snap_distance_km": 5.0
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    assert data["source"] == "local_dijkstra"
    assert data["origin_node"] == "fort_station"
    assert data["destination_node"] == "maradana_station"
    assert data["nodes"] == ["fort_station", "pettah_bus", "maradana_station"]
    assert pytest.approx(data["total_distance_km"], 1e-2) == 2.9
    assert data["modes_used"] == ["walking", "bus"]
    assert data["transfers_count"] == 1
    assert data["total_travel_time_min"] == 18.0
    assert data["travel_time_complete"] is True
    assert data["total_cost_lkr"] == 30.0
    assert data["cost_complete"] is True
    assert len(data["edges"]) == 2

def test_route_by_node_ids_success(client):
    payload = {
        "origin_node_id": "fort_station",
        "destination_node_id": "pettah_bus"
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["nodes"] == ["fort_station", "pettah_bus"]
    assert data["total_distance_km"] == 0.9

def test_route_origin_equals_destination(client):
    payload = {
        "origin_node_id": "fort_station",
        "destination_node_id": "fort_station"
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_distance_km"] == 0.0
    assert data["nodes"] == ["fort_station"]
    assert data["edges"] == []

def test_route_unreachable_destination(client):
    payload = {
        "origin_node_id": "fort_station",
        "destination_node_id": "kandy_station"
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "unreachable" in data["detail"].lower()

def test_route_coordinates_outside_coverage(client):
    payload = {
        "origin": {"latitude": 6.9340, "longitude": 79.8430},
        "destination": {"latitude": 9.6615, "longitude": 80.0255}, # Jaffna, ~350 km away
        "max_snap_distance_km": 10.0
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "outside graph coverage" in data["detail"]

def test_route_nonexistent_node_id(client):
    payload = {
        "origin_node_id": "nonexistent_node_123",
        "destination_node_id": "fort_station"
    }
    response = client.post("/routes/dijkstra", json=payload)
    assert response.status_code == 404
    assert "does not exist in graph" in response.json()["detail"]

def test_route_missing_parameters(client):
    # Missing origin
    response = client.post("/routes/dijkstra", json={"destination_node_id": "fort_station"})
    assert response.status_code == 422
    assert "origin" in response.json()["detail"].lower()
    
    # Missing destination
    response = client.post("/routes/dijkstra", json={"origin_node_id": "fort_station"})
    assert response.status_code == 422
    assert "destination" in response.json()["detail"].lower()

def test_empty_graph_service_unavailable():
    empty_graph = MultimodalGraph()
    test_app.dependency_overrides[get_multimodal_graph] = lambda: empty_graph
    try:
        c = TestClient(test_app)
        response = c.post("/routes/dijkstra", json={
            "origin_node_id": "A",
            "destination_node_id": "B"
        })
        assert response.status_code == 503
        assert "empty or not yet loaded" in response.json()["detail"]
    finally:
        test_app.dependency_overrides.clear()
