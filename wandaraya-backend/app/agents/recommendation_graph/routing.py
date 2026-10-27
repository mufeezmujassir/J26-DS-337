from app.agents.recommendation_graph.state import RecommendationGraphState


def after_validation(state: RecommendationGraphState) -> str:
    if state.get("graph_status") == "FAILED":
        return "compose_response"
    return "clarify_request" if state.get("clarification_required") else "resolve_destination"


def after_destination(state: RecommendationGraphState) -> str:
    if state.get("graph_status") == "FAILED":
        return "compose_response"
    return "clarify_request" if state.get("clarification_required") else "resolve_activity"


def after_recommendation(state: RecommendationGraphState) -> str:
    return "compose_response" if state.get("graph_status") == "FAILED" else "verify_results"
