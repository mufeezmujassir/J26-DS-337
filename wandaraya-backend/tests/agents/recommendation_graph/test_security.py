import pytest

from app.agents.recommendation_graph.services.checkpoint_service import (
    DevelopmentCheckpointService, SessionOwnershipError,
)


@pytest.mark.asyncio
async def test_session_is_bound_to_owner():
    service = DevelopmentCheckpointService(3600)
    await service.claim("session-abc", "researcher-a")
    with pytest.raises(SessionOwnershipError):
        await service.claim("session-abc", "researcher-b")
