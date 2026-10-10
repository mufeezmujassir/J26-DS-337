import math
import heapq
from typing import List, Tuple, Dict
from app.services.graph import MultimodalGraph

class DijkstraRouter:
    def __init__(self, graph: MultimodalGraph):
        self.graph = graph

    def route(self, from_node: str, to_node: str) -> Tuple[List[str], float]:
        """
        Calculates shortest path by distance_km.
        Returns Tuple of (path_node_ids, total_distance_km)
        Raises ValueError if destination is unreachable.
        """
        if from_node not in self.graph.nodes or to_node not in self.graph.nodes:
            raise ValueError("Origin or destination not in graph")

        distances: Dict[str, float] = {node_id: math.inf for node_id in self.graph.nodes}
        distances[from_node] = 0.0
        
        previous: Dict[str, str] = {}
        pq = [(0.0, from_node)]
        
        while pq:
            current_dist, current_node = heapq.heappop(pq)
            
            if current_node == to_node:
                break
                
            if current_dist > distances[current_node]:
                continue
                
            if current_node in self.graph.edges:
                for neighbor, edges in self.graph.edges[current_node].items():
                    min_edge_dist = math.inf
                    
                    for e in edges:
                        w = e.attributes.get("distance_km")
                        if w is not None and w >= 0:
                            min_edge_dist = min(min_edge_dist, w)
                            
                    if min_edge_dist == math.inf:
                        continue
                        
                    distance = current_dist + min_edge_dist
                    
                    if distance < distances[neighbor]:
                        distances[neighbor] = distance
                        previous[neighbor] = current_node
                        heapq.heappush(pq, (distance, neighbor))
                        
        if distances[to_node] == math.inf:
            raise ValueError("Destination is unreachable")
            
        path = []
        curr = to_node
        while curr != from_node:
            path.append(curr)
            curr = previous[curr]
        path.append(from_node)
        path.reverse()
        
        return path, distances[to_node]
