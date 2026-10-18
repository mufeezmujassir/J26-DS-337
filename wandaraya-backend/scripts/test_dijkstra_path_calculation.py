import copy
import pytest
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter, DijkstraPathResult

def test_simple_shortest_path_reconstruction():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    e = Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 4.5, "source_id": "road_101"})
    graph.add_edge(e)
    
    router = DijkstraRouter(graph)
    result = router.route("A", "B")
    
    assert isinstance(result, DijkstraPathResult)
    assert result.nodes == ["A", "B"]
    assert len(result.edges) == 1
    assert result.edges[0].from_node == "A"
    assert result.edges[0].to_node == "B"
    assert result.edges[0].mode == GraphMode.ROAD
    assert result.edges[0].attributes["source_id"] == "road_101"
    assert pytest.approx(result.total_distance_km, 1e-4) == 4.5
    
    # Check backwards-compatible tuple unpacking
    path_nodes, dist = result
    assert path_nodes == ["A", "B"]
    assert dist == 4.5

def test_two_competing_routes():
    graph = MultimodalGraph()
    for n in ["A", "B", "C", "D"]:
        graph.add_node(Node(n))
        
    # Route 1: A -> B -> D (3 + 7 = 10 km)
    e1 = Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 3.0, "source_id": "e1"})
    e2 = Edge("B", "D", GraphMode.ROAD, attributes={"distance_km": 7.0, "source_id": "e2"})
    # Route 2: A -> C -> D (4 + 4 = 8 km) -> Shortest
    e3 = Edge("A", "C", GraphMode.ROAD, attributes={"distance_km": 4.0, "source_id": "e3"})
    e4 = Edge("C", "D", GraphMode.ROAD, attributes={"distance_km": 4.0, "source_id": "e4"})
    for edge in [e1, e2, e3, e4]:
        graph.add_edge(edge)
        
    router = DijkstraRouter(graph)
    result = router.route("A", "D")
    
    assert result.nodes == ["A", "C", "D"]
    assert len(result.edges) == 2
    assert result.edges[0].attributes["source_id"] == "e3"
    assert result.edges[1].attributes["source_id"] == "e4"
    assert pytest.approx(result.total_distance_km, 1e-4) == 8.0

def test_disconnected_destination():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_node(Node("C"))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 2.0}))
    
    router = DijkstraRouter(graph)
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("A", "C")

def test_origin_equal_to_destination():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    
    router = DijkstraRouter(graph)
    result = router.route("A", "A")
    assert result.nodes == ["A"]
    assert result.edges == []
    assert result.total_distance_km == 0.0

def test_invalid_node_identifiers():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    
    router = DijkstraRouter(graph)
    with pytest.raises(ValueError, match="must not be None"):
        router.route(None, "A")
        
    with pytest.raises(ValueError, match="must not be None"):
        router.route("A", None)
        
    with pytest.raises(ValueError, match="Origin or destination not in graph"):
        router.route("A", "NonExistent")
        
    with pytest.raises(ValueError, match="Origin or destination not in graph"):
        router.route("NonExistent", "A")

def test_directed_edges():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, directed=True, attributes={"distance_km": 6.0}))
    
    router = DijkstraRouter(graph)
    forward = router.route("A", "B")
    assert forward.nodes == ["A", "B"]
    assert forward.total_distance_km == 6.0
    
    with pytest.raises(ValueError, match="Destination is unreachable"):
        router.route("B", "A")

def test_multimodal_path_reconstruction():
    graph = MultimodalGraph()
    graph.add_node(Node("Hotel"))
    graph.add_node(Node("BusStop1"))
    graph.add_node(Node("TrainStation1"))
    graph.add_node(Node("TrainStation2"))
    graph.add_node(Node("Destination"))
    
    # 1. Walk from Hotel to BusStop1 (0.5 km)
    e_walk = Edge("Hotel", "BusStop1", GraphMode.WALKING, attributes={"distance_km": 0.5, "source_id": "walk_1"})
    # 2. Bus to TrainStation1 (3.0 km)
    e_bus = Edge("BusStop1", "TrainStation1", GraphMode.BUS, attributes={"distance_km": 3.0, "source_id": "bus_2"})
    # 3. Transfer link at station (0.1 km)
    e_trans = Edge("TrainStation1", "TrainStation2", GraphMode.TRANSFER, attributes={"distance_km": 0.1, "source_id": "trans_3"})
    # 4. Rail to Destination (15.0 km)
    e_rail = Edge("TrainStation2", "Destination", GraphMode.RAIL, attributes={"distance_km": 15.0, "source_id": "rail_4"})
    
    for e in [e_walk, e_bus, e_trans, e_rail]:
        graph.add_edge(e)
        
    router = DijkstraRouter(graph)
    result = router.route("Hotel", "Destination")
    
    assert result.nodes == ["Hotel", "BusStop1", "TrainStation1", "TrainStation2", "Destination"]
    assert len(result.edges) == 4
    modes = [edge.mode for edge in result.edges]
    assert modes == [GraphMode.WALKING, GraphMode.BUS, GraphMode.TRANSFER, GraphMode.RAIL]
    assert pytest.approx(result.total_distance_km, 1e-4) == 18.6

def test_source_graph_immutability():
    graph = MultimodalGraph()
    graph.add_node(Node("A"))
    graph.add_node(Node("B"))
    graph.add_edge(Edge("A", "B", GraphMode.ROAD, attributes={"distance_km": 5.0}))
    
    # Snapshot nodes and edges before route calculation
    nodes_before = list(graph.nodes.keys())
    edges_before = len(graph.edges["A"]["B"])
    
    router = DijkstraRouter(graph)
    _ = router.route("A", "B")
    
    assert list(graph.nodes.keys()) == nodes_before
    assert len(graph.edges["A"]["B"]) == edges_before
