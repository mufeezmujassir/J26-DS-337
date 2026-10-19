import math
import logging
from typing import Optional, Tuple
from app.services.graph import MultimodalGraph
from app.services.dijkstra import DistanceCostModel

logger = logging.getLogger(__name__)

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points on the Earth surface in kilometres.
    Validates numeric inputs and returns non-negative distance.
    """
    r = 6371.0 # Earth's radius in kilometres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c

def find_nearest_routable_node(
    graph: MultimodalGraph,
    lat: float,
    lon: float,
    direction: str = "outgoing",
    max_radius_km: float = 25.0
) -> Tuple[Optional[str], Optional[float]]:
    """
    Finds the nearest graph node with coordinates within max_radius_km that is routable.
    
    - direction == 'outgoing': node must have at least one outgoing traversable edge
    - direction == 'incoming': node must have at least one incoming traversable edge
    - direction == 'either': node must have at least one traversable connected edge
    
    Returns (node_id, distance_km) or (None, None) if no routable node is within coverage.
    """
    if not graph.nodes:
        return None, None
        
    cost_model = DistanceCostModel()
    best_node_id = None
    min_dist_km = math.inf
    
    # Pre-check routable nodes to avoid selecting unroutable sinks or isolated components
    for node_id, node in graph.nodes.items():
        if node.lat is None or node.lon is None:
            continue
        if not (isinstance(node.lat, (int, float)) and isinstance(node.lon, (int, float))):
            continue
            
        # Check routability
        if direction == "outgoing":
            outgoing_edges = graph.get_all_edges_from(node_id)
            if not any(cost_model.get_weight(e) is not None for e in outgoing_edges):
                continue
        elif direction == "incoming":
            # Check incoming edges
            has_incoming = False
            for from_n, dest_dict in graph.edges.items():
                if node_id in dest_dict:
                    if any(cost_model.get_weight(e) is not None for e in dest_dict[node_id]):
                        has_incoming = True
                        break
            if not has_incoming:
                continue
                
        dist = haversine_km(lat, lon, float(node.lat), float(node.lon))
        if dist < min_dist_km:
            min_dist_km = dist
            best_node_id = node_id
            
    if best_node_id is not None and min_dist_km <= max_radius_km:
        return best_node_id, min_dist_km
        
    return None, None
