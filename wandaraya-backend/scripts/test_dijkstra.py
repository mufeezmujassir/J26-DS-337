import pytest
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter

def test_road_only_routing():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 5.0}))
    
    router = DijkstraRouter(graph)
    path, dist = router.route("A", "B")
    
    assert path == ["A", "B"]
    assert dist == 5.0

def test_valid_multimodal_route():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("Sta1"))
    graph.add_node(Node("B"))
    
    # Road A to Sta1
    graph.add_edge(Edge("A", "Sta1", GraphMode.ROAD, attributes={"distance_km": 1.0}))
    # Train Transfer (simulated)
    graph.add_edge(Edge("Sta1", "B", GraphMode.WALKING, attributes={"distance_km": 0.5}))
    
    router = DijkstraRouter(graph)
    path, dist = router.route("A", "B")
    assert path == ["A", "Sta1", "B"]
    assert dist == 1.5

def test_unreachable_destination():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    
    router = DijkstraRouter(graph)
    with pytest.raises(ValueError):
        router.route("A", "B")

def test_invalid_edge_weights():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    # Missing weights should be dynamically ignored by the explicit validation logic
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": None}))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": -5.0}))
    
    router = DijkstraRouter(graph)
    with pytest.raises(ValueError):
        router.route("A", "B")

def test_multiple_possible_paths_dijkstra():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_node(Node("C"))
    
    # Path 1: A -> B -> C (dist = 10)
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 6}))
    graph.add_edge(Edge("B", "C", GraphMode.ROAD, attributes={"distance_km": 4}))
    
    # Path 2: A -> C (dist = 8) - should win
    graph.add_edge(Edge("A", "C", GraphMode.ROAD, attributes={"distance_km": 8}))
    
    router = DijkstraRouter(graph)
    path, dist = router.route("A", "C")
    assert path == ["A", "C"]
    assert dist == 8.0

def test_slower_route_objective():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B_express"))
    graph.add_node(Node("B_scenic"))
    graph.add_node(Node("C"))

    # Express path: higher speed (10 km in 6 min = 100 km/h)
    graph.add_edge(Edge("A", "B_express", GraphMode.ROAD, attributes={"distance_km": 10.0, "travel_time_min": 6.0}))
    graph.add_edge(Edge("B_express", "C", GraphMode.ROAD, attributes={"distance_km": 10.0, "travel_time_min": 6.0}))

    # Scenic/leisurely path: lower speed (10 km in 30 min = 20 km/h)
    graph.add_edge(Edge("A", "B_scenic", GraphMode.BUS, attributes={"distance_km": 10.0, "travel_time_min": 30.0}))
    graph.add_edge(Edge("B_scenic", "C", GraphMode.BUS, attributes={"distance_km": 10.0, "travel_time_min": 30.0}))

    router_fast = DijkstraRouter(graph, objective="fastest")
    res_fast = router_fast.route("A", "C")
    assert "B_express" in res_fast.nodes

    router_slow = DijkstraRouter(graph, objective="slower")
    res_slow = router_slow.route("A", "C")
    assert "B_scenic" in res_slow.nodes
    assert res_slow.objective == "slower"

