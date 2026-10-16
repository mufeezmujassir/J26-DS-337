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
    objective: str = Field(default="shortest", description="Routing objective: 'shortest'/'distance', 'fastest'/'time', 'cheapest'/'cost', 'slower'/'leisurely', 'scenic'/'picturesque'")

class RouteEdgeResponse(BaseModel):
    from_node: str
    to_node: str
    mode: str
    distance_km: Optional[float] = None
    travel_time_min: Optional[float] = None
    cost_lkr: Optional[float] = None
    waiting_time_min: Optional[float] = None
    transfer_time_min: Optional[float] = None
    transfer_type: Optional[str] = None
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
    mode_sequence: List[str] = Field(default_factory=list)
    mode_changes_count: int = 0
    transfers_count: int
    transfer_locations: List[str] = Field(default_factory=list)
    total_travel_time_min: Optional[float] = None
    travel_time_complete: bool
    known_travel_time_min: Optional[float] = None
    total_waiting_time_min: Optional[float] = 0.0
    total_transfer_time_min: Optional[float] = 0.0
    total_journey_time_min: Optional[float] = None
    journey_time_complete: bool = True
    is_travel_time_estimated: bool = False
    total_cost_lkr: Optional[float] = None
    cost_complete: bool
    known_cost_lkr: Optional[float] = None
    is_cost_estimated: bool = False
    objective: str = "distance"
    optimized_weight: Optional[float] = None
    warnings: List[str]
    edges: List[RouteEdgeResponse]
    source: str = "local_dijkstra"
