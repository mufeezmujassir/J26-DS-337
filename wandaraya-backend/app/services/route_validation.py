import logging
from typing import Dict, Any, Optional

from app.schemas.route import RouteRequest, RouteResult
from app.services.route_api_client import RouteAPIClient

logger = logging.getLogger(__name__)

class RouteValidationService:
    def __init__(self):
        self.api_client = RouteAPIClient()

    def validate_distance(self, local_distance_km: float, api_distance_km: float) -> Dict[str, Any]:
        """
        Reusable distance comparison function.
        Calculates absolute difference and percentage difference.
        """
        absolute_difference = abs(local_distance_km - api_distance_km)
        percentage_difference = None
        
        if local_distance_km > 0:
            percentage_difference = (absolute_difference / local_distance_km) * 100.0
            
        return {
            "local_distance": local_distance_km,
            "api_distance": api_distance_km,
            "absolute_difference": absolute_difference,
            "percentage_difference": percentage_difference
        }

    async def validate_route(self, request: RouteRequest, local_distance_km: Optional[float] = None, local_duration: Optional[float] = None) -> RouteResult:
        """
        Validates road-routing information using the Route API.
        Implements safe fallback to use local data if API is unavailable.
        DOES NOT modify the local database.
        """
        api_result = await self.api_client.get_route(request)
        
        # Validating Distance
        if api_result.distance is not None and local_distance_km is not None:
            comparison = self.validate_distance(local_distance_km, api_result.distance)
            logger.info(f"Distance Validation: {comparison}")

        # Validating Travel Time
        if api_result.duration is not None and local_duration is not None:
            diff = abs(local_duration - api_result.duration)
            logger.info(f"Travel Time Validation: Local={local_duration}, API={api_result.duration}, Diff={diff}")
        elif local_duration is None:
            logger.info("Travel Time Validation: Local travel-time value unavailable.")
            
        # Geometry Validation
        if api_result.geometry:
            logger.info("Geometry Validation: Geometry successfully retrieved and parsed from API.")
            
        # Fallback Handling
        if api_result.source in ["route_api_timeout", "route_api_error", "route_api_http_error", "route_api_invalid_response", "route_api_unavailable"]:
            logger.warning(f"Route API failed with source: {api_result.source}. Checking local data fallback.")
            if local_distance_km is not None:
                logger.info("Fallback: Reverting to local validated distance.")
                return RouteResult(
                    distance=local_distance_km,
                    duration=local_duration,
                    geometry=None, # Missing geometry fallback usually requires a PostGIS ST_AsGeoJSON call outside this scope
                    source="local_database_fallback"
                )
            else:
                logger.error("Fallback: Local distance data unavailable. Returning error state.")
        
        return api_result
