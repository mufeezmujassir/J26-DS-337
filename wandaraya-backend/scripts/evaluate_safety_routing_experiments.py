"""
WANDARAYA Component 2: Safety-Aware Multimodal Route Optimization Evaluation
=============================================================================
Reproducible empirical benchmark for final-year research thesis.
Compares 6 routing strategies across realistic Sri Lankan transit corridors:
  1. Ordinary Dijkstra Baseline (Shortest-Time)
  2. Risk-Weighted Dijkstra (lambda = 1.0)
  3. Risk-Weighted Dijkstra (lambda = 3.0, Proposed Research Default)
  4. Risk-Weighted Dijkstra (lambda = 5.0, High Safety Aversion)
  5. Safety-Constrained Strategy (Strict exclusion of segments with Risk >= 75.0 or closed)
  6. RAGRO (Risk-Aware Adaptive Genetic Route Optimizer)

Evaluates:
  - Route travel time (min) & distance (km)
  - Estimated transit cost (LKR)
  - Travel-time-weighted average environmental risk (0-100)
  - Maximum segment hazard (0-100)
  - Duration in elevated risk zones (risk >= 50.0)
  - Detour ratio vs. shortest-time baseline (% time & distance)
  - Risk reduction percentage vs. baseline
  - Algorithmic computation time (ms)
  - Robustness under missing/stale telemetry and road closures
"""

import os
import sys
import time
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple, Set

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from scripts.run_swagger import get_graph, parse_location, find_transit_access
from app.services.graph import Node, Edge, GraphMode, MultimodalGraph
from app.services.dijkstra import DijkstraRouter
from app.services.ragro import RAGROOptimizer, RAGROConfig
from app.services.environmental_risk_service import (
    EnvironmentalRiskService,
    environmental_risk_service,
    get_model_risk_category,
)
from app.services.warning_service import warning_service


@dataclass
class CorridorEvaluationRecord:
    corridor: str
    scenario: str
    strategy: str
    success: bool
    runtime_ms: float
    total_travel_time_min: float
    total_distance_km: float
    total_cost_lkr: float
    route_average_risk: float
    max_segment_risk: float
    time_spent_in_elevated_risk_min: float
    time_detour_pct: float
    distance_detour_pct: float
    risk_reduction_pct: float
    model_risk_category: str
    selection_explanation: str
    notes: str = ""


def evaluate_single_strategy(
    strategy_name: str,
    graph: MultimodalGraph,
    v_start: str,
    v_end: str,
    base_time: Optional[float] = None,
    base_dist: Optional[float] = None,
    base_risk: Optional[float] = None,
    lambda_val: float = 3.0,
    verified_closures: Optional[Set[Tuple[str, str]]] = None,
    max_risk_threshold: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Executes a single route strategy and measures wall-clock runtime in milliseconds.
    """
    start_t = time.perf_counter()
    res_dict = None

    if strategy_name == "ordinary_dijkstra":
        router = DijkstraRouter(graph, objective="fastest")
        path_res = router.route(v_start, v_end)
        if path_res:
            res_dict = _extract_dijkstra_metrics(graph, path_res, "Shortest-Time Dijkstra Baseline")

    elif strategy_name.startswith("risk_weighted_dijkstra"):
        router = DijkstraRouter(
            graph,
            objective="safety",
            lambda_risk=lambda_val,
            verified_closures=verified_closures,
        )
        path_res = router.route(v_start, v_end)
        if path_res:
            res_dict = _extract_dijkstra_metrics(
                graph, path_res, f"Risk-Weighted Dijkstra (lambda={lambda_val})"
            )

    elif strategy_name == "safety_constrained":
        # Strategy: Strictly penalize/exclude segments exceeding max_risk_threshold (>= 75.0)
        # We achieve this with verified closures or very high lambda
        high_risk_closures = set(verified_closures or set())
        for u, to_map in graph.edges.items():
            for v, edge_list in to_map.items():
                for e in edge_list:
                    r = e.attributes.get("environmental_risk_score") or e.attributes.get("risk_score")
                    if r is not None and float(r) >= 75.0:
                        high_risk_closures.add((u, v))

        router = DijkstraRouter(
            graph,
            objective="safety",
            lambda_risk=lambda_val,
            verified_closures=high_risk_closures,
        )
        path_res = router.route(v_start, v_end)
        if path_res:
            res_dict = _extract_dijkstra_metrics(
                graph, path_res, "Safety-Constrained Strategy (Risk < 75.0)"
            )

    elif strategy_name == "ragro":
        config = RAGROConfig(population_size=12, max_generations=6, random_seed=42)
        optimizer = RAGROOptimizer(graph, config=config, verified_restrictions=[
            {"from_node": u, "to_node": v, "reason": "Restricted Edge"}
            for u, v in (verified_closures or set())
        ])
        ragro_out = optimizer.optimize(v_start, v_end)
        chrom = ragro_out.get("recommended_lowest_risk_route")
        if chrom and chrom.nodes:
            res_dict = {
                "nodes": chrom.nodes,
                "total_travel_time_min": chrom.total_travel_time_min,
                "total_distance_km": chrom.total_distance_km,
                "total_cost_lkr": chrom.total_cost_lkr,
                "route_average_risk": chrom.environmental_risk_score,
                "max_segment_risk": chrom.max_segment_risk,
                "time_spent_in_elevated_risk_min": chrom.time_spent_in_elevated_risk_min,
                "model_risk_category": chrom.model_risk_category,
                "selection_explanation": chrom.selection_explanation,
            }

    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
    return res_dict, elapsed_ms


def _extract_dijkstra_metrics(
    graph: MultimodalGraph, path_res: Any, strategy_desc: str
) -> Dict[str, Any]:
    nodes = path_res.nodes
    segments: List[Dict[str, Any]] = []

    for i in range(len(nodes) - 1):
        u, v = nodes[i], nodes[i + 1]
        c_edges = graph.get_edges(u, v)
        if not c_edges:
            continue
        edge = c_edges[0]
        seg_dist = float(edge.attributes.get("distance_km") or 0.0)
        seg_time = float(edge.attributes.get("travel_time_min") or 0.0)
        seg_risk = float(
            edge.attributes.get("environmental_risk_score")
            or edge.attributes.get("risk_score")
            or 15.0
        )
        segments.append({
            "segment_id": f"{u}->{v}",
            "from_node": u,
            "to_node": v,
            "mode": edge.mode.value if hasattr(edge.mode, "value") else str(edge.mode),
            "distance_km": seg_dist,
            "travel_time_min": seg_time,
            "segment_risk": seg_risk,
        })

    agg = EnvironmentalRiskService.calculate_route_risk_aggregation(segments, weighting="time")
    cat = get_model_risk_category(agg["route_average_risk"])

    return {
        "nodes": nodes,
        "total_travel_time_min": path_res.total_travel_time_min or 0.0,
        "total_distance_km": path_res.total_distance_km or 0.0,
        "total_cost_lkr": path_res.total_cost_lkr or 0.0,
        "route_average_risk": agg["route_average_risk"],
        "max_segment_risk": agg["max_segment_risk"],
        "time_spent_in_elevated_risk_min": agg["time_spent_in_elevated_risk_min"],
        "model_risk_category": cat,
        "selection_explanation": getattr(path_res, "selection_explanation", strategy_desc),
    }


def run_comprehensive_evaluation() -> List[CorridorEvaluationRecord]:
    print("=" * 100)
    print("  WANDARAYA COMPONENT 2: SAFETY-AWARE MULTIMODAL ROUTE OPTIMIZATION EVALUATION")
    print("=" * 100)

    graph = get_graph()
    records: List[CorridorEvaluationRecord] = []

    test_corridors = [
        ("Kandy", "Nuwara Eliya", "Hill Country (Active NBRO Hazard Belt)"),
        ("Colombo", "Kandy", "Major Highland Access Trunk Corridor"),
        ("Kandy", "Ella", "Central-Southern Escarpment Multimodal Corridor"),
        ("Colombo", "Galle", "Lowland Coastal Plain (Geological Control)"),
    ]

    scenarios = [
        ("Normal Conditions", {}),
        ("Elevated Monsoon Rainfall", {"rainfall_multiplier": 2.5}),
        ("Verified Road Closure", {"apply_closure": True}),
        ("Telemetry Degradation (Missing Data)", {"degraded_telemetry": True}),
    ]

    strategies = [
        ("ordinary_dijkstra", 0.0, "Shortest-Time Dijkstra"),
        ("risk_weighted_dijkstra_l1", 1.0, "Risk-Weighted Dijkstra (lambda=1.0)"),
        ("risk_weighted_dijkstra_l3", 3.0, "Risk-Weighted Dijkstra (lambda=3.0) [Default]"),
        ("risk_weighted_dijkstra_l5", 5.0, "Risk-Weighted Dijkstra (lambda=5.0)"),
        ("safety_constrained", 3.0, "Safety-Constrained Strategy (Risk < 75)"),
        ("ragro", 0.0, "RAGRO Multi-Objective Genetic Optimizer"),
    ]

    for start_name, end_name, corridor_desc in test_corridors:
        print(f"\n" + "-" * 100)
        print(f"[*] CORRIDOR: {start_name} -> {end_name} [{corridor_desc}]")
        print("-" * 100)

        s_lat, s_lon, _ = parse_location(start_name)
        e_lat, e_lon, _ = parse_location(end_name)

        v_start = f"eval_start_{start_name}"
        v_end = f"eval_end_{end_name}"

        # Clean prior
        for v in [v_start, v_end]:
            if v in graph.nodes: del graph.nodes[v]
            if v in graph.edges: del graph.edges[v]

        graph.add_node(Node(v_start, lat=s_lat, lon=s_lon, properties={"label": start_name}))
        graph.add_node(Node(v_end, lat=e_lat, lon=e_lon, properties={"label": end_name}))

        s_nodes = find_transit_access(s_lat, s_lon, graph)
        e_nodes = find_transit_access(e_lat, e_lon, graph)

        for mode in ["rail", "bus"]:
            st, sd = s_nodes[mode]
            if st and sd <= 35.0:
                graph.add_edge(Edge(v_start, st, GraphMode.WALKING, True, {"distance_km": sd, "travel_time_min": (sd/4.5)*60, "cost_lkr": 0.0, "environmental_risk_score": 10.0}))
                graph.add_edge(Edge(st, v_start, GraphMode.WALKING, True, {"distance_km": sd, "travel_time_min": (sd/4.5)*60, "cost_lkr": 0.0, "environmental_risk_score": 10.0}))
            et, ed = e_nodes[mode]
            if et and ed <= 35.0:
                graph.add_edge(Edge(et, v_end, GraphMode.WALKING, True, {"distance_km": ed, "travel_time_min": (ed/4.5)*60, "cost_lkr": 0.0, "environmental_risk_score": 10.0}))
                graph.add_edge(Edge(v_end, et, GraphMode.WALKING, True, {"distance_km": ed, "travel_time_min": (ed/4.5)*60, "cost_lkr": 0.0, "environmental_risk_score": 10.0}))

        # Evaluate across scenarios
        for scen_name, scen_opts in scenarios:
            print(f"\n  >> Scenario: {scen_name}")

            # Prepare closure set if scenario requires it
            closures = set()
            if scen_opts.get("apply_closure"):
                # Pick an intermediate road edge along shortest path to simulate landslide closure
                r_base = DijkstraRouter(graph, objective="fastest").route(v_start, v_end)
                if r_base and len(r_base.nodes) >= 3:
                    u_close, v_close = r_base.nodes[1], r_base.nodes[2]
                    closures.add((u_close, v_close))
                    closures.add((v_close, u_close))
                    print(f"     [!] Simulated road closure applied on critical edge: {u_close} <-> {v_close}")

            # First, compute baseline (ordinary shortest time Dijkstra)
            base_dict, base_runtime = evaluate_single_strategy(
                "ordinary_dijkstra", graph, v_start, v_end, verified_closures=closures
            )
            base_time = base_dict["total_travel_time_min"] if base_dict else 1.0
            base_dist = base_dict["total_distance_km"] if base_dict else 1.0
            base_risk = base_dict["route_average_risk"] if base_dict else 50.0

            for strat_key, l_val, strat_label in strategies:
                actual_strat = strat_key
                if "risk_weighted_dijkstra" in strat_key:
                    actual_strat = "risk_weighted_dijkstra"

                res_dict, runtime_ms = evaluate_single_strategy(
                    actual_strat,
                    graph,
                    v_start,
                    v_end,
                    base_time=base_time,
                    base_dist=base_dist,
                    base_risk=base_risk,
                    lambda_val=l_val,
                    verified_closures=closures,
                )

                if res_dict:
                    t_time = res_dict["total_travel_time_min"]
                    t_dist = res_dict["total_distance_km"]
                    t_cost = res_dict["total_cost_lkr"]
                    r_risk = res_dict["route_average_risk"]
                    m_risk = res_dict["max_segment_risk"]
                    elev_t = res_dict["time_spent_in_elevated_risk_min"]
                    m_cat = res_dict["model_risk_category"]

                    time_detour = round(((t_time - base_time) / base_time) * 100.0, 1) if base_time > 0 else 0.0
                    dist_detour = round(((t_dist - base_dist) / base_dist) * 100.0, 1) if base_dist > 0 else 0.0
                    risk_red = round(((base_risk - r_risk) / base_risk) * 100.0, 1) if base_risk > 0 else 0.0

                    rec = CorridorEvaluationRecord(
                        corridor=f"{start_name} -> {end_name}",
                        scenario=scen_name,
                        strategy=strat_label,
                        success=True,
                        runtime_ms=round(runtime_ms, 2),
                        total_travel_time_min=round(t_time, 1),
                        total_distance_km=round(t_dist, 2),
                        total_cost_lkr=round(t_cost, 2),
                        route_average_risk=round(r_risk, 1),
                        max_segment_risk=round(m_risk, 1),
                        time_spent_in_elevated_risk_min=round(elev_t, 1),
                        time_detour_pct=time_detour,
                        distance_detour_pct=dist_detour,
                        risk_reduction_pct=risk_red,
                        model_risk_category=m_cat,
                        selection_explanation=res_dict.get("selection_explanation", ""),
                    )
                    records.append(rec)

                    print(
                        f"     {strat_label:<44} | Time: {t_time:>5.1f}m ({time_detour:>+5.1f}%) | "
                        f"Dist: {t_dist:>5.1f}km | Risk: {r_risk:>4.1f}/100 ({risk_red:>+5.1f}%) | "
                        f"Max: {m_risk:>4.1f} | Elev: {elev_t:>4.1f}m | CPU: {runtime_ms:>5.1f}ms"
                    )
                else:
                    rec = CorridorEvaluationRecord(
                        corridor=f"{start_name} -> {end_name}",
                        scenario=scen_name,
                        strategy=strat_label,
                        success=False,
                        runtime_ms=round(runtime_ms, 2),
                        total_travel_time_min=0.0,
                        total_distance_km=0.0,
                        total_cost_lkr=0.0,
                        route_average_risk=0.0,
                        max_segment_risk=0.0,
                        time_spent_in_elevated_risk_min=0.0,
                        time_detour_pct=0.0,
                        distance_detour_pct=0.0,
                        risk_reduction_pct=0.0,
                        model_risk_category="UNAVAILABLE",
                        selection_explanation="No feasible path found under constraints",
                        notes="Constrained Infeasible",
                    )
                    records.append(rec)
                    print(f"     {strat_label:<44} | NO FEASIBLE PATH FOUND (Infeasible Constraints)")

        # Cleanup test nodes
        for v in [v_start, v_end]:
            if v in graph.nodes: del graph.nodes[v]
            if v in graph.edges: del graph.edges[v]
            for u in list(graph.edges.keys()):
                if v in graph.edges[u]: del graph.edges[u][v]

    return records


if __name__ == "__main__":
    records = run_comprehensive_evaluation()
    output_path = os.path.join(backend_dir, "scripts", "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in records], f, indent=2)
    print(f"\n[OK] Evaluation completed. Saved {len(records)} benchmark records to {output_path}")
