from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.recommendation_graph.builder import build_recommendation_graph
from app.agents.recommendation_graph.nodes import RecommendationGraphNodes
from app.agents.recommendation_graph.schemas.graph_request import AgenticRecommendationRequest
from app.agents.recommendation_graph.schemas.graph_response import AgenticRecommendationResponse
from app.agents.recommendation_graph.services.checkpoint_service import DevelopmentCheckpointService
from app.agents.recommendation_graph.services.llm_service import IntentExtractionService
from app.agents.recommendation_graph.tools import (
    build_activity_tool, build_destination_tool, build_recommendation_tool,
)
from app.config import settings


def _optional_structured_llm():
    if not settings.ENABLE_LANGCHAIN_INTENT_EXTRACTION or not settings.GROQ_API_KEY:
        return None
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=settings.LANGCHAIN_INTENT_MODEL, api_key=settings.GROQ_API_KEY,
                      base_url="https://api.groq.com/openai/v1", temperature=0, timeout=15, max_retries=1)


class RecommendationGraphService:
    def __init__(self, checkpoints: DevelopmentCheckpointService):
        self.checkpoints = checkpoints

    async def execute(self, db: AsyncSession, request: AgenticRecommendationRequest,
                      owner: str) -> AgenticRecommendationResponse:
        started = time.perf_counter()
        record = await self.checkpoints.claim(request.session_id, owner)
        nodes = RecommendationGraphNodes(
            intent_service=IntentExtractionService(
                _optional_structured_llm(), enabled=settings.ENABLE_LANGCHAIN_INTENT_EXTRACTION
            ),
            destination_tool=build_destination_tool(db), activity_tool=build_activity_tool(db),
            recommendation_tool=build_recommendation_tool(db),
            max_clarification_turns=settings.LANGGRAPH_MAX_CLARIFICATION_TURNS,
        )
        graph = build_recommendation_graph(nodes, self.checkpoints.checkpointer)
        config = {"configurable": {"thread_id": record.checkpoint_thread_id}}
        initial_state = {
            "session_id": request.session_id, "request_id": str(uuid.uuid4()),
            "owner_hash": record.owner_hash, "user_message": request.message,
            "trusted_current_datetime": datetime.now(ZoneInfo("Asia/Colombo")).isoformat(),
            "reranker_configuration": request.reranker_configuration.value,
            "candidate_limit": request.candidate_limit, "result_limit": request.result_limit,
            "clarification_turns": 0, "errors": [], "warnings": [], "nodes_executed": [],
            "tool_calls": [], "graph_status": "RUNNING", "final_response": {},
            "recommendation_response": {}, "verification": {},
        }
        graph_input = Command(resume=request.message) if record.awaiting_clarification else initial_state
        async with asyncio.timeout(settings.LANGGRAPH_EXECUTION_TIMEOUT_SECONDS):
            state = await graph.ainvoke(graph_input, config=config)
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        interrupts = state.get("__interrupt__", [])
        if interrupts or (state.get("clarification_required") and not state.get("final_response")):
            await self.checkpoints.set_awaiting(request.session_id, True)
            value = interrupts[0].value if interrupts else {
                "question": state.get("clarification_question"), "missing_fields": state.get("missing_fields", [])
            }
            response = AgenticRecommendationResponse(
                session_id=request.session_id, request_id=state["request_id"],
                graph_status="CLARIFICATION_REQUIRED", parsed_intent=state.get("intent"),
                clarification_required=True, clarification_question=value.get("question"),
                reranker_configuration=request.reranker_configuration, errors=state.get("errors", []),
                warnings=state.get("warnings", []), nodes_executed=state.get("nodes_executed", []),
                tool_calls=state.get("tool_calls", []), latency_ms=elapsed,
            )
            return response
        await self.checkpoints.set_awaiting(request.session_id, False)
        result = dict(state.get("final_response") or {})
        result["latency_ms"] = elapsed
        return AgenticRecommendationResponse.model_validate(result)
