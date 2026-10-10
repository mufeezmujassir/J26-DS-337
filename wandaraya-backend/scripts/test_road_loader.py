import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.graph import MultimodalGraph, GraphMode
from app.services.road_graph_loader import RoadGraphLoader

@pytest.mark.asyncio
async def test_road_graph_loader():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Mock data: r_id, length, slon, slat, elon, elat
    mock_result.fetchall.return_value = [
        ("r1", 1.5, 79.8, 6.9, 79.9, 7.0),
        ("r2", None, 79.9, 7.0, 80.0, 7.1),
        ("inv", 1.0, None, 6.9, 80.0, 7.1) # should be skipped
    ]
    mock_session.execute.return_value = mock_result
    
    graph = MultimodalGraph()
    loader = RoadGraphLoader(mock_session, graph)
    
    loaded = await loader.load()
    
    assert loaded == 2
    
    stats = graph.get_statistics()
    assert stats["total_nodes"] == 3
    # 2 undirected edges meaning 4 unidirectional internal edges
    assert stats["edges_by_mode"][GraphMode.ROAD] == 4
    
    # Verify edge attributes
    edges = graph.get_edges("road_79.8_6.9", "road_79.9_7.0")
    assert len(edges) == 1
    assert edges[0].attributes["distance_km"] == 1.5
    assert edges[0].attributes["source_id"] == "r1"
    
    edges_r2 = graph.get_edges("road_79.9_7.0", "road_80.0_7.1")
    assert edges_r2[0].attributes["distance_km"] == 0.0
