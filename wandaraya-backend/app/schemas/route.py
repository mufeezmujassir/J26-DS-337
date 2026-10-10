from pydantic import BaseModel, Field

class Coordinate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate

class RouteResult(BaseModel):
    distance: float | None = None
    duration: float | None = None
    geometry: str | None = None
    source: str
