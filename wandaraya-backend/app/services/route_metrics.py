import math
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from app.services.graph import Edge, GraphMode

@dataclass
class CalculatedRouteMetrics:
    total_distance_km: float
    total_cost_lkr: Optional[float]
    cost_complete: bool
    known_cost_lkr: Optional[float]
    total_travel_time_min: Optional[float]
    travel_time_complete: bool
    known_travel_time_min: Optional[float]
    total_waiting_time_min: Optional[float]
    total_transfer_time_min: Optional[float]
    total_journey_time_min: Optional[float]
    journey_time_complete: bool
    is_travel_time_estimated: bool
    is_cost_estimated: bool
    modes_used: List[str]
    mode_sequence: List[str]
    mode_changes_count: int
    transfers_count: int
    transfer_locations: List[str]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_distance_km": self.total_distance_km,
            "total_cost_lkr": self.total_cost_lkr,
            "cost_complete": self.cost_complete,
            "known_cost_lkr": self.known_cost_lkr,
            "total_travel_time_min": self.total_travel_time_min,
            "travel_time_complete": self.travel_time_complete,
            "known_travel_time_min": self.known_travel_time_min,
            "total_waiting_time_min": self.total_waiting_time_min,
            "total_transfer_time_min": self.total_transfer_time_min,
            "total_journey_time_min": self.total_journey_time_min,
            "journey_time_complete": self.journey_time_complete,
            "is_travel_time_estimated": self.is_travel_time_estimated,
            "is_cost_estimated": self.is_cost_estimated,
            "modes_used": self.modes_used,
            "mode_sequence": self.mode_sequence,
            "mode_changes_count": self.mode_changes_count,
            "transfers_count": self.transfers_count,
            "transfer_locations": self.transfer_locations,
            "warnings": self.warnings,
        }

class RouteMetricsService:
    """
    Focused service for calculating comprehensive route metrics from traversed graph edges.
    Calculates distances, fares, journey/waiting/transfer times, mode transitions, and data completeness.
    Enforces zero-fabrication and clear distinction between known, partial, and estimated values.
    """

    @staticmethod
    def calculate_metrics(edges: List[Edge], nodes: Optional[List[str]] = None) -> CalculatedRouteMetrics:
        if not edges:
            return CalculatedRouteMetrics(
                total_distance_km=0.0,
                total_cost_lkr=0.0,
                cost_complete=True,
                known_cost_lkr=0.0,
                total_travel_time_min=0.0,
                travel_time_complete=True,
                known_travel_time_min=0.0,
                total_waiting_time_min=0.0,
                total_transfer_time_min=0.0,
                total_journey_time_min=0.0,
                journey_time_complete=True,
                is_travel_time_estimated=False,
                is_cost_estimated=False,
                modes_used=[],
                mode_sequence=[],
                mode_changes_count=0,
                transfers_count=0,
                transfer_locations=[],
                warnings=[]
            )

        edge_count = len(edges)
        warnings: List[str] = []

        # 1. Distance Calculation (km)
        total_dist = 0.0
        missing_dist_count = 0
        for e in edges:
            d = e.attributes.get("distance_km")
            if d is not None and isinstance(d, (int, float)) and math.isfinite(float(d)) and float(d) >= 0.0:
                total_dist += float(d)
            else:
                missing_dist_count += 1
        total_distance_km = round(total_dist, 4)
        if missing_dist_count > 0:
            warnings.append(f"Distance unavailable for {missing_dist_count} of {edge_count} edge(s).")

        # 2. Cost / Fare Calculation (LKR)
        known_cost_sum = 0.0
        known_cost_count = 0
        missing_cost_count = 0
        is_cost_est = False

        for e in edges:
            c = e.attributes.get("cost_lkr")
            if c is not None and isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(float(c)) and float(c) >= 0.0:
                known_cost_sum += float(c)
                known_cost_count += 1
                if e.attributes.get("is_cost_estimated", False):
                    is_cost_est = True
            else:
                missing_cost_count += 1

        cost_complete = (missing_cost_count == 0)
        total_cost_lkr = round(known_cost_sum, 2) if cost_complete else None
        known_cost_lkr = round(known_cost_sum, 2) if known_cost_count > 0 else None

        if not cost_complete:
            warnings.append(
                f"Travel cost unavailable for {missing_cost_count} of {edge_count} edge(s). "
                f"Total route cost not estimated (known subtotal: {known_cost_lkr} LKR)."
            )

        # 3. Travel Time, Waiting Time & Transfer Time (Minutes)
        known_travel_sum = 0.0
        known_travel_count = 0
        missing_travel_count = 0
        is_time_est = False

        total_waiting_sum = 0.0
        has_waiting_info = False

        total_transfer_time_sum = 0.0
        has_transfer_time_info = False

        for e in edges:
            t = e.attributes.get("travel_time_min")
            if t is not None and isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(float(t)) and float(t) >= 0.0:
                known_travel_sum += float(t)
                known_travel_count += 1
                if e.attributes.get("is_estimated", False):
                    is_time_est = True
            else:
                missing_travel_count += 1

            # Waiting time attribute (e.g. scheduled dwell/boarding time)
            w = e.attributes.get("waiting_time_min")
            if w is not None and isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(float(w)) and float(w) >= 0.0:
                total_waiting_sum += float(w)
                has_waiting_info = True

            # Transfer time attribute (e.g. walking/interchange time)
            tr = e.attributes.get("transfer_time_min")
            if tr is not None and isinstance(tr, (int, float)) and not isinstance(tr, bool) and math.isfinite(float(tr)) and float(tr) >= 0.0:
                total_transfer_time_sum += float(tr)
                has_transfer_time_info = True

        travel_time_complete = (missing_travel_count == 0)
        total_travel_time_min = round(known_travel_sum, 2) if travel_time_complete else None
        known_travel_time_min = round(known_travel_sum, 2) if known_travel_count > 0 else None

        total_waiting_time_min = round(total_waiting_sum, 2) if has_waiting_info else 0.0
        total_transfer_time_min = round(total_transfer_time_sum, 2) if has_transfer_time_info else 0.0

        # Total journey time = travel_time + waiting_time + transfer_time
        # Ensure we avoid double counting: if an edge's transfer time is already in travel_time_min,
        # the model attributes must distinguish them.
        journey_time_complete = travel_time_complete
        if journey_time_complete and total_travel_time_min is not None:
            # If waiting time or distinct transfer time are explicitly provided, add them
            total_journey_time_min = round(total_travel_time_min + total_waiting_time_min + total_transfer_time_min, 2)
        else:
            total_journey_time_min = None

        if not travel_time_complete:
            warnings.append(
                f"Travel time unavailable for {missing_travel_count} of {edge_count} edge(s). "
                f"Total duration not estimated (no hardcoded speed assumption; known subtotal: {known_travel_time_min} min)."
            )
        elif is_time_est:
            warnings.append("Travel time contains estimated segment durations.")

        # 4. Mode Sequence & Mode Changes
        mode_sequence = [e.mode.value if hasattr(e.mode, "value") else str(e.mode) for e in edges]
        modes_used: List[str] = []
        for m in mode_sequence:
            if m not in modes_used:
                modes_used.append(m)

        # Mode Changes: Count genuine vehicular/transit mode changes (e.g. Bus -> Rail)
        # Distinguish pure transfer links (walking/transfer) from primary transit modes
        mode_changes_count = 0
        primary_transit_modes = {"bus", "rail", "road"}
        transfer_modes = {"walking", "transfer"}

        # Track sequential primary modes
        prev_primary_mode: Optional[str] = None
        for m in mode_sequence:
            if m in primary_transit_modes:
                if prev_primary_mode is not None and m != prev_primary_mode:
                    mode_changes_count += 1
                prev_primary_mode = m

        # 5. Transfers Count and Transfer Locations
        transfers_count = 0
        transfer_locations: List[str] = []
        prev_mode: Optional[str] = None
        prev_was_transfer = False

        for idx, e in enumerate(edges):
            m_val = e.mode.value if hasattr(e.mode, "value") else str(e.mode)
            is_transfer_edge = (
                m_val == "transfer"
                or (hasattr(e, "mode") and getattr(e.mode, "name", None) == "TRANSFER")
                or bool(e.attributes.get("transfer_type"))
            )

            if is_transfer_edge:
                transfers_count += 1
                prev_was_transfer = True
                if e.from_node not in transfer_locations:
                    transfer_locations.append(e.from_node)
                if e.to_node not in transfer_locations:
                    transfer_locations.append(e.to_node)
            elif prev_mode is not None and m_val != prev_mode and not prev_was_transfer:
                # Direct mode change without a transfer edge
                transfers_count += 1
                prev_was_transfer = False
                if e.from_node not in transfer_locations:
                    transfer_locations.append(e.from_node)
            else:
                prev_was_transfer = False

            prev_mode = m_val

        return CalculatedRouteMetrics(
            total_distance_km=total_distance_km,
            total_cost_lkr=total_cost_lkr,
            cost_complete=cost_complete,
            known_cost_lkr=known_cost_lkr,
            total_travel_time_min=total_travel_time_min,
            travel_time_complete=travel_time_complete,
            known_travel_time_min=known_travel_time_min,
            total_waiting_time_min=total_waiting_time_min,
            total_transfer_time_min=total_transfer_time_min,
            total_journey_time_min=total_journey_time_min,
            journey_time_complete=journey_time_complete,
            is_travel_time_estimated=is_time_est,
            is_cost_estimated=is_cost_est,
            modes_used=modes_used,
            mode_sequence=mode_sequence,
            mode_changes_count=mode_changes_count,
            transfers_count=transfers_count,
            transfer_locations=transfer_locations,
            warnings=warnings
        )
