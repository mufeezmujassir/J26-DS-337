import math
import heapq
from typing import List, Tuple, Dict, Optional, Any, Set
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
    Component 2 Safety-Aware Dijkstra Cost Model:
      SafetyEdgeCost = SegmentTravelTime * [1 + lambda * (SegmentRisk / 100)^2]

    Principles:
    - lambda = 3.0 (configurable experimental sensitivity parameter, not a validated optimum).
    - SegmentTravelTime in minutes (calculated via TimeCostModel, or estimated from distance and transit speed).
    - SegmentRisk is on a 0-100 scale.
    - Excludes verified closed/restricted segments (closure_status == 'Closed' or is_closed is True).
    - Unknown risk is NOT treated as zero risk; uses configurable default_unknown_risk (default 15.0).
    - Ordinary shortest-time Dijkstra remains untouched via TimeCostModel as a scientific baseline.
    """

    def __init__(
        self,
        lambda_risk: float = 3.0,
        default_unknown_risk: float = 15.0,
        verified_closures: Optional[Set[Tuple[str, str]]] = None,
    ):
        self.lambda_risk = float(lambda_risk)
        self.default_unknown_risk = float(default_unknown_risk)
        self.verified_closures = verified_closures or set()

    @classmethod
    def calculate_edge_weight(
        cls,
        edge: Edge,
        lambda_risk: float = 3.0,
        default_unknown_risk: float = 15.0,
        verified_closures: Optional[Set[Tuple[str, str]]] = None,
    ) -> Optional[float]:
        inst = cls(
            lambda_risk=lambda_risk,
            default_unknown_risk=default_unknown_risk,
            verified_closures=verified_closures,
        )
        return inst.get_weight(edge)

    def get_cost(self, edge: Edge) -> Optional[float]:
        return self.get_weight(edge)

    def get_weight(self, edge: Optional[Edge] = None) -> Optional[float]:
        # Handle static invocation: EnvironmentalRiskCostModel.get_weight(edge)
        if edge is None and isinstance(self, Edge):
            return EnvironmentalRiskCostModel.calculate_edge_weight(self)

        if edge is None:
            return None

        # 1. Authoritative road closure check
        attrs = getattr(edge, "attributes", {}) or {}
        if str(attrs.get("closure_status", "")).lower() == "closed" or attrs.get("is_closed") is True:
            return None
        if self.verified_closures and (edge.from_node, edge.to_node) in self.verified_closures:
            return None

        # 2. Segment Travel Time in minutes
        val_t = TimeCostModel.get_weight(edge)
        if val_t is None:
            val_d = DistanceCostModel.get_weight(edge)
            if val_d is None:
                return None
            mode_str = str(getattr(edge.mode, "value", edge.mode)).lower()
            if "walk" in mode_str:
                speed_kmh = 4.5
            elif "bus" in mode_str:
                speed_kmh = 30.0
            elif "rail" in mode_str:
                speed_kmh = 40.0
            else:
                speed_kmh = 50.0
            val_t = (val_d / speed_kmh) * 60.0

        if val_t <= 0.0:
            val_t = 0.1

        # 3. Segment Environmental Risk (0-100 scale)
        raw_risk = attrs.get("segment_risk")
        if raw_risk is None:
            raw_risk = attrs.get("environmental_risk_score")
        if raw_risk is None:
            raw_risk = attrs.get("risk_score")

        if raw_risk is not None:
            try:
                seg_risk = min(100.0, max(0.0, float(raw_risk)))
            except (ValueError, TypeError):
                seg_risk = self.default_unknown_risk
        elif attrs.get("landslide_proximity") or attrs.get("hazard_detected"):
            seg_risk = 60.0
        elif attrs.get("warning_active"):
            seg_risk = 85.0
        else:
            seg_risk = self.default_unknown_risk

        # 4. Configurable Quadratic Penalty: TravelTime * [1 + lambda * (Risk / 100)^2]
        penalty = 1.0 + self.lambda_risk * ((seg_risk / 100.0) ** 2)
        return max(0.01, round(val_t * penalty, 4))


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
        optimized_weight: Optional[float] = None,
        selection_explanation: Optional[str] = None,
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
        elif self.objective in ("environmental_risk", "safe", "risk_aware", "safety", "safest"):
            self.optimized_weight = self.total_journey_time_min if self.total_journey_time_min is not None else self.total_travel_time_min
            self.warnings.append(
                "Safety-aware objective optimized using risk-weighted travel time penalizing segments with elevated landslide and weather hazards."
            )
        else:
            self.optimized_weight = optimized_weight

        # Clear, transparent route selection explanation
        if selection_explanation:
            self.selection_explanation = selection_explanation
        elif self.objective in ("shortest", "distance"):
            self.selection_explanation = f"Selected to minimize total travel distance ({round(self.total_distance_km, 2)} km) across available transportation links."
        elif self.objective in ("fastest", "time"):
            time_val = round(self.total_journey_time_min or self.total_travel_time_min or 0.0, 1)
            self.selection_explanation = f"Selected to minimize total journey time ({time_val} min) prioritizing high-speed transit corridors."
        elif self.objective in ("cheapest", "cost"):
            cost_val = round(self.total_cost_lkr or 0.0, 2)
            self.selection_explanation = f"Selected to minimize total passenger fare ({cost_val} LKR) utilizing regulated public transit tariffs."
        elif self.objective in ("slower", "slowest", "leisurely"):
            self.selection_explanation = "Selected for a relaxed, leisurely travel pace with lower transit speeds and relaxed connections."
        elif self.objective in ("scenic", "picturesque"):
            self.selection_explanation = "Selected to prioritize scenic beauty along picturesque coastal and hill-country railway and road corridors."
        elif self.objective in ("environmental_risk", "safe", "risk_aware", "safety", "safest"):
            self.selection_explanation = "Selected using safety-weighted Dijkstra (lambda=3.0) penalizing segments with elevated landslide susceptibility and severe weather hazards, avoiding known risk zones while excluding verified road closures."
        else:
            self.selection_explanation = f"Selected based on configured objective '{self.objective}'."

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
            "selection_explanation": self.selection_explanation,
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
        "safety": "environmental_risk",
        "safest": "environmental_risk",
    }

    def __init__(
        self,
        graph: MultimodalGraph,
        cost_model: Optional[Any] = None,
        objective: str = "shortest",
        allowed_modes: Optional[Any] = None,
        lambda_risk: float = 3.0,
        verified_closures: Optional[Set[Tuple[str, str]]] = None,
    ):
        self.graph = graph
        self.lambda_risk = float(lambda_risk)
        self.verified_closures = verified_closures or set()
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
            self.cost_model = EnvironmentalRiskCostModel(
                lambda_risk=self.lambda_risk,
                verified_closures=self.verified_closures,
            )

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
