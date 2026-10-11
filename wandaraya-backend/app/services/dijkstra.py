import math
import heapq
from typing import List, Tuple, Dict, Optional, Any
from app.services.graph import MultimodalGraph, Edge

class DistanceCostModel:
    """
    Distance-based cost model for Dijkstra routing.
    Minimizes distance in kilometres (distance_km).
    Enforces strict numeric validation: finite, non-negative, non-boolean numeric values.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights.
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        if not hasattr(edge, "attributes") or not isinstance(edge.attributes, dict):
            return None
        w = edge.attributes.get("distance_km")
        if w is None or isinstance(w, bool):
            return None
        if not isinstance(w, (int, float)):
            return None
        try:
            val = float(w)
        except (ValueError, TypeError):
            return None
        if not math.isfinite(val) or val < 0.0:
            return None
        return val

class DijkstraPathResult:
    """
    Result of a Dijkstra route calculation.
    Contains ordered node IDs, ordered Edge objects, and total distance in kilometres.
    Compatible with tuple unpacking: `path, dist = router.route(...)`
    """
    def __init__(self, nodes: List[str], edges: List[Edge], total_distance_km: float):
        self.nodes = nodes
        self.edges = edges
        self.total_distance_km = total_distance_km

    def __iter__(self):
        yield self.nodes
        yield self.total_distance_km

    def __getitem__(self, idx):
        return (self.nodes, self.total_distance_km)[idx]

    def __len__(self):
        return 2

    def __eq__(self, other):
        if isinstance(other, tuple) and len(other) == 2:
            return (self.nodes, self.total_distance_km) == other
        if isinstance(other, DijkstraPathResult):
            return (self.nodes, self.edges, self.total_distance_km) == (other.nodes, other.edges, other.total_distance_km)
        return False

    def __repr__(self):
        return f"DijkstraPathResult(nodes={self.nodes}, total_distance_km={self.total_distance_km}, edges_count={len(self.edges)})"

class DijkstraRouter:
    def __init__(self, graph: MultimodalGraph, cost_model: Optional[Any] = None):
        self.graph = graph
        self.cost_model = cost_model or DistanceCostModel()

    def route(self, from_node: str, to_node: str) -> DijkstraPathResult:
        """
        Calculates shortest path by distance_km.
        Reconstructs ordered node path and corresponding ordered edge sequence.
        Calculates total distance from actual path edges.
        Preserves transport mode and source edge metadata.
        Returns DijkstraPathResult (which unpacks as (nodes, total_distance_km)).
        Raises ValueError if origin/destination is invalid or destination is unreachable.
        """
        if from_node is None or to_node is None:
            raise ValueError("Origin and destination must not be None")

        if from_node not in self.graph.nodes or to_node not in self.graph.nodes:
            raise ValueError("Origin or destination not in graph")

        # Handle identical origin and destination
        if from_node == to_node:
            return DijkstraPathResult(nodes=[from_node], edges=[], total_distance_km=0.0)

        distances: Dict[str, float] = {node_id: math.inf for node_id in self.graph.nodes}
        distances[from_node] = 0.0
        
        previous_node: Dict[str, str] = {}
        previous_edge: Dict[str, Edge] = {}
        pq = [(0.0, from_node)]
        
        while pq:
            current_dist, current_node = heapq.heappop(pq)
            
            if current_node == to_node:
                break
                
            if current_dist > distances[current_node]:
                continue
                
            if current_node in self.graph.edges:
                for neighbor, edge_list in self.graph.edges[current_node].items():
                    # Find candidate edge with minimum valid weight between current_node and neighbor
                    best_edge = None
                    min_edge_dist = math.inf
                    
                    for e in edge_list:
                        w = self.cost_model.get_weight(e)
                        if w is not None and w < min_edge_dist:
                            min_edge_dist = w
                            best_edge = e
                            
                    if best_edge is None or min_edge_dist == math.inf:
                        continue
                        
                    distance = current_dist + min_edge_dist
                    
                    if distance < distances[neighbor]:
                        distances[neighbor] = distance
                        previous_node[neighbor] = current_node
                        previous_edge[neighbor] = best_edge
                        heapq.heappush(pq, (distance, neighbor))
                        
        if distances[to_node] == math.inf or to_node not in previous_node:
            raise ValueError("Destination is unreachable")
            
        # Reconstruct ordered node path and edge sequence
        reversed_nodes: List[str] = []
        reversed_edges: List[Edge] = []
        curr = to_node
        while curr != from_node:
            reversed_nodes.append(curr)
            edge = previous_edge[curr]
            reversed_edges.append(edge)
            curr = previous_node[curr]
        reversed_nodes.append(from_node)

        path_nodes = list(reversed(reversed_nodes))
        path_edges = list(reversed(reversed_edges))

        # Recalculate total distance directly from actual path edges
        total_distance = sum(
            self.cost_model.get_weight(e) or 0.0
            for e in path_edges
        )

        return DijkstraPathResult(
            nodes=path_nodes,
            edges=path_edges,
            total_distance_km=total_distance
        )
