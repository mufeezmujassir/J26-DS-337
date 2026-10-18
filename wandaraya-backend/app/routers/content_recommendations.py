"""Read-only Stage 12.1 content-based recommendation API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.recommendation.content_based.schemas import (
    ContentBasedRecommendationRequest,
    ContentBasedRecommendationResponse,
)
from app.recommendation.content_based.service import ContentBasedRecommendationService


router = APIRouter(prefix="/api/v1/recommendations", tags=["Content-Based Recommendations"])


@router.post("/content-based", response_model=ContentBasedRecommendationResponse)
async def content_based_recommendations(
    payload: ContentBasedRecommendationRequest,
    db: AsyncSession = Depends(get_db),
) -> ContentBasedRecommendationResponse:
    """Rank semantic candidates with verified attraction metadata.

    This route is read-only and intentionally does not apply weather or any of
    the future contextual re-ranking dimensions.
    """
    try:
        return await ContentBasedRecommendationService(db=db).recommend(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Content recommendation retrieval is temporarily unavailable.",
        ) from exc
