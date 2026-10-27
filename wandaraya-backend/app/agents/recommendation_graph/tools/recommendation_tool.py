from __future__ import annotations

from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.recommendation.unified_context.orchestrator import UnifiedContextOrchestrator
from app.recommendation.unified_context.schemas import UnifiedContextRequest


def build_recommendation_tool(db: AsyncSession) -> StructuredTool:
    orchestrator = UnifiedContextOrchestrator(db, engine_enabled=True, reranking_enabled=True)

    async def _run(**kwargs):
        request = UnifiedContextRequest(**kwargs)
        response = await orchestrator.recommend(request)
        return response.model_dump(mode="json")

    return StructuredTool.from_function(
        coroutine=_run,
        name="run_unified_context_recommendation",
        description=(
            "Run the existing deterministic Stage 12.5 semantic retrieval and four-layer "
            "experimental context reranker. This tool cannot modify production ordering."
        ),
        args_schema=UnifiedContextRequest,
    )
