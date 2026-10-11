import pytest
import httpx
from app.schemas.route import RouteRequest, Coordinate
from app.services.route_api_client import RouteAPIClient
from app.services.route_validation import RouteValidationService

def test_coordinate_validation():
    with pytest.raises(ValueError):
        Coordinate(latitude=100.0, longitude=0.0)
    with pytest.raises(ValueError):
        Coordinate(latitude=0.0, longitude=200.0)
    
    valid = Coordinate(latitude=6.9271, longitude=79.8612)
    assert valid.latitude == 6.9271

@pytest.mark.asyncio
async def test_route_api_timeout(mocker):
    mocker.patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout"))
    
    client = RouteAPIClient()
    req = RouteRequest(
        origin=Coordinate(latitude=6.9271, longitude=79.8612),
        destination=Coordinate(latitude=7.2906, longitude=80.6337)
    )
    result = await client.get_route(req)
    
    assert result.source == "route_api_timeout"

@pytest.mark.asyncio
async def test_route_api_success_and_validation(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "routes": [{
            "summary": {
                "distance": 115000, # meters
                "duration": 7200
            },
            "geometry": "encodedpolyline"
        }]
    }
    mocker.patch("httpx.AsyncClient.post", return_value=mock_response)
    
    validator = RouteValidationService()
    req = RouteRequest(
        origin=Coordinate(latitude=6.9271, longitude=79.8612),
        destination=Coordinate(latitude=7.2906, longitude=80.6337)
    )
    result = await validator.validate_route(req, local_distance_km=116.0)
    
    assert result.source == "route_api"
    assert result.distance == 115.0 # converted to km
    assert result.duration == 7200
    assert result.geometry == "encodedpolyline"
    
@pytest.mark.asyncio
async def test_route_api_fallback(mocker):
    mocker.patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("No connection"))
    
    validator = RouteValidationService()
    req = RouteRequest(
        origin=Coordinate(latitude=6.0, longitude=80.0),
        destination=Coordinate(latitude=7.0, longitude=81.0)
    )
    result = await validator.validate_route(req, local_distance_km=150.0, local_duration=10000.0)
    
    assert result.source == "local_database_fallback"
    assert result.distance == 150.0
    assert result.duration == 10000.0
    assert result.geometry is None
