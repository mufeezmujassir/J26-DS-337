import pytest
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter, DijkstraPathResult

def test_distance_totals_and_counts():
    graph = MultimodalGraph()
    for n in ["N1", "N2", "N3"]:
        graph.add_node(Node(n))
    graph.add_edge(Edge("N1", "N2", GraphMode.ROAD, attributes={"distance_km": 2.45}))
    graph.add_edge(Edge("N2", "N3", GraphMode.ROAD, attributes={"distance_km": 3.55}))
    
    router = DijkstraRouter(graph)
    result = router.route("N1", "N3")
    
    assert result.total_distance_km == 6.0
    assert result.node_count == 3
    assert result.edge_count == 2
    assert result.nodes == ["N1", "N2", "N3"]
    assert result.modes_used == ["road"]
    assert result.transfers_count == 0

def test_mode_sequences_and_transfers():
    graph = MultimodalGraph()
    for n in ["A", "B", "C", "D"]:
        graph.add_node(Node(n))
        
    # A -> B (Walking, 0.5 km)
    graph.add_edge(Edge("A", "B", GraphMode.WALKING, attributes={"distance_km": 0.5}))
    # B -> C (Transfer edge, 0.1 km)
    graph.add_edge(Edge("B", "C", GraphMode.TRANSFER, attributes={"distance_km": 0.1}))
    # C -> D (Bus, 4.0 km)
    graph.add_edge(Edge("C", "D", GraphMode.BUS, attributes={"distance_km": 4.0}))
    
    router = DijkstraRouter(graph)
    result = router.route("A", "D")
    
    assert result.modes_used == ["walking", "transfer", "bus"]
    # 1 transfer at transfer edge (walking -> transfer -> bus)
    assert result.transfers_count == 1

def test_missing_travel_time_behavior():
    graph = MultimodalGraph()
    for n in ["A", "B", "C"]:
        graph.add_node(Node(n))
        
    # First edge has travel time, second edge has None
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 2.0, "travel_time_min": 5.0}))
    graph.add_edge(Edge("B", "C", GraphMode.ROAD, attributes={"distance_km": 3.0, "travel_time_min": None}))
    
    router = DijkstraRouter(graph)
    result = router.route("A", "C")
    
    # Must NOT invent average speeds or fabricate time
    assert result.total_travel_time_min is None
    assert result.travel_time_complete is False
    assert any("Travel time unavailable" in w for w in result.warnings)

def test_complete_travel_time_behavior():
    graph = MultimodalGraph()
    for n in ["A", "B", "C"]:
        graph.add_node(Node(n))
        
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 2.0, "travel_time_min": 6.5}))
    graph.add_edge(Edge("B", "C", GraphMode.ROAD, attributes={"distance_km": 3.0, "travel_time_min": 10.5}))
    
    router = DijkstraRouter(graph)
    result = router.route("A", "C")
    
    assert result.total_travel_time_min == 17.0
    assert result.travel_time_complete is True

def test_missing_cost_vs_true_zero_cost():
    graph = MultimodalGraph()
    for n in ["A", "B", "C", "D"]:
        graph.add_node(Node(n))
        
    # True zero cost (e.g. free walking transfer leg) + paid bus leg
    graph.add_edge(Edge("A", "B", GraphMode.WALKING, attributes={"distance_km": 0.5, "cost_lkr": 0.0}))
    graph.add_edge(Edge("B", "C", GraphMode.BUS, attributes={"distance_km": 5.0, "cost_lkr": 75.0}))
    
    router = DijkstraRouter(graph)
    result1 = router.route("A", "C")
    assert result1.total_cost_lkr == 75.0
    assert result1.cost_complete is True
    
    # Edge with missing (None) cost
    graph.add_edge(Edge("C", "D", GraphMode.ROAD, attributes={"distance_km": 2.0, "cost_lkr": None}))
    result2 = router.route("A", "D")
    assert result2.total_cost_lkr is None
    assert result2.cost_complete is False
    assert any("Travel cost unavailable" in w for w in result2.warnings)

def test_route_result_to_dict():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_edge(Edge(
        "A", "B", GraphMode.ROAD,
        attributes={"distance_km": 1.5, "cost_lkr": 0.0, "travel_time_min": 3.0, "source_id": "rd_1"}
    ))
    
    router = DijkstraRouter(graph)
    result = router.route("A", "B")
    d = result.to_dict()
    
    assert d["total_distance_km"] == 1.5
    assert d["nodes"] == ["A", "B"]
    assert d["nodes_count"] == 2
    assert d["edges_count"] == 1
    assert d["modes_used"] == ["road"]
    assert d["transfers_count"] == 0
    assert d["total_travel_time_min"] == 3.0
    assert d["travel_time_complete"] is True
    assert d["total_cost_lkr"] == 0.0
    assert d["cost_complete"] is True
    assert len(d["edges"]) == 1
    assert d["edges"][0]["source_id"] == "rd_1"

def test_single_node_origin_equals_destination_metadata():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    
    router = DijkstraRouter(graph)
    result = router.route("A", "A")
    d = result.to_dict()
    
    assert d["total_distance_km"] == 0.0
    assert d["nodes"] == ["A"]
    assert d["nodes_count"] == 1
    assert d["edges_count"] == 0
    assert d["modes_used"] == []
    assert d["transfers_count"] == 0
    assert d["total_travel_time_min"] == 0.0
    assert d["travel_time_complete"] is True
    assert d["total_cost_lkr"] == 0.0
    assert d["cost_complete"] is True
    assert d["edges"] == []
    assert d["warnings"] == []
