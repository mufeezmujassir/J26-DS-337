import pytest
from app.services.graph import Edge, GraphMode

def test_standard_edge_attributes():
    # Test that missing values are represented explicitly
    edge = Edge("A", "B", GraphMode.ROAD)
    attrs = edge.attributes
    assert attrs["distance_km"] is None
    assert attrs["cost_lkr"] is None
    assert attrs["source_id"] is None
    
    # Test preservation of sourced values and estimation flags
    edge2 = Edge(
        "A", "B", 
        GraphMode.BUS, 
        attributes={
            "distance_km": 1.2, 
            "cost_lkr": 50.0, 
            "is_estimated": True, 
            "travel_time_min": 15
        }
    )
    attrs2 = edge2.attributes
    assert attrs2["distance_km"] == 1.2
    assert attrs2["cost_lkr"] == 50.0
    assert attrs2["is_estimated"] is True
    assert attrs2["travel_time_min"] == 15
    assert attrs2["source_dataset"] is None
