from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class RecommendationGraphState(TypedDict, total=False):
    session_id: str
    request_id: str
    owner_hash: str
    user_message: str
    trusted_current_datetime: str
    reranker_configuration: str
    candidate_limit: int
    result_limit: int
    intent: dict[str, Any]
    query: str
    destination_text: str | None
    destination_id: int | None
    travel_date: str | None
    travel_time: str | None
    travel_end_time: str | None
    approximate_time_period: str | None
    activity_type_id: int | None
    requested_activities: list[str]
    user_interests: list[str]
    user_preferences: dict[str, Any]
    group_preferences: dict[str, Any]
    travel_constraints: dict[str, Any]
    missing_fields: list[str]
    clarification_required: bool
    clarification_question: str | None
    clarification_turns: int
    recommendation_request: dict[str, Any]
    recommendation_response: dict[str, Any]
    verification: dict[str, Any]
    final_response: dict[str, Any]
    errors: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    nodes_executed: Annotated[list[str], operator.add]
    tool_calls: Annotated[list[str], operator.add]
    graph_status: str
