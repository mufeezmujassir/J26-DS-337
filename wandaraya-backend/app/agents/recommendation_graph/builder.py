from langgraph.graph import END, START, StateGraph

from app.agents.recommendation_graph.nodes import RecommendationGraphNodes
from app.agents.recommendation_graph.routing import after_destination, after_recommendation, after_validation
from app.agents.recommendation_graph.state import RecommendationGraphState


def build_recommendation_graph(nodes: RecommendationGraphNodes, checkpointer):
    workflow = StateGraph(RecommendationGraphState)
    workflow.add_node("parse_intent", nodes.parse_intent)
    workflow.add_node("validate_request", nodes.validate_request)
    workflow.add_node("clarify_request", nodes.clarify_request)
    workflow.add_node("resolve_destination", nodes.resolve_destination)
    workflow.add_node("resolve_activity", nodes.resolve_activity)
    workflow.add_node("run_recommendation", nodes.run_recommendation)
    workflow.add_node("verify_results", nodes.verify_results)
    workflow.add_node("compose_response", nodes.compose_response)
    workflow.add_edge(START, "parse_intent")
    workflow.add_edge("parse_intent", "validate_request")
    workflow.add_conditional_edges("validate_request", after_validation)
    workflow.add_edge("clarify_request", "parse_intent")
    workflow.add_conditional_edges("resolve_destination", after_destination)
    workflow.add_edge("resolve_activity", "run_recommendation")
    workflow.add_conditional_edges("run_recommendation", after_recommendation)
    workflow.add_edge("verify_results", "compose_response")
    workflow.add_edge("compose_response", END)
    return workflow.compile(checkpointer=checkpointer)
