import logging
import math
from app.services.graph import MultimodalGraph, Edge, GraphMode

logger = logging.getLogger(__name__)

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0 # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def build_transfers(graph: MultimodalGraph, max_walk_km: float = 0.5) -> int:
    """
    Builds walking transfer edges between disconnected transit nodes and road nodes.
    Uses Haversine distance, parameterized by spatial threshold.
    """
    road_nodes = [n for id, n in graph.nodes.items() if id.startswith("road_")]
    station_nodes = [n for id, n in graph.nodes.items() if id.startswith("station_")]
    
    transfers_added = 0
    for sn in station_nodes:
        # Find closest road node within spatial threshold
        closest = None
        min_dist = max_walk_km
        
        for rn in road_nodes:
            d = haversine(sn.lat, sn.lon, rn.lat, rn.lon)
            if d < min_dist:
                min_dist = d
                closest = rn
        
        if closest:
            edge = Edge(
                from_node=sn.node_id, 
                to_node=closest.node_id,
                mode=GraphMode.WALKING,
                directed=False,
                attributes={"distance_km": float(min_dist), "transfer_type": "station_to_road"}
            )
            try:
                graph.add_edge(edge)
                transfers_added += 1
            except ValueError:
                pass
                
    logger.info(f"Built {transfers_added} walking transfer links.")
    return transfers_added
