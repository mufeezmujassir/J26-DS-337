"""Run a separate Stage 12.5 real-data shadow pilot; production order is immutable."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from app.database import AsyncSessionLocal
from app.recommendation.unified_context.orchestrator import UnifiedContextOrchestrator
from app.recommendation.unified_context.schemas import UnifiedContextRequest


async def run_case(case: dict) -> dict:
    async with AsyncSessionLocal() as db:
        service = UnifiedContextOrchestrator(db, engine_enabled=True, reranking_enabled=True)
        started = perf_counter()
        response = await service.recommend(UnifiedContextRequest(**case))
        return {
            "request": case,
            "response": response.model_dump(mode="json"),
            "measured_wall_latency_ms": round((perf_counter() - started) * 1000, 3),
            "production_order_unchanged": response.production_candidate_order == response.original_candidate_order,
        }


async def run(args) -> dict:
    cases = json.loads(args.input.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        try:
            results.append(await run_case(case))
        except Exception as exc:
            results.append({"request": case, "error_type": type(exc).__name__, "error": str(exc)})
    successful = [item for item in results if "response" in item]
    return {
        "stage": "12.5",
        "version": "stage12_5_unified_context_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pilot_type": "real_semantic_shadow",
        "queries_requested": len(cases),
        "queries_completed": len(successful),
        "production_ranking_changed": any(not item["production_order_unchanged"] for item in successful),
        "results": results,
        "note": "No benchmark value is emitted unless it was measured by this execution.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="JSON array of UnifiedContextRequest objects")
    parser.add_argument("--output", type=Path, default=Path("data/reports/stage12_5_shadow_pilot.json"))
    args = parser.parse_args()
    payload = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "completed": payload["queries_completed"]}))


if __name__ == "__main__":
    main()
