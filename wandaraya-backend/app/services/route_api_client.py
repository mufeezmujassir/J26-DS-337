import httpx
import logging
from app.config import settings
from app.schemas.route import RouteRequest, RouteResult

logger = logging.getLogger(__name__)

class RouteAPIClient:
    def __init__(self):
        self.base_url = settings.ROUTE_API_BASE_URL.rstrip("/")
        self.api_key = settings.ROUTE_API_KEY
        # OpenRouteService driving-car endpoint format
        self.endpoint = f"{self.base_url}/v2/directions/driving-car"

    async def get_route(self, request: RouteRequest) -> RouteResult:
        if not self.api_key:
            logger.error("ROUTE_API_KEY is not configured.")
            return RouteResult(source="route_api_unavailable")

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        
        # ORS expects coordinates in [longitude, latitude] format
        body = {
            "coordinates": [
                [request.origin.longitude, request.origin.latitude],
                [request.destination.longitude, request.destination.latitude]
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                logger.info(f"Route API Request Started for ({request.origin.latitude}, {request.origin.longitude}) to ({request.destination.latitude}, {request.destination.longitude})")
                response = await client.post(self.endpoint, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"Route API Request Completed. Status: {response.status_code}")
                
                # Parse normalized fields from ORS response
                distance = None
                duration = None
                geometry = None
                
                if "routes" in data and len(data["routes"]) > 0:
                    route = data["routes"][0]
                    distance = route["summary"].get("distance")
                    # Convert distance from meters to km
                    if distance is not None:
                        distance = distance / 1000.0
                    
                    duration = route["summary"].get("duration")
                    geometry = route.get("geometry")
                
                return RouteResult(
                    distance=distance,
                    duration=duration,
                    geometry=geometry,
                    source="route_api"
                )
        
        except httpx.TimeoutException:
            logger.warning("Route API request timed out.")
            return RouteResult(source="route_api_timeout")
        except httpx.RequestError as exc:
            logger.error(f"Route API connection failure: {exc}")
            return RouteResult(source="route_api_error")
        except httpx.HTTPStatusError as exc:
            logger.error(f"Route API HTTP error: {exc.response.status_code}")
            return RouteResult(source="route_api_http_error")
        except Exception as exc:
            logger.error(f"Route API unexpected error: {exc}")
            return RouteResult(source="route_api_invalid_response")
