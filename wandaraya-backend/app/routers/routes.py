import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.schemas.route import (
    DijkstraRouteRequest,
    DijkstraRouteResponse,
    RouteEdgeResponse,
)
from app.services.graph import MultimodalGraph
from app.services.graph_builder import graph_builder
from app.services.dijkstra import DijkstraRouter
from app.services.spatial import find_nearest_routable_node

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Routes"])

async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session

async def get_multimodal_graph(session: AsyncSession = Depends(get_db_session)) -> MultimodalGraph:
    """
    Returns the multimodal graph instance.
    Cached in-memory by graph_builder to prevent rebuilding on every request.
    """
    return await graph_builder.build(session, force_reload=False)

@router.post("/routes/dijkstra", response_model=DijkstraRouteResponse)
@router.post("/api/routes/dijkstra", response_model=DijkstraRouteResponse, include_in_schema=False)
async def calculate_dijkstra_route(
    payload: DijkstraRouteRequest,
    graph: MultimodalGraph = Depends(get_multimodal_graph)
) -> DijkstraRouteResponse:
    """
    Calculates the shortest multimodal route using the local Dijkstra baseline.
    Maps geographic coordinates to nearest routable graph nodes using Haversine distance.
    Returns ordered path, mode sequences, transfers count, and distance metadata.
    """
    # 1. Validate request parameters
    has_origin_coord = payload.origin is not None
    has_origin_id = bool(payload.origin_node_id and payload.origin_node_id.strip())
    if not has_origin_coord and not has_origin_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either origin coordinates or origin_node_id must be provided."
        )

    has_dest_coord = payload.destination is not None
    has_dest_id = bool(payload.destination_node_id and payload.destination_node_id.strip())
    if not has_dest_coord and not has_dest_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either destination coordinates or destination_node_id must be provided."
        )

    # 2. Check graph availability
    if not graph.nodes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transport graph is empty or not yet loaded from data sources."
        )

    # 3. Resolve origin node
    origin_node = None
    if has_origin_id:
        if payload.origin_node_id in graph.nodes:
            origin_node = payload.origin_node_id
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Origin node '{payload.origin_node_id}' does not exist in graph."
            )
    else:
        origin_node, dist_km = find_nearest_routable_node(
            graph,
            lat=payload.origin.latitude,
            lon=payload.origin.longitude,
            direction="outgoing",
            max_radius_km=payload.max_snap_distance_km
        )
        if origin_node is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Origin location ({payload.origin.latitude}, {payload.origin.longitude}) "
                       f"is outside graph coverage area (no connected node within {payload.max_snap_distance_km} km)."
            )

    # 4. Resolve destination node
    dest_node = None
    if has_dest_id:
        if payload.destination_node_id in graph.nodes:
            dest_node = payload.destination_node_id
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination node '{payload.destination_node_id}' does not exist in graph."
            )
    else:
        dest_node, dist_km = find_nearest_routable_node(
            graph,
            lat=payload.destination.latitude,
            lon=payload.destination.longitude,
            direction="incoming",
            max_radius_km=payload.max_snap_distance_km
        )
        if dest_node is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Destination location ({payload.destination.latitude}, {payload.destination.longitude}) "
                       f"is outside graph coverage area (no connected node within {payload.max_snap_distance_km} km)."
            )

    # 5. Run Dijkstra routing
    try:
        router = DijkstraRouter(graph)
        result = router.route(origin_node, dest_node)
    except ValueError as e:
        err_msg = str(e)
        if "unreachable" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination node '{dest_node}' is unreachable from origin node '{origin_node}'."
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Routing error: {err_msg}"
        )
    except Exception as e:
        logger.error(f"Unexpected routing failure: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while calculating the route."
        )

    # 6. Format and return response
    return DijkstraRouteResponse(
        origin_node=origin_node,
        destination_node=dest_node,
        total_distance_km=result.total_distance_km,
        nodes=result.nodes,
        nodes_count=result.node_count,
        edges_count=result.edge_count,
        modes_used=result.modes_used,
        transfers_count=result.transfers_count,
        total_travel_time_min=result.total_travel_time_min,
        travel_time_complete=result.travel_time_complete,
        total_cost_lkr=result.total_cost_lkr,
        cost_complete=result.cost_complete,
        warnings=result.warnings,
        edges=[
            RouteEdgeResponse(
                from_node=e.from_node,
                to_node=e.to_node,
                mode=e.mode.value if hasattr(e.mode, "value") else str(e.mode),
                distance_km=e.attributes.get("distance_km"),
                travel_time_min=e.attributes.get("travel_time_min"),
                cost_lkr=e.attributes.get("cost_lkr"),
                source_id=e.attributes.get("source_id"),
                source_dataset=e.attributes.get("source_dataset"),
                is_estimated=e.attributes.get("is_estimated", False)
            )
            for e in result.edges
        ],
        source="local_dijkstra"
    )
