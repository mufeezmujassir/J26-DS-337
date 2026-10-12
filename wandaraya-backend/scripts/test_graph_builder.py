import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.graph_builder import MultimodalGraphBuilder

@pytest.mark.asyncio
async def test_graph_builder_caching():
    builder = MultimodalGraphBuilder()
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    
    graph1 = await builder.build(mock_session)
    
    # Second build should return cached reference without executing queries
    mock_session.reset_mock()
    graph2 = await builder.build(mock_session)
    
    assert graph1 is graph2
    mock_session.execute.assert_not_called()
    
    # Third build with force_reload should execute queries
    graph3 = await builder.build(mock_session, force_reload=True)
    assert graph3 is not graph1
    assert mock_session.execute.called
