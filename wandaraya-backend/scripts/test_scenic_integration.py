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
