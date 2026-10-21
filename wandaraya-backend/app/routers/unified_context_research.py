from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.recommendation.unified_context.orchestrator import (
    UnifiedContextEngineDisabled,
    UnifiedContextOrchestrator,
)
from app.recommendation.unified_context.schemas import UnifiedContextRequest, UnifiedContextResponse

router = APIRouter(prefix="/api/v1/research/recommendations", tags=["Research: Unified Context"])


@router.post("/context-aware", response_model=UnifiedContextResponse)
async def context_aware_recommendations(
    payload: UnifiedContextRequest,
    x_research_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_UNIFIED_CONTEXT_RESEARCH_API:
        raise HTTPException(status_code=503, detail="The Stage 12.5 research API is disabled.")
    configured = settings.UNIFIED_CONTEXT_RESEARCH_API_TOKEN or settings.AIRFLOW_API_TOKEN
    if len(configured) < 32:
        raise HTTPException(status_code=503, detail="Research API authentication is not configured.")
    if x_research_token is None or not secrets.compare_digest(
        x_research_token.encode("utf-8"), configured.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    try:
        return await UnifiedContextOrchestrator(db).recommend(payload)
    except UnifiedContextEngineDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
