import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.graph import MultimodalGraph, Node, GraphMode
from app.services.station_loader import StationGraphLoader
from app.services.transfer_loader import build_transfers

@pytest.mark.asyncio
async def test_station_and_transfers():
    graph = MultimodalGraph()
    # Add a mock road node
    graph.add_node(Node(node_id="road_79.8_6.9", lat=6.9, lon=79.8))
    
    mock_session = AsyncMock()
    class MockStation:
        def __init__(self, id, lat, lon):
            self.id=id; self.lat=lat; self.lon=lon
            self.name="Test Station"; self.osm_id="osm1"; self.type="station"
            
    # Station slightly offset from road_79.8_6.9
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MockStation(id=1, lat=6.902, lon=79.802),  # Valid, close
        MockStation(id=2, lat=9.000, lon=80.000)   # Too far
    ]
    mock_session.execute.return_value = mock_result
    
    loader = StationGraphLoader(mock_session, graph)
    await loader.load()
    
    stats = graph.get_statistics()
    assert stats["total_nodes"] == 3 # 1 road + 2 stations
    
    added = build_transfers(graph, max_walk_km=1.0)
    
    # 2 nodes, 1 transfer built (undirected)
    assert added == 1
    stats = graph.get_statistics()
    # Undirected edges register as 2 directed edges internally for the adjacency list
    assert stats["edges_by_mode"][GraphMode.WALKING] == 2
    
    # Check attributes of the transfer
    edges = graph.get_edges("station_1", "road_79.8_6.9")
    assert len(edges) == 1
    assert "distance_km" in edges[0].attributes
    assert edges[0].attributes["transfer_type"] == "station_to_road"
