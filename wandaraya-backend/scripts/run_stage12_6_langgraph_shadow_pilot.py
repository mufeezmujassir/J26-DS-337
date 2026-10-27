from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.recommendation_graph.schemas.graph_request import AgenticRecommendationRequest
from app.agents.recommendation_graph.services.checkpoint_service import DevelopmentCheckpointService
from app.agents.recommendation_graph.services.graph_service import RecommendationGraphService
from app.database import AsyncSessionLocal


CASES = [
    ("stage12-6-kandy", "Recommend cultural and scenic attractions near Kandy on 2026-10-22 morning"),
    ("stage12-6-mirissa", "Recommend beach activities near Mirissa on 2026-10-22 at 3pm"),
    ("stage12-6-ella", "Recommend nature and waterfall attractions near Ella on 2026-10-22 at 8am"),
]


def _summarize(response, phase: str) -> dict:
    evidence = {name: {"AVAILABLE": 0, "PARTIALLY_AVAILABLE": 0, "OTHER": 0}
                for name in ("weather", "time_of_day", "holiday_event", "historical_seasonality")}
    for candidate in response.recommendations:
        for name, item in candidate.evidence.items():
            bucket = item.status.value if item.status.value in {"AVAILABLE", "PARTIALLY_AVAILABLE"} else "OTHER"
            evidence[name][bucket] += 1
    return {
        "phase": phase, "session_id": response.session_id, "status": response.graph_status,
        "latency_ms": response.latency_ms, "candidate_count": len(response.recommendations),
        "context_coverage": evidence, "group_emotion_status": response.group_emotion_status,
        "configuration": response.reranker_configuration.value, "errors": response.errors,
        "warnings": response.warnings, "nodes_executed": response.nodes_executed,
        "tool_calls": response.tool_calls,
        "production_order_preserved": response.production_candidate_order == response.original_candidate_order,
    }


async def main() -> None:
    service = RecommendationGraphService(DevelopmentCheckpointService(3600))
    results = []
    for index, (session_id, message) in enumerate(CASES):
        try:
            async with AsyncSessionLocal() as db:
                response = await service.execute(
                    db, AgenticRecommendationRequest(session_id=session_id, message=message,
                                                     candidate_limit=30, result_limit=5), "stage12-6-pilot"
                )
            results.append(_summarize(response, "cold" if index == 0 else "warm"))
        except Exception as exc:
            results.append({"phase": "cold" if index == 0 else "warm", "session_id": session_id,
                            "status": "FAILED", "candidate_count": 0,
                            "group_emotion_status": "DEFERRED_NOT_INTEGRATED",
                            "production_order_preserved": True,
                            "errors": [{"type": type(exc).__name__, "message": str(exc)}]})
    report = {
        "stage": "12.6", "generated_at": datetime.now(timezone.utc).isoformat(),
        "pilot_type": "real_postgresql_qdrant_shadow", "llm_calls": 0,
        "group_emotion_integrated": False, "recommendation_accuracy_validated": False,
        "production_ranking_changed": any(not row.get("production_order_preserved", False) for row in results),
        "queries": results,
    }
    target = Path("data/reports/stage12_6_langgraph_shadow_pilot.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
