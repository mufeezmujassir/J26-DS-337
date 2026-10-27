from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents.recommendation_graph.builder import build_recommendation_graph
from app.agents.recommendation_graph.nodes import RecommendationGraphNodes
from app.agents.recommendation_graph.services.llm_service import IntentExtractionService


class AsyncTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def ainvoke(self, value):
        self.calls.append(value)
        return self.result


def base_state(message):
    return {
        "session_id": "session-001", "request_id": "request-001", "owner_hash": "hash",
        "user_message": message,
        "trusted_current_datetime": datetime(2026, 10, 21, 10, tzinfo=ZoneInfo("Asia/Colombo")).isoformat(),
        "reranker_configuration": "R3_WEATHER_SEASONALITY_REDUNDANCY_CONTROLLED",
        "candidate_limit": 10, "result_limit": 3, "clarification_turns": 0,
        "errors": [], "warnings": [], "nodes_executed": [], "tool_calls": [], "graph_status": "RUNNING",
    }


def nodes(recommendation_result):
    return RecommendationGraphNodes(
        intent_service=IntentExtractionService(),
        destination_tool=AsyncTool({"status": "RESOLVED", "district_id": 1, "district_name": "Kandy"}),
        activity_tool=AsyncTool({"status": "NOT_REQUESTED", "activity_type_id": None}),
        recommendation_tool=AsyncTool(recommendation_result), max_clarification_turns=3,
    )


@pytest.mark.asyncio
async def test_graph_interrupts_and_resumes_missing_destination():
    recommendation = {
        "candidates": [], "original_candidate_order": [], "experimental_candidate_order": [],
        "production_candidate_order": [], "errors": [],
    }
    graph = build_recommendation_graph(nodes(recommendation), MemorySaver())
    config = {"configurable": {"thread_id": "session-001"}}
    first = await graph.ainvoke(base_state("Suggest attractions tomorrow evening"), config)
    assert first["graph_status"] == "CLARIFICATION_REQUIRED"
    assert first["missing_fields"] == ["destination"]
    second = await graph.ainvoke(Command(resume="Kandy"), config)
    assert second["graph_status"] == "COMPLETED"
    assert second["destination_id"] == 1
    assert "group_emotion" not in second["recommendation_request"]["contextual_metadata"]


@pytest.mark.asyncio
async def test_graph_preserves_production_order_and_verifies_scores():
    candidate = {
        "attraction_id": 7, "attraction_name": "Temple", "original_semantic_score": 0.8,
        "normalized_semantic_score": 0.9, "original_semantic_rank": 1,
        "final_experimental_context_score": 0.85, "experimental_rank": 1, "rank_movement": 0,
        "context_score": 0.75, "evidence": {}, "contributions": [], "evidence_availability": {},
        "source_provenance": {}, "confidence": 0.7, "limitations": [],
        "explanation": {"positive_factors": [], "negative_factors": [], "missing_dimensions": ["weather"],
                        "evidence_sources": [], "limitations": [], "summary": "Limited evidence"},
    }
    recommendation = {"candidates": [candidate], "original_candidate_order": [7],
                      "experimental_candidate_order": [7], "production_candidate_order": [7], "errors": []}
    graph = build_recommendation_graph(nodes(recommendation), MemorySaver())
    state = await graph.ainvoke(base_state("Visit Kandy tomorrow at 9am"),
                               {"configurable": {"thread_id": "complete-001"}})
    assert state["graph_status"] == "COMPLETED"
    assert state["final_response"]["production_candidate_order"] == [7]
    assert state["verification"]["missing_dimensions"] == {7: ["weather"]}


@pytest.mark.asyncio
async def test_verifier_rejects_invalid_score_and_changed_production_order():
    invalid = {"attraction_id": 9, "attraction_name": "Unsafe", "final_experimental_context_score": 2.0,
               "explanation": {"missing_dimensions": []}}
    recommendation = {"candidates": [invalid], "original_candidate_order": [9],
                      "experimental_candidate_order": [9], "production_candidate_order": [10], "errors": []}
    graph = build_recommendation_graph(nodes(recommendation), MemorySaver())
    state = await graph.ainvoke(base_state("Visit Kandy tomorrow at 9am"),
                               {"configurable": {"thread_id": "invalid-001"}})
    assert state["graph_status"] == "FAILED"
    assert {error["code"] for error in state["errors"]} == {"INVALID_SCORE", "PRODUCTION_ORDER_CHANGED"}
