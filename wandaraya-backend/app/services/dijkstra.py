import math
import heapq
from typing import List, Tuple, Dict, Optional, Any
from app.services.graph import MultimodalGraph, Edge
from app.services.route_metrics import RouteMetricsService, CalculatedRouteMetrics

class DistanceCostModel:
    """
    Distance-based cost model for shortest-route Dijkstra routing.
    Minimizes distance in kilometres (distance_km).
    Enforces strict numeric validation: finite, non-negative, non-boolean numeric values.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights (returns None).
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
    Cost-based cost model for cheapest-route Dijkstra routing.
    Minimizes monetary cost in LKR (cost_lkr).
    Enforces strict numeric validation: finite, non-negative, non-boolean numeric values.
    Distinguishes explicitly free edges (cost_lkr = 0.0) from missing fares (cost_lkr is None).
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights (returns None).
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

class SlowerCostModel:
    """
    Slower / Leisurely route cost model for WANDARAYA scenic routing.
    Favors relaxed, leisurely travel pace with lower transit speeds (e.g. scenic coastal
    or hill-country bus/train) over rushed express highways.
    Calculates cost proportional to edge transit speed in km/h.
    Minimizing speed steers Dijkstra towards slower, more leisurely options.
    Enforces strict numeric validation: finite, non-negative, non-boolean numbers.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights (returns None).
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        if not hasattr(edge, "attributes") or not isinstance(edge.attributes, dict):
            return None

        attrs = edge.attributes
        d = attrs.get("distance_km")
        t = attrs.get("travel_time_min")

        def _val(val):
            if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
                return None
            try:
                f = float(val)
                return f if math.isfinite(f) and f >= 0.0 else None
            except (ValueError, TypeError):
                return None

        val_d = _val(d)
        val_t = _val(t)

        if val_d is None:
            return None

        # If travel time is provided, speed = distance / (time / 60)
        if val_t is not None and val_t > 0.0:
            speed_kmh = val_d / (val_t / 60.0)
        else:
            # Mode default speed baseline
            mode_str = str(getattr(edge.mode, "value", edge.mode)).lower()
            if "walk" in mode_str:
                speed_kmh = 4.5
            elif "bus" in mode_str:
                speed_kmh = 30.0
            elif "rail" in mode_str:
                speed_kmh = 40.0
            else:
                speed_kmh = 50.0

        # Non-negative, finite positive weight
        return max(0.1, round(speed_kmh, 4))

class ScenicCostModel:
    """
    Scenic route cost model for WANDARAYA scenic routing.
    Prioritizes aesthetically pleasing transit options (such as scenic coastal
    railway lines, hill country rail, or scenic trunk routes with picturesque landscapes)
    over utilitarian high-speed expressway bypasses.

    Dijkstra minimizes total edge weight, so higher scenic value results in lower weight.
    Cost formulation:
      base_weight = distance_km * scenic_factor
      where scenic_factor:
        - Rail (Coastal, Main/Hill Country, Eastern lines): 0.40 (highly favored for scenic beauty)
        - Regular bus (scenic coastal / landmark routes): 0.85
        - Walking: 1.00
        - High-speed highway/expressway: 2.50 (penalized for low scenic interaction)
      If explicit 'scenic_score' attribute is present (0-100), adjusts factor accordingly.
    Enforces strict numeric validation: finite, non-negative, non-boolean numbers.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights (returns None).
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        if not hasattr(edge, "attributes") or not isinstance(edge.attributes, dict):
            return None

        attrs = edge.attributes
        d = attrs.get("distance_km")

        def _val(val):
            if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
                return None
            try:
                f = float(val)
                return f if math.isfinite(f) and f >= 0.0 else None
            except (ValueError, TypeError):
                return None

        val_d = _val(d)
        if val_d is None:
            return None

        mode_str = str(getattr(edge.mode, "value", edge.mode)).lower()
        route_no = str(attrs.get("route_no", "")).upper()
        via = str(attrs.get("via", "")).lower()
        corridor = str(attrs.get("corridor", "")).lower()

        # Scenic multiplier: lower multiplier means preferred in Dijkstra
        if "rail" in mode_str:
            if any(k in corridor for k in ("main", "coastal", "hill", "eastern")):
                scenic_factor = 0.40
            else:
                scenic_factor = 0.50
        elif "expressway" in via or "ex" in route_no or "highway" in via:
            scenic_factor = 2.50
        elif "walk" in mode_str:
            scenic_factor = 1.00
        elif "bus" in mode_str:
            scenic_factor = 0.85
        else:
            scenic_factor = 1.00

        # Incorporate explicit scenic_score on edge if present (0 to 100)
        explicit_score = _val(attrs.get("scenic_score"))
        if explicit_score is not None and explicit_score > 0:
            scenic_factor *= (1.5 - (min(100.0, explicit_score) / 100.0) * 1.2)

        return max(0.01, round(val_d * scenic_factor, 4))

class TimeCostModel:
    """
    Journey-time cost model for fastest-route Dijkstra routing.
    Minimizes total journey time in minutes, accounting for:
      - in-vehicle or road travel time (travel_time_min)
      - walking duration
      - scheduled waiting time (waiting_time_min)
      - transfer time (transfer_time_min)
    Avoids double-counting and enforces strict numeric validation:
    finite, non-negative, non-boolean numbers.
    Rejects missing, negative, NaN, infinite, or non-numeric edge weights (returns None).
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        if not hasattr(edge, "attributes") or not isinstance(edge.attributes, dict):
            return None

        attrs = edge.attributes
        t = attrs.get("travel_time_min")
        w = attrs.get("waiting_time_min")
        tr = attrs.get("transfer_time_min")

        def _val(val):
            if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
                return None
            try:
                f = float(val)
                return f if math.isfinite(f) and f >= 0.0 else None
            except (ValueError, TypeError):
                return None

        val_t = _val(t)
        val_w = _val(w)
        val_tr = _val(tr)

        # If neither motion travel time nor transfer time is provided, journey time is unknown
        if val_t is None and val_tr is None:
            return None

        # Base motion time
        motion_time = val_t if val_t is not None else val_tr

        # Additional transfer time (only add if distinct from motion_time to prevent double-counting)
        add_transfer = 0.0
        if val_tr is not None and val_t is not None and val_tr != val_t:
            add_transfer = val_tr

        add_waiting = val_w if val_w is not None else 0.0

        total_edge_time = motion_time + add_transfer + add_waiting
        return round(total_edge_time, 4)

class EnvironmentalRiskCostModel:
    """
    Environmental risk-aware cost model for Dijkstra routing.
    Weights edges by distance with a penalty factor for edges passing through
    documented landslide proximity hazard zones or active severe weather areas.
    Maintains travel distance, travel time, and fare as strictly separate metrics.
    """
    @staticmethod
    def get_weight(edge: Edge) -> Optional[float]:
        val_d = DistanceCostModel.get_weight(edge)
        if val_d is None:
            return None
        attrs = getattr(edge, "attributes", {}) or {}
        # Penalty if edge is tagged with environmental hazard (e.g., landslide proximity or severe weather alert)
        risk_penalty = 1.0
        if attrs.get("hazard_detected") or attrs.get("landslide_proximity"):
            risk_penalty = 3.0  # Steers path towards safer alternative corridors
        return max(0.01, round(val_d * risk_penalty, 4))

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
        objective: str = "shortest",
        optimized_weight: Optional[float] = None
    ):
        self.nodes = nodes
        self.edges = edges
        self.node_count = len(nodes)
        self.edge_count = len(edges)
        self.objective = objective

        # Calculate comprehensive metrics via RouteMetricsService
        metrics = RouteMetricsService.calculate_metrics(edges, nodes)
        self.total_distance_km = total_distance_km if total_distance_km is not None else metrics.total_distance_km
        self.total_cost_lkr = metrics.total_cost_lkr
        self.cost_complete = metrics.cost_complete
        self.known_cost_lkr = metrics.known_cost_lkr
        self.total_travel_time_min = metrics.total_travel_time_min
        self.travel_time_complete = metrics.travel_time_complete
        self.known_travel_time_min = metrics.known_travel_time_min
        self.total_waiting_time_min = metrics.total_waiting_time_min
        self.total_transfer_time_min = metrics.total_transfer_time_min
        self.total_journey_time_min = metrics.total_journey_time_min
        self.journey_time_complete = metrics.journey_time_complete
        self.is_travel_time_estimated = metrics.is_travel_time_estimated
        self.is_cost_estimated = metrics.is_cost_estimated
        self.modes_used = metrics.modes_used
        self.mode_sequence = metrics.mode_sequence
        self.mode_changes_count = metrics.mode_changes_count
        self.transfers_count = metrics.transfers_count
        self.transfer_locations = metrics.transfer_locations
        self.warnings = list(metrics.warnings)

        # Map optimized weight and warnings per objective
        if self.objective in ("shortest", "distance"):
            self.optimized_weight = self.total_distance_km
        elif self.objective in ("fastest", "time"):
            self.optimized_weight = self.total_journey_time_min if self.total_journey_time_min is not None else self.total_travel_time_min
            if not any("timetable" in w.lower() for w in self.warnings):
                self.warnings.append(
                    "Fastest-route objective calculated using static link journey times; "
                    "real-time GTFS timetable departures and headway delays are not modeled."
                )
        elif self.objective in ("cheapest", "cost"):
            self.optimized_weight = self.total_cost_lkr
        elif self.objective in ("slower", "slowest", "leisurely"):
            self.optimized_weight = self.total_journey_time_min if self.total_journey_time_min is not None else self.total_travel_time_min
            self.warnings.append(
                "Slower-route objective optimized for a relaxed, leisurely journey pace with lower transit speed."
            )
        elif self.objective in ("scenic", "picturesque"):
            self.optimized_weight = self.total_distance_km
            self.warnings.append(
                "Scenic-route objective optimized for picturesque landscapes, coastal/hill corridors, and scenic vistas."
            )
        elif self.objective in ("environmental_risk", "safe", "risk_aware"):
            self.optimized_weight = self.total_distance_km
            self.warnings.append(
                "Environmental-risk objective optimized to steer route away from documented landslide zones and severe weather alerts."
            )
        else:
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
    SUPPORTED_OBJECTIVES = {
        "shortest": "shortest",
        "distance": "shortest",
        "fastest": "fastest",
        "time": "fastest",
        "cheapest": "cheapest",
        "cost": "cheapest",
        "slower": "slower",
        "slowest": "slower",
        "leisurely": "slower",
        "scenic": "scenic",
        "picturesque": "scenic",
        "environmental_risk": "environmental_risk",
        "safe": "environmental_risk",
        "risk_aware": "environmental_risk",
    }

    def __init__(
        self,
        graph: MultimodalGraph,
        cost_model: Optional[Any] = None,
        objective: str = "shortest",
        allowed_modes: Optional[Any] = None
    ):
        self.graph = graph
        raw_obj = (objective or "shortest").lower().strip()
        if raw_obj not in self.SUPPORTED_OBJECTIVES:
            raise ValueError(
                f"Unsupported routing objective '{objective}'. "
                "Supported objectives are: 'shortest' (distance), 'fastest' (time), 'cheapest' (cost), 'slower' (leisurely pace), 'scenic' (picturesque landscape), 'environmental_risk' (hazard avoidance)."
            )
        self.canonical_objective = self.SUPPORTED_OBJECTIVES[raw_obj]
        self.objective = raw_obj
        if allowed_modes is not None:
            if isinstance(allowed_modes, str):
                self.allowed_modes = {m.strip().lower() for m in allowed_modes.split(",") if m.strip()}
            else:
                self.allowed_modes = {str(m).strip().lower() for m in allowed_modes if str(m).strip()}
        else:
            self.allowed_modes = None

        if cost_model is not None:
            self.cost_model = cost_model
        elif self.canonical_objective == "shortest":
            self.cost_model = DistanceCostModel()
        elif self.canonical_objective == "fastest":
            self.cost_model = TimeCostModel()
        elif self.canonical_objective == "cheapest":
            self.cost_model = CostCostModel()
        elif self.canonical_objective == "slower":
            self.cost_model = SlowerCostModel()
        elif self.canonical_objective == "scenic":
            self.cost_model = ScenicCostModel()
        elif self.canonical_objective == "environmental_risk":
            self.cost_model = EnvironmentalRiskCostModel()

    def _is_mode_allowed(self, mode_str: str) -> bool:
        if self.allowed_modes is None:
            return True
        norm = mode_str.lower().strip()
        if norm in self.allowed_modes:
            return True
        if norm == "rail" and ("train" in self.allowed_modes or "rail" in self.allowed_modes):
            return True
        if norm in ("road", "car") and ("car" in self.allowed_modes or "road" in self.allowed_modes or "driving" in self.allowed_modes):
            return True
        if norm in ("walking", "transfer") and ("walking" in self.allowed_modes or "walk" in self.allowed_modes or "transfer" in self.allowed_modes):
            return True
        if norm == "bike" and ("bike" in self.allowed_modes or "cycling" in self.allowed_modes):
            return True
        return False

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
                        if self.allowed_modes is not None:
                            mode_str = e.mode.value if hasattr(e.mode, "value") else str(e.mode)
                            if not self._is_mode_allowed(mode_str):
                                continue
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
