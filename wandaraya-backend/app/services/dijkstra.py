import math
import heapq
from typing import List, Tuple, Dict, Optional, Any
from app.services.graph import MultimodalGraph, Edge
from app.services.route_metrics import RouteMetricsService, CalculatedRouteMetrics

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

class CostCostModel:
    """
    Cost-based cost model for Dijkstra routing.
    Minimizes monetary cost in LKR (cost_lkr).
    Enforces strict numeric validation: finite, non-negative, non-boolean numeric values.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights.
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        if not hasattr(edge, "attributes") or not isinstance(edge.attributes, dict):
            return None
        w = edge.attributes.get("cost_lkr")
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

class TimeCostModel:
    """
    Travel-time-based cost model for Dijkstra routing.
    Minimizes journey time in minutes (travel_time_min).
    Enforces strict numeric validation: finite, non-negative, non-boolean numeric values.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights.
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        if not hasattr(edge, "attributes") or not isinstance(edge.attributes, dict):
            return None
        w = edge.attributes.get("travel_time_min")
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
    and derived route metrics calculated via RouteMetricsService.
    Compatible with tuple unpacking: `path, dist = router.route(...)`
    """
    def __init__(
        self,
        nodes: List[str],
        edges: List[Edge],
        total_distance_km: Optional[float] = None,
        objective: str = "distance",
        optimized_weight: Optional[float] = None
    ):
        self.nodes = nodes
        self.edges = edges
        self.node_count = len(nodes)
        self.edge_count = len(edges)
        self.objective = objective

        # Calculate comprehensive metrics via RouteMetricsService
        metrics: CalculatedRouteMetrics = RouteMetricsService.calculate_metrics(edges, nodes)
        self.metrics = metrics

        # Total distance: use calculated metric or explicit distance
        calc_dist = metrics.total_distance_km if total_distance_km is None else total_distance_km
        self.total_distance_km = round(calc_dist, 6)

        # Mode and transfer statistics
        self.modes_used = metrics.modes_used
        self.mode_sequence = metrics.mode_sequence
        self.mode_changes_count = metrics.mode_changes_count
        self.transfers_count = metrics.transfers_count
        self.transfer_locations = metrics.transfer_locations

        # Time metrics
        self.total_travel_time_min = metrics.total_travel_time_min
        self.travel_time_complete = metrics.travel_time_complete
        self.known_travel_time_min = metrics.known_travel_time_min
        self.total_waiting_time_min = metrics.total_waiting_time_min
        self.total_transfer_time_min = metrics.total_transfer_time_min
        self.total_journey_time_min = metrics.total_journey_time_min
        self.journey_time_complete = metrics.journey_time_complete
        self.is_travel_time_estimated = metrics.is_travel_time_estimated

        # Cost metrics
        self.total_cost_lkr = metrics.total_cost_lkr
        self.cost_complete = metrics.cost_complete
        self.known_cost_lkr = metrics.known_cost_lkr
        self.is_cost_estimated = metrics.is_cost_estimated

        # Warnings & optimization tracking
        self.warnings: List[str] = list(metrics.warnings)
        self.optimized_weight = optimized_weight

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_distance_km": self.total_distance_km,
            "nodes": self.nodes,
            "nodes_count": self.node_count,
            "edges_count": self.edge_count,
            "modes_used": self.modes_used,
            "mode_sequence": self.mode_sequence,
            "mode_changes_count": self.mode_changes_count,
            "transfers_count": self.transfers_count,
            "transfer_locations": self.transfer_locations,
            "total_travel_time_min": self.total_travel_time_min,
            "travel_time_complete": self.travel_time_complete,
            "known_travel_time_min": self.known_travel_time_min,
            "total_waiting_time_min": self.total_waiting_time_min,
            "total_transfer_time_min": self.total_transfer_time_min,
            "total_journey_time_min": self.total_journey_time_min,
            "journey_time_complete": self.journey_time_complete,
            "is_travel_time_estimated": self.is_travel_time_estimated,
            "total_cost_lkr": self.total_cost_lkr,
            "cost_complete": self.cost_complete,
            "known_cost_lkr": self.known_cost_lkr,
            "is_cost_estimated": self.is_cost_estimated,
            "objective": self.objective,
            "optimized_weight": self.optimized_weight,
            "warnings": self.warnings,
            "edges": [
                {
                    "from_node": e.from_node,
                    "to_node": e.to_node,
                    "mode": e.mode.value if hasattr(e.mode, "value") else str(e.mode),
                    "distance_km": e.attributes.get("distance_km"),
                    "travel_time_min": e.attributes.get("travel_time_min"),
                    "cost_lkr": e.attributes.get("cost_lkr"),
                    "waiting_time_min": e.attributes.get("waiting_time_min"),
                    "transfer_time_min": e.attributes.get("transfer_time_min"),
                    "transfer_type": e.attributes.get("transfer_type"),
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
            f"transfers={self.transfers_count}, "
            f"objective={self.objective})"
        )

class DijkstraRouter:
    def __init__(
        self,
        graph: MultimodalGraph,
        cost_model: Optional[Any] = None,
        objective: str = "distance"
    ):
        self.graph = graph
        self.objective = objective.lower().strip() if objective else "distance"

        if cost_model is not None:
            self.cost_model = cost_model
        elif self.objective == "distance":
            self.cost_model = DistanceCostModel()
        elif self.objective == "cost":
            self.cost_model = CostCostModel()
        elif self.objective == "time":
            self.cost_model = TimeCostModel()
        else:
            raise ValueError(
                f"Unsupported routing objective '{objective}'. "
                "Supported objectives are: 'distance', 'cost', 'time'."
            )

    def route(self, from_node: str, to_node: str) -> DijkstraPathResult:
        """
        Calculates shortest path using Dijkstra algorithm with the selected cost model.
        Default objective: distance minimization.
        Optional objectives: cost minimization, travel-time minimization.
        Reconstructs ordered node path and corresponding ordered edge sequence.
        Calculates comprehensive route metrics without fabricating missing values.
        Returns DijkstraPathResult (unpacks as (nodes, total_distance_km)).
        Raises ValueError if origin/destination is invalid or destination is unreachable.
        """
        if from_node is None or to_node is None:
            raise ValueError("Origin and destination must not be None")

        if from_node not in self.graph.nodes or to_node not in self.graph.nodes:
            raise ValueError("Origin or destination not in graph")

        # Handle identical origin and destination
        if from_node == to_node:
            return DijkstraPathResult(
                nodes=[from_node],
                edges=[],
                total_distance_km=0.0,
                objective=self.objective,
                optimized_weight=0.0
            )

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

        # Direct sum of distances from actual path edges
        actual_total_distance = sum(
            float(e.attributes.get("distance_km") or 0.0)
            for e in path_edges
        )

        optimized_weight = distances[to_node]

        return DijkstraPathResult(
            nodes=path_nodes,
            edges=path_edges,
            total_distance_km=actual_total_distance,
            objective=self.objective,
            optimized_weight=optimized_weight
        )
