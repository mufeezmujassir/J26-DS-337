import logging
from app.services.graph import MultimodalGraph
from app.services.transfer_loader import haversine

logger = logging.getLogger(__name__)

def associate_scenic_places(graph: MultimodalGraph, scenic_places: list, max_dist_km: float = 1.0) -> int:
    """
    Associates scenic places with the nearest graph Node if within threshold.
    Preserves source metadata by appending to node.properties['scenic_places'].
    Does not score edges or fabricate connections.
    """
    associations = 0
    for sp in scenic_places:
        if getattr(sp, "latitude", None) is None or getattr(sp, "longitude", None) is None: 
            continue
            
        closest_node = None
        min_d = max_dist_km
        
        for n_id, n in graph.nodes.items():
            if not n.lat or not n.lon: 
                continue
            d = haversine(sp.latitude, sp.longitude, n.lat, n.lon)
            if d < min_d:
                min_d = d
                closest_node = n
        
        if closest_node:
            scenic_list = closest_node.properties.setdefault('scenic_places', [])
            scenic_list.append({
                "name": getattr(sp, "name", "unknown"),
                "category": getattr(sp, "category", "unknown"),
                "distance_km": float(min_d),
                "source_dataset": "scenic_places",
                "original_type": getattr(sp, "type", None)
            })
            associations += 1
            
    logger.info(f"Associated {associations} scenic places to graph nodes.")
    return associations
