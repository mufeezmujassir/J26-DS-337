# Route API Integration

"The Route API is used as a supporting road-routing/data-validation service and is not the proposed RAGRO optimization algorithm."

## Purpose
The external Route API is designed to validate and enrich our local road network lengths and geometries for Component 2 (Environmental-Risk-Aware Multimodal Route Optimization). It allows us to cross-check distances and durations from our static dataset before constructing the multimodal transportation graph.

## Configuration & Usage
This platform uses OpenRouteService (ORS) as the primary provider. 

### Environment Variables
Set the following variables in `.env`:
- `ROUTE_API_BASE_URL`: The API URL (e.g., `https://api.openrouteservice.org`)
- `ROUTE_API_KEY`: A valid API credentials key for ORS. Do NOT commit the `.env` file nor expose this key publicly.

## System Architecture

### Request Structure
We submit route requests mapped via the `RouteRequest` schema. This strictly enforces validation limits on Geographic Coordinates:
- Latitude: between -90 to 90
- Longitude: between -180 to 180

### Normalized Response
Responses are handled by `RouteAPIClient` and stripped of provider-specific formatting, and converted into our generalized `RouteResult`. It captures:
- `distance` (float in km, normalized from meters)
- `duration` (float in seconds)
- `geometry` (the mapped polyline string)
- `source` (provider identifier or fallback identifier).

## Validation Logic
Our `validate_distance` utility compares `local_distance` from our `Road` tables against the `api_distance`. It evaluates both the absolute delta and the percentage difference. 
We report the discrepancy cleanly using `logging` mechanisms without overwriting database schemas automatically, enforcing a Read-Only validation approach. Travel times are handled similarly.

## Fallback Behavior
The core application will not crash if the routing provider becomes unavailable. Common HTTPS errors such as timeout, connection failure, 4xx/5xx are suppressed in `route_api_client.py` natively.
If encountering these, the validation routines seamlessly resort to `local_database_fallback` values (reusing static `total_length_km`) preventing downstream graphs from breaking.

## Testing
Development workflows incorporate `pytest`. See `tests/test_route_api.py`.
Tests aggressively mock HTTpx responses rather than invoking live ORS integrations to bypass billing concerns and increase test robustness. Tests assert validation edge cases, request constraints, timeout hooks, parsing reliability, and standard fallbacks logic functionality. 

## Known Limitations
- Does not modify existing PostGIS geometry schemas yet.
- Test endpoints (`/api/route/validate`) are not production ready for public traffic. They exist for developer validation.
