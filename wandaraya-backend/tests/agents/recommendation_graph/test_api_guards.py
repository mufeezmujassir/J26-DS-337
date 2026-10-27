import pytest
from fastapi import HTTPException

from app.agents.recommendation_graph.schemas.graph_request import AgenticRecommendationRequest
from app.config import settings
from app.routers.langgraph_recommendations import agentic_context_aware_recommendations


@pytest.mark.asyncio
async def test_agent_api_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE", False)
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_RESEARCH_API", False)
    with pytest.raises(HTTPException) as raised:
        await agentic_context_aware_recommendations(
            AgenticRecommendationRequest(session_id="guard-001", message="Visit Kandy tomorrow morning"),
            x_research_token=None, x_research_owner=None, db=None,
        )
    assert raised.value.status_code == 503


@pytest.mark.asyncio
async def test_agent_api_requires_dedicated_token(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE", True)
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_RESEARCH_API", True)
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_PRODUCTION_ROUTING", False)
    monkeypatch.setattr(settings, "ALLOW_LOCAL_DEVELOPMENT_RESEARCH_ACCESS", False)
    monkeypatch.setattr(settings, "LANGGRAPH_RESEARCH_API_TOKEN", "x" * 32)
    with pytest.raises(HTTPException) as raised:
        await agentic_context_aware_recommendations(
            AgenticRecommendationRequest(session_id="guard-002", message="Visit Kandy tomorrow morning"),
            x_research_token="wrong", x_research_owner="owner", db=None,
        )
    assert raised.value.status_code == 401


@pytest.mark.asyncio
async def test_agent_api_local_development_access_is_explicit(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE", True)
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_RESEARCH_API", True)
    monkeypatch.setattr(settings, "ENABLE_LANGGRAPH_PRODUCTION_ROUTING", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LOCAL_DEVELOPMENT_RESEARCH_ACCESS", True)
    monkeypatch.setattr(settings, "LANGGRAPH_RESEARCH_API_TOKEN", "")

    with pytest.raises(HTTPException) as raised:
        await agentic_context_aware_recommendations(
            AgenticRecommendationRequest(session_id="guard-003", message="Visit Kandy tomorrow morning"),
            x_research_token=None, x_research_owner="owner", db=None,
        )

    assert raised.value.status_code == 503
