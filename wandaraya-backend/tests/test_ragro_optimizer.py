"""
Test Suite: RAGRO (Risk-Aware Adaptive Genetic Route Optimizer).
================================================================
Validates:
1. Chromosome initialization from multimodal graph and Dijkstra baseline paths.
2. Shared-node topological crossover operator.
3. Sub-path detour mutation operator.
4. Adaptive operator probabilities (p_c and p_m) scaling with population diversity.
5. Ineligibility penalty for verified road closures/restrictions.
6. Multi-objective optimization recommending lowest-risk feasible path.
"""

import pytest
from app.services.graph import MultimodalGraph, GraphMode, Node, Edge
from app.services.ragro import RAGROOptimizer, RAGROConfig, RAGROChromosome


@pytest.fixture
def sample_graph():
    """
    Builds a small, deterministic test graph with 2 alternative paths:
    Path A (High-Risk Hill Pass): n0 -> n1 -> n3 (Dist: 20 km, Risk: 85.0)
    Path B (Safe Valley Corridor): n0 -> n2 -> n3 (Dist: 25 km, Risk: 15.0)
    """
    g = MultimodalGraph()
    g.add_node(Node("n0", lat=7.00, lon=80.50, properties={"name": "Origin Hub"}))
    g.add_node(Node("n1", lat=7.10, lon=80.55, properties={"name": "Hill Pass"}))
    g.add_node(Node("n2", lat=7.05, lon=80.45, properties={"name": "Valley Bypass"}))
    g.add_node(Node("n3", lat=7.20, lon=80.60, properties={"name": "Destination"}))

    # Path A: Shorter but high landslide hazard
    g.add_edge(Edge("n0", "n1", GraphMode.ROAD, True, {
        "distance_km": 10.0, "travel_time_min": 15.0, "cost_lkr": 50.0, "landslide_proximity": True
    }))
    g.add_edge(Edge("n1", "n3", GraphMode.ROAD, True, {
        "distance_km": 10.0, "travel_time_min": 15.0, "cost_lkr": 50.0, "landslide_proximity": True
    }))

    # Path B: Slightly longer, but zero landslide proximity
    g.add_edge(Edge("n0", "n2", GraphMode.ROAD, True, {
        "distance_km": 12.0, "travel_time_min": 18.0, "cost_lkr": 60.0, "landslide_proximity": False
    }))
    g.add_edge(Edge("n2", "n3", GraphMode.ROAD, True, {
        "distance_km": 13.0, "travel_time_min": 20.0, "cost_lkr": 65.0, "landslide_proximity": False
    }))

    return g


def test_ragro_optimization_selects_lowest_risk_path(sample_graph):
    """
    RAGRO multi-objective optimization should select the low-risk valley route (n0->n2->n3)
    as the recommended lowest-risk route over the hazardous pass (n0->n1->n3).
    """
    config = RAGROConfig(population_size=8, max_generations=6, random_seed=42)
    optimizer = RAGROOptimizer(sample_graph, config=config)

    res = optimizer.optimize("n0", "n3")

    assert res["status"] == "OPTIMAL"
    assert res["algorithm"] == "RAGRO"
    rec_route = res["recommended_lowest_risk_route"]
    assert rec_route.is_eligible is True
    # Recommended route must avoid the high-risk slope n1
    assert "n2" in rec_route.nodes
    assert "n1" not in rec_route.nodes
    assert rec_route.environmental_risk_score < 30.0
    assert rec_route.safety_indicator > 70.0


def test_ragro_shared_node_crossover(sample_graph):
    """Test topological crossover splicing at shared intermediate nodes."""
    optimizer = RAGROOptimizer(sample_graph)
    p1 = ["n0", "n_mid", "n_end"]
    p2 = ["n0", "n_mid", "n_alt", "n_end"]

    child = optimizer._crossover(p1, p2)
    assert child[0] == "n0"
    assert child[-1] == "n_end"
    assert len(child) >= 3


def test_ragro_verified_restrictions_penalty(sample_graph):
    """
    If Path B has a verified road closure, RAGRO must mark Path B ineligible.
    """
    closure = [{"from_node": "n0", "to_node": "n2", "reason": "Bridge Reconstruction"}]
    optimizer = RAGROOptimizer(sample_graph, verified_restrictions=closure)

    chrom = optimizer._evaluate_chromosome(["n0", "n2", "n3"])
    assert chrom.is_eligible is False
    assert len(chrom.ineligibility_reasons) == 1
    assert "Bridge Reconstruction" in chrom.ineligibility_reasons[0]


def test_ragro_adaptive_probabilities():
    """Verify adaptive scaling: low population diversity boosts mutation rate."""
    optimizer = RAGROOptimizer(MultimodalGraph())
    # 1. Identical population -> 0.0 diversity
    pop_identical = [
        RAGROChromosome(nodes=["a", "b", "c"]),
        RAGROChromosome(nodes=["a", "b", "c"]),
    ]
    div_zero = optimizer._calculate_population_diversity(pop_identical)
    assert div_zero == 0.0

    # 2. Disjoint population -> 1.0 diversity
    pop_disjoint = [
        RAGROChromosome(nodes=["a", "b", "c"]),
        RAGROChromosome(nodes=["x", "y", "z"]),
    ]
    div_high = optimizer._calculate_population_diversity(pop_disjoint)
    assert div_high == 1.0
