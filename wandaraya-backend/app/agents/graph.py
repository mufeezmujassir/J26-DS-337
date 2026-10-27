"""Compatibility exports for the Stage 12.6 recommendation graph."""

from app.agents.recommendation_graph.builder import build_recommendation_graph
from app.agents.recommendation_graph.state import RecommendationGraphState

__all__ = ["RecommendationGraphState", "build_recommendation_graph"]
