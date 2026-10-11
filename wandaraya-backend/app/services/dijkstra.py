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
    Contains ordered node IDs, ordered Edge objects, total distance in kilometres,
    and derived route metadata from actual edges.
    Compatible with tuple unpacking: `path, dist = router.route(...)`
    """
    def __init__(self, nodes: List[str], edges: List[Edge], total_distance_km: float):
        self.nodes = nodes
        self.edges = edges
        self.total_distance_km = round(total_distance_km, 6)
        self.node_count = len(nodes)
        self.edge_count = len(edges)

        # Modes used: unique modes in order of first appearance
        seen_modes = set()
        self.modes_used: List[str] = []
        for e in edges:
            m_val = e.mode.value if hasattr(e.mode, "value") else str(e.mode)
            if m_val not in seen_modes:
                seen_modes.add(m_val)
                self.modes_used.append(m_val)

        # Transfers count: count mode changes and explicit transfer links without double-counting
        self.transfers_count = self._calculate_transfers(edges)

        # Travel time: calculate only when ALL edge values are available, numeric and finite
        self.total_travel_time_min, self.travel_time_complete = self._calculate_total_time(edges)

        # Travel cost: calculate only when ALL edge values are available, numeric and finite
        self.total_cost_lkr, self.cost_complete = self._calculate_total_cost(edges)

        # Warnings / Provenance
        self.warnings: List[str] = []
        if not self.travel_time_complete and self.edge_count > 0:
            missing_time = sum(
                1 for e in edges
                if e.attributes.get("travel_time_min") is None
                or isinstance(e.attributes.get("travel_time_min"), bool)
                or not isinstance(e.attributes.get("travel_time_min"), (int, float))
            )
            self.warnings.append(
                f"Travel time unavailable for {missing_time} of {self.edge_count} edge(s). "
                "Total duration not estimated (no hardcoded speed assumption)."
            )
        if not self.cost_complete and self.edge_count > 0:
            missing_cost = sum(
                1 for e in edges
                if e.attributes.get("cost_lkr") is None
                or isinstance(e.attributes.get("cost_lkr"), bool)
                or not isinstance(e.attributes.get("cost_lkr"), (int, float))
            )
            self.warnings.append(
                f"Travel cost unavailable for {missing_cost} of {self.edge_count} edge(s). "
                "Total cost not estimated."
            )

    @staticmethod
    def _calculate_transfers(edges: List[Edge]) -> int:
        if not edges:
            return 0
        transfers = 0
        prev_mode = None
        for e in edges:
            m_val = e.mode.value if hasattr(e.mode, "value") else str(e.mode)
            is_transfer_edge = (
                m_val == "transfer"
                or (hasattr(e, "mode") and getattr(e.mode, "name", None) == "TRANSFER")
                or bool(e.attributes.get("transfer_type"))
            )
            if is_transfer_edge:
                transfers += 1
            elif prev_mode is not None and m_val != prev_mode and prev_mode != "transfer":
                transfers += 1
            prev_mode = m_val
        return transfers

    @staticmethod
    def _calculate_total_time(edges: List[Edge]) -> Tuple[Optional[float], bool]:
        if not edges:
            return 0.0, True
        total = 0.0
        for e in edges:
            val = e.attributes.get("travel_time_min")
            if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
                return None, False
            f_val = float(val)
            if not math.isfinite(f_val) or f_val < 0.0:
                return None, False
            total += f_val
        return round(total, 4), True

    @staticmethod
    def _calculate_total_cost(edges: List[Edge]) -> Tuple[Optional[float], bool]:
        if not edges:
            return 0.0, True
        total = 0.0
        for e in edges:
            val = e.attributes.get("cost_lkr")
            if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
                return None, False
            f_val = float(val)
            if not math.isfinite(f_val) or f_val < 0.0:
                return None, False
            total += f_val
        return round(total, 4), True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_distance_km": self.total_distance_km,
            "nodes": self.nodes,
            "nodes_count": self.node_count,
            "edges_count": self.edge_count,
            "modes_used": self.modes_used,
            "transfers_count": self.transfers_count,
            "total_travel_time_min": self.total_travel_time_min,
            "travel_time_complete": self.travel_time_complete,
            "total_cost_lkr": self.total_cost_lkr,
            "cost_complete": self.cost_complete,
            "warnings": self.warnings,
            "edges": [
                {
                    "from_node": e.from_node,
                    "to_node": e.to_node,
                    "mode": e.mode.value if hasattr(e.mode, "value") else str(e.mode),
                    "distance_km": e.attributes.get("distance_km"),
                    "travel_time_min": e.attributes.get("travel_time_min"),
                    "cost_lkr": e.attributes.get("cost_lkr"),
                    "source_id": e.attributes.get("source_id"),
                    "source_dataset": e.attributes.get("source_dataset"),
                    "is_estimated": e.attributes.get("is_estimated", False),
                }
                for e in self.edges
            ]
        }

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
        return (
            f"DijkstraPathResult(nodes={self.nodes}, "
            f"distance_km={self.total_distance_km}, "
            f"modes={self.modes_used}, "
            f"transfers={self.transfers_count})"
        )

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
