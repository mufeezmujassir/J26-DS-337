from pydantic import BaseModel, Field
from typing import Optional, List

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

class DijkstraRouteRequest(BaseModel):
    origin: Optional[Coordinate] = None
    destination: Optional[Coordinate] = None
    origin_node_id: Optional[str] = None
    destination_node_id: Optional[str] = None
    max_snap_distance_km: float = Field(default=25.0, ge=0.1, le=100.0)

class RouteEdgeResponse(BaseModel):
    from_node: str
    to_node: str
    mode: str
    distance_km: Optional[float] = None
    travel_time_min: Optional[float] = None
    cost_lkr: Optional[float] = None
    source_id: Optional[str] = None
    source_dataset: Optional[str] = None
    is_estimated: bool = False

class DijkstraRouteResponse(BaseModel):
    origin_node: str
    destination_node: str
    total_distance_km: float
    nodes: List[str]
    nodes_count: int
    edges_count: int
    modes_used: List[str]
    transfers_count: int
    total_travel_time_min: Optional[float] = None
    travel_time_complete: bool
    total_cost_lkr: Optional[float] = None
    cost_complete: bool
    warnings: List[str]
    edges: List[RouteEdgeResponse]
    source: str = "local_dijkstra"
