from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.schemas.route import RouteRequest, RouteResult
from app.services.route_validation import RouteValidationService

router = APIRouter()
route_validation_service = RouteValidationService()

class RouteValidationRequest(BaseModel):
    request: RouteRequest
    local_distance_km: Optional[float] = None
    local_duration: Optional[float] = None

@router.post("/route/validate", response_model=RouteResult)
async def validate_route(payload: RouteValidationRequest):
    """
    Test endpoint for validation and fallback logic.
    Does NOT modify the database.
    """
    result = await route_validation_service.validate_route(
        request=payload.request,
        local_distance_km=payload.local_distance_km,
        local_duration=payload.local_duration
    )
    return result
