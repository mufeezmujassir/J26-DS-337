from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.recommendation_graph.schemas.graph_request import AgenticRecommendationRequest
from app.agents.recommendation_graph.schemas.graph_response import AgenticRecommendationResponse
from app.agents.recommendation_graph.services.graph_service import RecommendationGraphService
from app.agents.recommendation_graph.services.checkpoint_service import (
    DevelopmentCheckpointService, SessionOwnershipError,
)
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/api/v1/research/agents", tags=["Research: LangGraph Recommendations"])
_checkpoints = DevelopmentCheckpointService(settings.LANGGRAPH_SESSION_TTL_SECONDS)
_service = RecommendationGraphService(_checkpoints)


@router.post("/context-aware", response_model=AgenticRecommendationResponse)
async def agentic_context_aware_recommendations(
    payload: AgenticRecommendationRequest,
    x_research_token: str | None = Header(default=None),
    x_research_owner: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE or not settings.ENABLE_LANGGRAPH_RESEARCH_API:
        raise HTTPException(status_code=503, detail="The Stage 12.6 LangGraph research API is disabled.")
    if settings.ENABLE_LANGGRAPH_PRODUCTION_ROUTING:
        raise HTTPException(status_code=503, detail="Production routing is prohibited for this research workflow.")
    local_development_access = (
        settings.ENVIRONMENT.lower() == "development"
        and settings.ALLOW_LOCAL_DEVELOPMENT_RESEARCH_ACCESS
    )
    if not local_development_access:
        configured = settings.LANGGRAPH_RESEARCH_API_TOKEN
        if len(configured) < 32:
            raise HTTPException(status_code=503, detail="LangGraph research API authentication is not configured.")
        if x_research_token is None or not secrets.compare_digest(x_research_token, configured):
            raise HTTPException(status_code=401, detail="Unauthorized.")
    if x_research_owner is None or not x_research_owner.strip():
        raise HTTPException(status_code=400, detail="X-Research-Owner is required for session isolation.")
    try:
        return await _service.execute(db, payload, x_research_owner)
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="The research graph exceeded its execution timeout.") from exc
    except asyncio.CancelledError:
        raise
