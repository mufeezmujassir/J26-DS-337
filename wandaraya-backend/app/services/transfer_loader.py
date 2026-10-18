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

def build_transfers(graph: MultimodalGraph, max_walk_km: float = 2.0) -> int:
    """
    Builds walking transfer edges between disconnected transit nodes (rail, bus, road).
    Uses Haversine distance, parameterized by spatial threshold.
    """
    road_nodes = [n for id, n in graph.nodes.items() if id.startswith("road_")]
    transit_nodes = [n for id, n in graph.nodes.items() if id.startswith("station_") or id.startswith("rail_")]
    bus_nodes = [n for id, n in graph.nodes.items() if id.startswith("bus_")]
    
    transfers_added = 0

    # 1. Transfer between rail and bus stands (intermodal hubs)
    for rn in transit_nodes:
        for bn in bus_nodes:
            d = haversine(rn.lat, rn.lon, bn.lat, bn.lon)
            if d <= max_walk_km:
                walk_time = round((d / 4.5) * 60.0 + 5.0, 1) # walking speed 4.5 km/h + 5 min transfer
                edge = Edge(
                    from_node=rn.node_id, 
                    to_node=bn.node_id,
                    mode=GraphMode.WALKING,
                    directed=False,
                    attributes={
                        "distance_km": round(float(d), 2),
                        "travel_time_min": walk_time,
                        "cost_lkr": 0.0,
                        "transfer_type": "rail_to_bus"
                    }
                )
                try:
                    graph.add_edge(edge)
                    transfers_added += 1
                except ValueError:
                    pass

    # 2. Transfer between transit and road nodes
    if road_nodes:
        for sn in (transit_nodes + bus_nodes):
            closest = None
            min_dist = max_walk_km
            for rn in road_nodes:
                d = haversine(sn.lat, sn.lon, rn.lat, rn.lon)
                if d < min_dist:
                    min_dist = d
                    closest = rn
            if closest:
                t_type = "station_to_road" if (sn.node_id.startswith("station_") or sn.node_id.startswith("rail_")) else "bus_to_road"
                edge = Edge(
                    from_node=sn.node_id, 
                    to_node=closest.node_id,
                    mode=GraphMode.WALKING,
                    directed=False,
                    attributes={"distance_km": round(float(min_dist), 2), "transfer_type": t_type}
                )
                try:
                    graph.add_edge(edge)
                    transfers_added += 1
                except ValueError:
                    pass
                
    logger.info(f"Built {transfers_added} walking transfer links.")
    return transfers_added
