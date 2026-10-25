"""
RAGRO: Risk-Aware Adaptive Genetic Route Optimizer for WANDARAYA.
=================================================================
A multi-objective genetic algorithm for multimodal transit network routing under
dynamic environmental hazard and landslide risk constraints.

Key Architectural Components:
1. Chromosome: Valid, feasible sequence of graph nodes [v_0, v_1, ..., v_k].
2. Seeding: Initialized with Dijkstra Pareto candidates (shortest, fastest, cheapest, slower, scenic, safety)
   plus stochastic k-path perturbations.
3. Fitness Function: Multi-attribute objective incorporating:
   - Route-Level Environmental Risk (with maximum-segment risk penalty)
   - Travel Time (minutes)
   - Official Transit Fare Cost (LKR)
   - Total Path Distance (km)
   - Authoritative Closure / Restriction Ineligibility Penalty
4. Genetic Operators:
   - Shared-node crossover: Identifies topological intersection nodes between candidate parents.
   - Sub-path detour mutation: Re-routes between two intermediate nodes using alternative edge modes.
   - Adaptive operator probabilities: Dynamically scales crossover (p_c) and mutation (p_m) based on
     population edge diversity (Jaccard similarity).
   - Strict elitism: Retains top non-dominated candidate routes across generations.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.graph import MultimodalGraph, GraphMode, Edge, Node
from app.services.dijkstra import DijkstraRouter, DijkstraPathResult
from app.services.environmental_risk_service import environmental_risk_service
from app.services.scenic_service import scenic_service

logger = logging.getLogger(__name__)


@dataclass
class RAGROConfig:
    population_size: int = 16
    max_generations: int = 12
    base_crossover_prob: float = 0.70
    base_mutation_prob: float = 0.25
    tournament_size: int = 3
    elite_count: int = 3
    # Objective weights (must sum to 1.0)
    weight_risk: float = 0.40
    weight_time: float = 0.35
    weight_cost: float = 0.15
    weight_distance: float = 0.10
    random_seed: Optional[int] = 42


@dataclass
class RouteSegmentEvaluation:
    from_node: str
    to_node: str
    mode: str
    distance_km: float
    travel_time_min: float
    cost_lkr: float
    coordinates: List[Tuple[float, float]]
    landslide_susceptibility: float
    rainfall_risk: float
    weather_risk: float
    segment_environmental_risk: float
    segment_safety_indicator: float
    is_restricted: bool = False
    restriction_reason: Optional[str] = None


@dataclass
class RAGROChromosome:
    nodes: List[str]
    edges: List[Edge] = field(default_factory=list)
    total_distance_km: float = 0.0
    total_travel_time_min: float = 0.0
    total_cost_lkr: float = 0.0
    environmental_risk_score: float = 0.0
    safety_indicator: float = 100.0
    max_segment_risk: float = 0.0
    highest_risk_segment_id: Optional[str] = None
    highest_risk_segment_mode: Optional[str] = None
    time_spent_in_elevated_risk_min: float = 0.0
    distance_in_elevated_risk_km: float = 0.0
    model_risk_category: str = "Low model-estimated risk"
    selection_explanation: str = ""
    fitness: float = float("inf")
    is_eligible: bool = True
    ineligibility_reasons: List[str] = field(default_factory=list)
    segments: List[RouteSegmentEvaluation] = field(default_factory=list)
    coordinates: List[Tuple[float, float]] = field(default_factory=list)
    scenic_score: float = 0.0
    generation_found: int = 0
    route_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "nodes": self.nodes,
            "total_distance_km": round(self.total_distance_km, 2),
            "total_travel_time_min": round(self.total_travel_time_min, 1),
            "total_cost_lkr": round(self.total_cost_lkr, 2),
            "environmental_risk_score": round(self.environmental_risk_score, 1),
            "safety_indicator": round(self.safety_indicator, 1),
            "maximum_segment_risk": round(self.max_segment_risk, 1),
            "highest_risk_segment_id": self.highest_risk_segment_id,
            "highest_risk_segment_mode": self.highest_risk_segment_mode,
            "time_spent_in_elevated_risk_min": round(self.time_spent_in_elevated_risk_min, 1),
            "distance_in_elevated_risk_km": round(self.distance_in_elevated_risk_km, 2),
            "model_risk_category": self.model_risk_category,
            "selection_explanation": self.selection_explanation,
            "fitness": round(self.fitness, 4),
            "is_eligible": self.is_eligible,
            "ineligibility_reasons": self.ineligibility_reasons,
            "scenic_score": round(self.scenic_score, 1),
            "coordinates_count": len(self.coordinates),
        }


class RAGROOptimizer:
    """
    Risk-Aware Adaptive Genetic Route Optimizer.
    """

    def __init__(
        self,
        graph: MultimodalGraph,
        config: Optional[RAGROConfig] = None,
        allowed_modes: Optional[Set[str]] = None,
        verified_restrictions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.graph = graph
        self.config = config or RAGROConfig()
        self.allowed_modes = allowed_modes
        self.verified_restrictions = verified_restrictions or []
        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)

    def optimize(
        self,
        origin_node: str,
        dest_node: str,
        dijkstra_baseline_routes: Optional[Dict[str, DijkstraResult]] = None,
    ) -> Dict[str, Any]:
        """
        Executes genetic optimization between origin_node and dest_node.
        Returns optimized route set, Pareto front, convergence metrics, and recommended lowest-risk route.
        """
        if origin_node not in self.graph.nodes or dest_node not in self.graph.nodes:
            raise ValueError(f"Origin '{origin_node}' or Destination '{dest_node}' not in graph.")

        # 1. Initialize population from Dijkstra baselines + localized perturbations
        population: List[RAGROChromosome] = self._initialize_population(
            origin_node, dest_node, dijkstra_baseline_routes
        )

        if not population:
            # Fallback to single Dijkstra safety run
            router = DijkstraRouter(self.graph, objective="safety", allowed_modes=self.allowed_modes)
            res = router.route(origin_node, dest_node)
            if res:
                chrom = self._evaluate_chromosome(res.nodes, generation=0, route_id="dijkstra_safety")
                population = [chrom]
            else:
                raise ValueError(f"No feasible path could be found between '{origin_node}' and '{dest_node}'.")

        # Evaluate initial population
        for chrom in population:
            self._evaluate_fitness(chrom)

        generations_history: List[Dict[str, Any]] = []

        # 2. Main Genetic Evolution Loop
        current_pop = list(population)
        for gen in range(1, self.config.max_generations + 1):
            # Calculate population diversity (Jaccard edge similarity)
            diversity = self._calculate_population_diversity(current_pop)

            # Adapt operator probabilities
            # Low diversity -> boost mutation, lower crossover
            p_c = max(0.40, min(0.95, self.config.base_crossover_prob * (1.0 + (diversity - 0.5) * 0.4)))
            p_m = max(0.10, min(0.60, self.config.base_mutation_prob * (1.0 - (diversity - 0.5) * 0.6)))

            # Elitism: retain top N eligible individuals
            current_pop.sort(key=lambda c: (not c.is_eligible, c.fitness))
            next_pop: List[RAGROChromosome] = [self._clone_chromosome(c) for c in current_pop[:self.config.elite_count]]

            # Breeding loop
            while len(next_pop) < self.config.population_size:
                p1 = self._tournament_select(current_pop)
                p2 = self._tournament_select(current_pop)

                # Crossover
                if random.random() < p_c:
                    child_nodes = self._crossover(p1.nodes, p2.nodes)
                else:
                    child_nodes = list(p1.nodes if random.random() < 0.5 else p2.nodes)

                # Mutation
                if random.random() < p_m:
                    child_nodes = self._mutate(child_nodes)

                # Create and evaluate child if valid
                if child_nodes and self._is_valid_path(child_nodes):
                    child = self._evaluate_chromosome(child_nodes, generation=gen, route_id=f"ragro_g{gen}_c{len(next_pop)}")
                    self._evaluate_fitness(child)
                    next_pop.append(child)
                else:
                    # Keep a mutated version of a good parent
                    mutated = self._mutate(list(p1.nodes))
                    if mutated and self._is_valid_path(mutated):
                        child = self._evaluate_chromosome(mutated, generation=gen, route_id=f"ragro_g{gen}_c{len(next_pop)}")
                        self._evaluate_fitness(child)
                        next_pop.append(child)
                    else:
                        next_pop.append(self._clone_chromosome(p1))

            current_pop = next_pop[:self.config.population_size]
            best_gen = min(current_pop, key=lambda c: (not c.is_eligible, c.fitness))
            generations_history.append({
                "generation": gen,
                "best_fitness": round(best_gen.fitness, 4),
                "best_risk": round(best_gen.environmental_risk_score, 1),
                "diversity_jaccard": round(diversity, 3),
                "crossover_prob": round(p_c, 3),
                "mutation_prob": round(p_m, 3),
            })

        # 3. Final Pareto and Recommendation Selection
        current_pop.sort(key=lambda c: (not c.is_eligible, c.fitness))
        eligible_routes = [c for c in current_pop if c.is_eligible]
        best_overall = eligible_routes[0] if eligible_routes else current_pop[0]

        # Recommended lowest-risk route: among eligible routes, lowest environmental_risk_score,
        # with max_segment_risk and travel time as tie-breakers.
        if eligible_routes:
            lowest_risk_route = min(
                eligible_routes,
                key=lambda c: (c.environmental_risk_score, c.max_segment_risk, c.total_travel_time_min)
            )
        else:
            lowest_risk_route = best_overall

        # Deduplicate distinctive alternative routes for frontend presentation
        distinct_routes = self._select_distinct_alternatives(current_pop, top_k=5)

        return {
            "status": "OPTIMAL" if eligible_routes else "SUBOPTIMAL_CONSTRAINTS",
            "algorithm": "RAGRO",
            "generations_completed": self.config.max_generations,
            "population_size": len(current_pop),
            "recommended_lowest_risk_route": lowest_risk_route,
            "best_overall_fitness_route": best_overall,
            "distinct_alternatives": distinct_routes,
            "generations_history": generations_history,
            "weights_used": {
                "risk": self.config.weight_risk,
                "time": self.config.weight_time,
                "cost": self.config.weight_cost,
                "distance": self.config.weight_distance,
            },
        }

    def _initialize_population(
        self,
        origin_node: str,
        dest_node: str,
        dijkstra_baseline_routes: Optional[Dict[str, DijkstraResult]]
    ) -> List[RAGROChromosome]:
        pop: List[RAGROChromosome] = []
        seen_paths: Set[Tuple[str, ...]] = set()

        # Add existing Dijkstra baselines
        objectives = ["shortest", "fastest", "cheapest", "slower", "scenic", "safety"]
        for idx, obj in enumerate(objectives):
            res = None
            if dijkstra_baseline_routes and obj in dijkstra_baseline_routes:
                res = dijkstra_baseline_routes[obj]
            else:
                try:
                    router = DijkstraRouter(self.graph, objective=obj, allowed_modes=self.allowed_modes)
                    res = router.route(origin_node, dest_node)
                except Exception:
                    pass

            if res and res.nodes:
                p_tuple = tuple(res.nodes)
                if p_tuple not in seen_paths:
                    seen_paths.add(p_tuple)
                    chrom = self._evaluate_chromosome(res.nodes, generation=0, route_id=f"dijkstra_{obj}")
                    pop.append(chrom)

        # Generate stochastic perturbations around baseline paths to reach population_size
        if pop:
            base_nodes = list(pop[0].nodes)
            attempts = 0
            while len(pop) < self.config.population_size and attempts < 35:
                attempts += 1
                mutated_nodes = self._mutate(list(base_nodes))
                if mutated_nodes and self._is_valid_path(mutated_nodes):
                    p_tuple = tuple(mutated_nodes)
                    if p_tuple not in seen_paths:
                        seen_paths.add(p_tuple)
                        chrom = self._evaluate_chromosome(
                            mutated_nodes, generation=0, route_id=f"ragro_seed_{len(pop)}"
                        )
                        pop.append(chrom)

        return pop

    def _evaluate_chromosome(
        self,
        nodes: List[str],
        generation: int = 0,
        route_id: str = ""
    ) -> RAGROChromosome:
        """
        Calculates all physical and environmental risk metrics along the node path.
        """
        edges: List[Edge] = []
        total_dist = 0.0
        total_time = 0.0
        total_cost = 0.0
        coords: List[Tuple[float, float]] = []
        segments: List[RouteSegmentEvaluation] = []
        is_eligible = True
        ineligibility_reasons = []

        for i in range(len(nodes) - 1):
            u, v = nodes[i], nodes[i + 1]
            # Retrieve best edge between u and v
            candidate_edges = self.graph.get_edges(u, v)
            if not candidate_edges:
                return RAGROChromosome(
                    nodes=nodes,
                    is_eligible=False,
                    ineligibility_reasons=[f"Missing edge between {u} and {v}"]
                )

            # Filter by allowed modes if present
            valid_e = candidate_edges
            if self.allowed_modes:
                valid_e = [
                    e for e in candidate_edges
                    if (e.mode.value if hasattr(e.mode, "value") else str(e.mode)).lower() in self.allowed_modes
                ] or candidate_edges

            # Pick lowest-weight edge
            edge = min(valid_e, key=lambda e: float(e.attributes.get("distance_km") or 0.0))
            edges.append(edge)

            seg_dist = float(edge.attributes.get("distance_km") or 0.0)
            seg_time = float(edge.attributes.get("travel_time_min") or 0.0)
            seg_cost = float(edge.attributes.get("cost_lkr") or 0.0)
            total_dist += seg_dist
            total_time += seg_time
            total_cost += seg_cost

            # Coordinates for segment
            u_node = self.graph.get_node(u)
            v_node = self.graph.get_node(v)
            u_c = (u_node.lat, u_node.lon) if (u_node and u_node.lat is not None and u_node.lon is not None) else None
            v_c = (v_node.lat, v_node.lon) if (v_node and v_node.lat is not None and v_node.lon is not None) else None

            seg_coords = []
            if u_c:
                seg_coords.append(u_c)
                if not coords or coords[-1] != u_c:
                    coords.append(u_c)
            if v_c:
                seg_coords.append(v_c)
                coords.append(v_c)

            # Check verified restrictions / closures
            is_seg_restricted = False
            restr_reason = None
            for r in self.verified_restrictions:
                if r.get("from_node") == u and r.get("to_node") == v:
                    is_seg_restricted = True
                    restr_reason = r.get("reason", "Verified Road Closure")
                    is_eligible = False
                    ineligibility_reasons.append(f"Segment {u}->{v}: {restr_reason}")

            # Environmental risk of this segment
            # Formula:
            # DynamicLandslideScore = 0.60 * L + 0.40 * R
            # EnvironmentalRisk = 0.60 * DynamicLandslideScore + 0.40 * W = 0.36 * L + 0.24 * R + 0.40 * W
            # SegmentSafetyIndicator = 100 - SegmentEnvironmentalRisk
            seg_ls = 0.0
            precomputed_risk = edge.attributes.get("environmental_risk_score")
            if precomputed_risk is None:
                precomputed_risk = edge.attributes.get("risk_score")

            if edge.attributes.get("landslide_proximity") is True:
                seg_ls = 75.0
            elif edge.attributes.get("landslide_proximity") is False:
                seg_ls = 0.0
            elif u_c and v_c:
                mid_lat = (u_c[0] + v_c[0]) / 2.0
                mid_lon = (u_c[1] + v_c[1]) / 2.0
                try:
                    from app.services.landslide_service import landslide_service
                    susc, _ = landslide_service.get_susceptibility_score(mid_lat, mid_lon)
                    if susc is not None and susc > 0:
                        seg_ls = float(susc)
                except Exception:
                    pass

            seg_r = float(edge.attributes.get("rainfall_risk", 5.0))
            seg_w = float(edge.attributes.get("weather_risk", 5.0))

            if precomputed_risk is not None:
                seg_env_risk = round(float(precomputed_risk), 2)
            else:
                dyn_ls = 0.60 * seg_ls + 0.40 * seg_r
                seg_env_risk = round(0.60 * dyn_ls + 0.40 * seg_w, 2)
            seg_safety = round(100.0 - seg_env_risk, 2)

            segments.append(RouteSegmentEvaluation(
                from_node=u,
                to_node=v,
                mode=edge.mode.value if hasattr(edge.mode, "value") else str(edge.mode),
                distance_km=seg_dist,
                travel_time_min=seg_time,
                cost_lkr=seg_cost,
                coordinates=seg_coords,
                landslide_susceptibility=seg_ls,
                rainfall_risk=seg_r,
                weather_risk=seg_w,
                segment_environmental_risk=seg_env_risk,
                segment_safety_indicator=seg_safety,
                is_restricted=is_seg_restricted,
                restriction_reason=restr_reason,
            ))

        # Route-level risk aggregation
        # RouteRisk = sum(segment_risk * segment_travel_time) / sum(segment_travel_time)
        # (or distance-weighted if time is 0)
        route_risk = 0.0
        max_seg_risk = 0.0
        highest_risk_seg_id = None
        highest_risk_seg_mode = None
        time_spent_elevated = 0.0
        dist_spent_elevated = 0.0

        if segments:
            max_seg_risk = max(s.segment_environmental_risk for s in segments)
            high_segs = [s for s in segments if s.segment_environmental_risk == max_seg_risk]
            if high_segs:
                highest_risk_seg_id = f"{high_segs[0].from_node}->{high_segs[0].to_node}"
                highest_risk_seg_mode = high_segs[0].mode

            if total_time > 0.0:
                weighted_sum = sum(s.segment_environmental_risk * s.travel_time_min for s in segments)
                route_risk = round(weighted_sum / total_time, 2)
            elif total_dist > 0.0:
                weighted_sum = sum(s.segment_environmental_risk * s.distance_km for s in segments)
                route_risk = round(weighted_sum / total_dist, 2)
            else:
                route_risk = round(sum(s.segment_environmental_risk for s in segments) / len(segments), 2)

            time_spent_elevated = sum(s.travel_time_min for s in segments if s.segment_environmental_risk >= 50.0)
            dist_spent_elevated = sum(s.distance_km for s in segments if s.segment_environmental_risk >= 50.0)

        safety_indicator = round(100.0 - route_risk, 2)
        from app.services.environmental_risk_service import get_model_risk_category
        risk_cat = get_model_risk_category(route_risk)
        explanation = (
            f"RAGRO multi-objective candidate: Travel-time-weighted risk {route_risk:.1f}/100 ({risk_cat}), "
            f"max segment risk {max_seg_risk:.1f}/100, elevated risk duration {time_spent_elevated:.1f} min."
        )

        return RAGROChromosome(
            nodes=nodes,
            edges=edges,
            total_distance_km=total_dist,
            total_travel_time_min=total_time,
            total_cost_lkr=total_cost,
            environmental_risk_score=route_risk,
            safety_indicator=safety_indicator,
            max_segment_risk=max_seg_risk,
            highest_risk_segment_id=highest_risk_seg_id,
            highest_risk_segment_mode=highest_risk_seg_mode,
            time_spent_in_elevated_risk_min=round(time_spent_elevated, 1),
            distance_in_elevated_risk_km=round(dist_spent_elevated, 2),
            model_risk_category=risk_cat,
            selection_explanation=explanation,
            is_eligible=is_eligible,
            ineligibility_reasons=ineligibility_reasons,
            segments=segments,
            coordinates=coords,
            generation_found=generation,
            route_id=route_id or f"ragro_{generation}_{len(nodes)}",
        )

    def _evaluate_fitness(self, chrom: RAGROChromosome) -> float:
        """
        Fitness evaluation:
        Fitness = w_risk * Norm(Risk) + w_time * Norm(Time) + w_cost * Norm(Cost) + w_dist * Norm(Dist)
        Plus penalties for maximum segment hazard hotspots and closure ineligibility.
        """
        if not chrom.is_eligible:
            chrom.fitness = 10000.0 + len(chrom.ineligibility_reasons) * 1000.0
            return chrom.fitness

        # Normalization references (typical intercity corridor scales in Sri Lanka)
        norm_risk = chrom.environmental_risk_score / 100.0
        norm_time = chrom.total_travel_time_min / 300.0  # ~5 hours
        norm_cost = chrom.total_cost_lkr / 2000.0
        norm_dist = chrom.total_distance_km / 200.0

        # Maximum segment risk hotspot penalty: ensures low average doesn't hide a lethal hotspot
        hotspot_penalty = (chrom.max_segment_risk / 100.0) * 0.15 if chrom.max_segment_risk > 65.0 else 0.0

        chrom.fitness = (
            self.config.weight_risk * norm_risk +
            self.config.weight_time * norm_time +
            self.config.weight_cost * norm_cost +
            self.config.weight_distance * norm_dist +
            hotspot_penalty
        )
        return chrom.fitness

    def _tournament_select(self, population: List[RAGROChromosome]) -> RAGROChromosome:
        candidates = random.sample(population, min(self.config.tournament_size, len(population)))
        return min(candidates, key=lambda c: (not c.is_eligible, c.fitness))

    def _crossover(self, p1_nodes: List[str], p2_nodes: List[str]) -> List[str]:
        """
        Shared-Node Topological Crossover.
        Finds intermediate nodes shared between p1 and p2 (excluding origin and destination).
        """
        if len(p1_nodes) < 3 or len(p2_nodes) < 3:
            return list(p1_nodes)

        # Candidate common crossover points
        common = [
            n for n in p1_nodes[1:-1]
            if n in p2_nodes[1:-1]
        ]
        if not common:
            return list(p1_nodes)

        split_node = random.choice(common)
        idx1 = p1_nodes.index(split_node)
        idx2 = p2_nodes.index(split_node)

        child = p1_nodes[:idx1] + p2_nodes[idx2:]
        # Remove loops
        child = self._remove_loops(child)
        return child

    def _mutate(self, nodes: List[str]) -> List[str]:
        """
        Sub-Path Detour Mutation.
        Selects two non-adjacent nodes and replaces the subpath with an alternative Dijkstra segment.
        """
        if len(nodes) < 4:
            return nodes

        i = random.randint(0, len(nodes) - 3)
        # Bounded local sub-path window (2 to 10 hops) for fast Dijkstra localized perturbation
        max_hop = min(len(nodes) - 1, i + 10)
        j = random.randint(i + 2, max_hop)
        u, v = nodes[i], nodes[j]

        # Route between u and v using a randomly chosen objective
        obj = random.choice(["shortest", "fastest", "cheapest", "scenic"])
        try:
            router = DijkstraRouter(self.graph, objective=obj, allowed_modes=self.allowed_modes)
            res = router.route(u, v)
            if res and res.nodes:
                new_path = nodes[:i] + res.nodes + nodes[j + 1:]
                return self._remove_loops(new_path)
        except Exception:
            pass

        return nodes

    def _remove_loops(self, path: List[str]) -> List[str]:
        seen = {}
        cleaned = []
        for node in path:
            if node in seen:
                # Truncate back to first occurrence
                idx = seen[node]
                cleaned = cleaned[:idx + 1]
                seen = {n: i for i, n in enumerate(cleaned)}
            else:
                seen[node] = len(cleaned)
                cleaned.append(node)
        return cleaned

    def _is_valid_path(self, nodes: List[str]) -> bool:
        if len(nodes) < 2:
            return False
        for i in range(len(nodes) - 1):
            if not self.graph.get_edges(nodes[i], nodes[i + 1]):
                return False
        return True

    def _calculate_population_diversity(self, population: List[RAGROChromosome]) -> float:
        """
        Calculates Jaccard edge similarity diversity across the population.
        0.0 = completely identical; 1.0 = completely disjoint edges.
        """
        if len(population) < 2:
            return 1.0

        all_edge_sets = [
            set(zip(c.nodes[:-1], c.nodes[1:]))
            for c in population if len(c.nodes) >= 2
        ]
        if not all_edge_sets:
            return 1.0

        pair_similarities = []
        for i in range(len(all_edge_sets)):
            for j in range(i + 1, len(all_edge_sets)):
                s1, s2 = all_edge_sets[i], all_edge_sets[j]
                union = len(s1.union(s2))
                if union > 0:
                    sim = len(s1.intersection(s2)) / union
                    pair_similarities.append(sim)

        if not pair_similarities:
            return 1.0
        avg_sim = sum(pair_similarities) / len(pair_similarities)
        return max(0.0, min(1.0, 1.0 - avg_sim))

    def _clone_chromosome(self, c: RAGROChromosome) -> RAGROChromosome:
        return RAGROChromosome(
            nodes=list(c.nodes),
            edges=list(c.edges),
            total_distance_km=c.total_distance_km,
            total_travel_time_min=c.total_travel_time_min,
            total_cost_lkr=c.total_cost_lkr,
            environmental_risk_score=c.environmental_risk_score,
            safety_indicator=c.safety_indicator,
            max_segment_risk=c.max_segment_risk,
            highest_risk_segment_id=c.highest_risk_segment_id,
            highest_risk_segment_mode=c.highest_risk_segment_mode,
            time_spent_in_elevated_risk_min=c.time_spent_in_elevated_risk_min,
            distance_in_elevated_risk_km=c.distance_in_elevated_risk_km,
            model_risk_category=c.model_risk_category,
            selection_explanation=c.selection_explanation,
            fitness=c.fitness,
            is_eligible=c.is_eligible,
            ineligibility_reasons=list(c.ineligibility_reasons),
            segments=list(c.segments),
            coordinates=list(c.coordinates),
            scenic_score=c.scenic_score,
            generation_found=c.generation_found,
            route_id=c.route_id,
        )

    def _select_distinct_alternatives(
        self,
        population: List[RAGROChromosome],
        top_k: int = 5
    ) -> List[RAGROChromosome]:
        """
        Picks distinctive alternative routes ensuring topological diversity.
        """
        unique: List[RAGROChromosome] = []
        seen_signatures: Set[str] = set()

        for c in population:
            # Signature based on mode count and intermediate nodes
            sig = f"{round(c.total_distance_km, 1)}_{round(c.total_travel_time_min, 0)}_{round(c.environmental_risk_score, 1)}"
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                unique.append(c)
                if len(unique) >= top_k:
                    break

        return unique or population[:top_k]
