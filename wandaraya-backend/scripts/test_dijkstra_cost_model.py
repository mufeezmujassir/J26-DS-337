import math
import pytest
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DistanceCostModel, DijkstraRouter

def test_distance_cost_model_validation():
    # Valid numeric values
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 10.5})) == 10.5
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 0})) == 0.0
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 5})) == 5.0
    
    # Invalid values: booleans
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": True})) is None
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": False})) is None
    
    # Invalid values: negatives, None, inf, nan, strings, missing
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": -1.0})) is None
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": None})) is None
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": math.inf})) is None
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": float("nan")})) is None
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": "5.0"})) is None
    assert DistanceCostModel.get_weight(Edge("A", "B", GraphMode.ROAD, attributes={})) is None

def test_single_valid_path():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_node(Node("C"))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 3.2}))
    graph.add_edge(Edge("B", "C", GraphMode.ROAD, attributes={"distance_km": 4.8}))
    
    router = DijkstraRouter(graph)
    path, dist = router.route("A", "C")
    assert path == ["A", "B", "C"]
    assert pytest.approx(dist, 1e-4) == 8.0

def test_multiple_candidate_paths_minimization():
    graph = MultimodalGraph()
    for n in ["A", "B", "C", "D"]:
        graph.add_node(Node(n))
        
    # Path 1: A -> B -> D: 5.0 + 6.0 = 11.0 km
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 5.0}))
    graph.add_edge(Edge("B", "D", GraphMode.ROAD, attributes={"distance_km": 6.0}))
    
    # Path 2: A -> C -> D: 7.0 + 2.0 = 9.0 km (Shortest)
    graph.add_edge(Edge("A", "C", GraphMode.ROAD, attributes={"distance_km": 7.0}))
    graph.add_edge(Edge("C", "D", GraphMode.ROAD, attributes={"distance_km": 2.0}))
    
    # Path 3: Direct A -> D: 12.0 km
    graph.add_edge(Edge("A", "D", GraphMode.ROAD, attributes={"distance_km": 12.0}))
    
    router = DijkstraRouter(graph)
    path, dist = router.route("A", "D")
    assert path == ["A", "C", "D"]
    assert pytest.approx(dist, 1e-4) == 9.0

def test_disconnected_nodes():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_node(Node("Isolated"))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 3.0}))
    
    router = DijkstraRouter(graph)
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("A", "Isolated")

def test_invalid_weights_ignored_safely():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    
    # Only invalid edges exist
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": -4.0}))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": None}))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": "invalid"}))
    
    router = DijkstraRouter(graph)
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("A", "B")

def test_directed_connections_respected():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    # One-way directed from A to B
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, directed=True, attributes={"distance_km": 5.0}))
    
    router = DijkstraRouter(graph)
    path, dist = router.route("A", "B")
    assert path == ["A", "B"]
    assert dist == 5.0
    
    # Reverse should be unreachable
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("B", "A")
