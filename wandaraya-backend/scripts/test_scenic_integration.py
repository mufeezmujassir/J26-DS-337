import pytest
from app.services.graph import MultimodalGraph, Node
from app.services.scenic_integration import associate_scenic_places

class MockScenicPlace:
    def __init__(self, lat, lon, name, category, ptype):
        self.latitude = lat
        self.longitude = lon
        self.name = name
        self.category = category
        self.type = ptype

def test_scenic_integration():
    graph = MultimodalGraph()
    graph.add_node(Node(node_id="n1", lat=7.0, lon=80.0))
    graph.add_node(Node(node_id="n2", lat=7.5, lon=80.5))
    
    places = [
        # Close to n1 (should associate)
        MockScenicPlace(7.001, 80.001, "Lake", "Nature", "Waterbody"),
        # Too far from any node (> 1.0 km threshold)
        MockScenicPlace(6.0, 79.0, "Far Place", "Unknown", None)
    ]
    
    assoc = associate_scenic_places(graph, places, max_dist_km=1.0)
    
    assert assoc == 1
    
    node1 = graph.get_node("n1")
    assert "scenic_places" in node1.properties
    assert len(node1.properties["scenic_places"]) == 1
    
    meta = node1.properties["scenic_places"][0]
    assert meta["name"] == "Lake"
    assert meta["source_dataset"] == "scenic_places"
    assert meta["original_type"] == "Waterbody"
    assert meta["distance_km"] < 1.0

def test_scenic_service_corridor_scoring():
    from app.services.scenic_service import scenic_service
    # Test high-scenic corridor (Kandy to Ella hill country)
    coords = [(7.2906, 80.6337), (6.9497, 80.7891), (6.8667, 81.0466)]
    res = scenic_service.calculate_scenic_score(coords, total_distance_km=140.0, corridor_radius_km=10.0)
    assert res["scenic_score"] >= 50
    assert "scenic_rating" in res
    assert res["total_scenic_places"] > 0
    assert isinstance(res["scenic_places"], list)

def test_rail_graph_loader_official_fares():
    from app.services.rail_graph_loader import rail_graph_loader
    # Test official Sri Lanka Railways tariffs
    fare = rail_graph_loader.get_fare("Colombo Fort", "Badulla")
    assert fare["3rd_class_rs"] == 460.0
    assert fare["2nd_class_rs"] == 900.0
    assert fare["1st_class_rs"] == 1800.0
    assert fare["distance_km"] > 250.0

    fare_jaffna = rail_graph_loader.get_fare("Colombo Fort", "Jaffna")
    assert fare_jaffna["3rd_class_rs"] == 580.0
    assert fare_jaffna["2nd_class_rs"] == 1150.0
    assert fare_jaffna["1st_class_rs"] == 2250.0
