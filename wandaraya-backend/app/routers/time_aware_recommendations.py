from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.recommendation.time_context.schemas import TimeAwareRecommendationRequest, TimeAwareResponse
from app.recommendation.time_context.service import TimeAwareRecommendationService

router = APIRouter(prefix="/api/v1/recommendations", tags=["Time-Aware Recommendations"])


@router.post("/time-aware", response_model=TimeAwareResponse)
async def time_aware_recommendations(payload: TimeAwareRecommendationRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await TimeAwareRecommendationService(db).recommend(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Time-aware recommendation retrieval is temporarily unavailable.") from exc
