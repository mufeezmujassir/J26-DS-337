import pytest
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter

@pytest.fixture
def multimodal_network():
    """
    Constructs a realistic multimodal network adhering to Step 3 graph topology:
    - Pure Road network corridor
    - Bus routes with directed schedule lines
    - Railway segments with directed transit lines
    - Walking transfer links connecting stations and road nodes
    - Isolated network component
    """
    g = MultimodalGraph()

    # Pure road nodes
    g.add_node(Node("highway_a", lat=6.800, lon=79.800))
    g.add_node(Node("highway_b", lat=6.820, lon=79.820))
    g.add_node(Node("highway_c", lat=6.840, lon=79.840))
    g.add_edge(Edge("highway_a", "highway_b", GraphMode.ROAD, directed=False, attributes={"distance_km": 3.0}))
    g.add_edge(Edge("highway_b", "highway_c", GraphMode.ROAD, directed=False, attributes={"distance_km": 4.5}))

    # Multimodal corridor nodes
    g.add_node(Node("home_road", lat=6.900, lon=79.850))
    g.add_node(Node("bus_stop_alpha", lat=6.902, lon=79.852))
    g.add_node(Node("bus_stop_beta", lat=6.915, lon=79.860))
    g.add_node(Node("station_junction_road", lat=6.920, lon=79.865))
    g.add_node(Node("station_central", lat=6.922, lon=79.866))
    g.add_node(Node("station_terminal", lat=6.940, lon=79.870))
    g.add_node(Node("office_road", lat=6.942, lon=79.872))

    # Dedicated directed transit segment without road bypass
    g.add_node(Node("rural_train_origin", lat=7.000, lon=80.000))
    g.add_node(Node("rural_train_dest", lat=7.050, lon=80.050))
    g.add_edge(Edge("rural_train_origin", "rural_train_dest", GraphMode.RAIL, directed=True, attributes={"distance_km": 5.0}))

    # Disjoint network (e.g., offshore island)
    g.add_node(Node("island_node_1", lat=6.000, lon=80.000))
    g.add_node(Node("island_node_2", lat=6.010, lon=80.010))
    g.add_edge(Edge("island_node_1", "island_node_2", GraphMode.ROAD, directed=False, attributes={"distance_km": 1.2}))

    # Multimodal edges:
    # 1. Walking: Home -> Bus Stop Alpha (0.3 km)
    g.add_edge(Edge(
        "home_road", "bus_stop_alpha", GraphMode.WALKING,
        directed=False,
        attributes={"distance_km": 0.3}
    ))
    
    # 2. Directed Bus: Alpha -> Beta (1.8 km), Beta -> Station Junction (0.9 km)
    g.add_edge(Edge(
        "bus_stop_alpha", "bus_stop_beta", GraphMode.BUS,
        directed=True,
        attributes={"distance_km": 1.8}
    ))
    g.add_edge(Edge(
        "bus_stop_beta", "station_junction_road", GraphMode.BUS,
        directed=True,
        attributes={"distance_km": 0.9}
    ))

    # 3. Intermodal Transfer: Station Junction Road <-> Station Central (0.2 km)
    g.add_edge(Edge(
        "station_junction_road", "station_central", GraphMode.TRANSFER,
        directed=False,
        attributes={"distance_km": 0.2, "transfer_type": "road_to_rail"}
    ))

    # 4. Directed Railway: Central -> Terminal (3.5 km)
    g.add_edge(Edge(
        "station_central", "station_terminal", GraphMode.RAIL,
        directed=True,
        attributes={"distance_km": 3.5}
    ))

    # 5. Walking: Terminal -> Office (0.4 km)
    g.add_edge(Edge(
        "station_terminal", "office_road", GraphMode.WALKING,
        directed=False,
        attributes={"distance_km": 0.4}
    ))

    # 6. Slower/Longer Road bypass from Home to Office:
    # Home -> Junction (4.5 km) -> Office (6.0 km) = 10.5 km (multimodal path is 7.1 km)
    g.add_edge(Edge("home_road", "station_junction_road", GraphMode.ROAD, directed=False, attributes={"distance_km": 4.5}))
    g.add_edge(Edge("station_junction_road", "office_road", GraphMode.ROAD, directed=False, attributes={"distance_km": 6.0}))

    return g

def test_single_mode_road_routing(multimodal_network):
    router = DijkstraRouter(multimodal_network)
    result = router.route("highway_a", "highway_c")
    
    assert result.nodes == ["highway_a", "highway_b", "highway_c"]
    assert result.modes_used == ["road"]
    assert pytest.approx(result.total_distance_km, 1e-4) == 7.5
    assert result.transfers_count == 0

def test_single_mode_bus_routing(multimodal_network):
    router = DijkstraRouter(multimodal_network)
    result = router.route("bus_stop_alpha", "station_junction_road")
    
    assert result.modes_used == ["bus"]
    assert pytest.approx(result.total_distance_km, 1e-4) == 2.7
    assert result.transfers_count == 0
    assert result.nodes == ["bus_stop_alpha", "bus_stop_beta", "station_junction_road"]

def test_single_mode_railway_routing(multimodal_network):
    router = DijkstraRouter(multimodal_network)
    result = router.route("station_central", "station_terminal")
    
    assert result.modes_used == ["rail"]
    assert pytest.approx(result.total_distance_km, 1e-4) == 3.5
    assert result.transfers_count == 0
    assert result.nodes == ["station_central", "station_terminal"]

def test_single_mode_walking_routing(multimodal_network):
    router = DijkstraRouter(multimodal_network)
    result = router.route("home_road", "bus_stop_alpha")
    
    assert result.modes_used == ["walking"]
    assert pytest.approx(result.total_distance_km, 1e-4) == 0.3
    assert result.transfers_count == 0

def test_multimodal_walk_bus_transfer_rail_walk(multimodal_network):
    """
    Tests complete journey from home_road to office_road:
    Walk (0.3) -> Bus (1.8 + 0.9) -> Transfer (0.2) -> Rail (3.5) -> Walk (0.4)
    Total multimodal distance = 7.1 km (shorter than road bypass which is 10.5 km).
    """
    router = DijkstraRouter(multimodal_network)
    result = router.route("home_road", "office_road")
    
    assert result.nodes == [
        "home_road",
        "bus_stop_alpha",
        "bus_stop_beta",
        "station_junction_road",
        "station_central",
        "station_terminal",
        "office_road"
    ]
    assert pytest.approx(result.total_distance_km, 1e-4) == 7.1
    assert result.modes_used == ["walking", "bus", "transfer", "rail"]
    # Transfers count:
    # walking -> bus (+1)
    # bus -> transfer (+1 at transfer edge)
    # transfer -> rail (same transfer bridge)
    # rail -> walking (+1)
    # Total = 3
    assert result.transfers_count == 3
    assert len(result.edges) == 6

def test_directed_public_transit_cannot_be_traversed_backward(multimodal_network):
    """
    Railway from rural_train_origin -> rural_train_dest is strictly directed.
    Going backward dest -> origin has no valid reverse edge.
    """
    router = DijkstraRouter(multimodal_network)
    
    with pytest.raises(ValueError) as exc:
        router.route("rural_train_dest", "rural_train_origin")
    assert "unreachable" in str(exc.value).lower()

def test_disjoint_network_returns_unreachable(multimodal_network):
    """
    Origin in main city network, destination on isolated island network.
    Must raise unreachable ValueError without inventing fictitious connections.
    """
    router = DijkstraRouter(multimodal_network)
    
    with pytest.raises(ValueError) as exc:
        router.route("home_road", "island_node_1")
    assert "unreachable" in str(exc.value).lower()
