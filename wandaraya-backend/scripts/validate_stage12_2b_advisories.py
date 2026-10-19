"""Read-only Stage 12.2B advisory audit and integration evidence report."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.attraction_descriptions import AttractionDescription
from app.recommendation.time_context.advisory import load_strict_json, normalise_advisory_report


REPORT_ROOT = Path("data/reports")


async def source_urls_for(attraction_id: int) -> set[str]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AttractionDescription.source_url).where(
            AttractionDescription.attraction_id == attraction_id,
            AttractionDescription.is_active.is_(True),
        ))).scalars().all()
    return {url for url in rows if url}


async def main() -> None:
    audits = []
    for attraction_id in (1, 27):
        path = REPORT_ROOT / f"stage12_2_llm_best_time_advisory_{attraction_id}.json"
        try:
            raw = load_strict_json(path)
            normalised = normalise_advisory_report(raw, attraction_id)
            stored_urls = await source_urls_for(attraction_id)
            cited = set(normalised["cited_sources"])
            audits.append({
                "attraction_id": attraction_id, "report": str(path), "json_valid": True,
                "status": raw.get("status"), "normalised_advisory": normalised,
                "cited_sources_exist_in_active_description_records": cited.issubset(stored_urls),
                "stored_source_url_count": len(stored_urls),
                "claim_entailment_independently_verified": False,
                "claim_entailment_note": "The historic report retains URL provenance but not captured source text; wording is not promoted to factual operating evidence.",
            })
        except Exception as exc:
            audits.append({"attraction_id": attraction_id, "report": str(path), "json_valid": False, "error": str(exc)})

    now = datetime.now(timezone.utc).isoformat()
    policy = {
        "verified_operator_time_evidence": "Only stored verified operating-hours evidence may determine OPEN/CLOSED.",
        "source_supported_advisory": "Cited URL must belong to an active stored description. It remains explanatory; claim entailment is not silently treated as verified.",
        "llm_generated_advisory": "No source citation; explicitly model-generated, low evidence confidence.",
        "advisory_unavailable": "Null text; does not penalize or exclude a candidate.",
        "ranking": "Best-time advisory is not included in baseline_score or final_experimental_score.",
        "groq": "The public API never invokes Groq; only an explicit CLI --execute can do so.",
    }
    integration = {
        "endpoint": "POST /api/v1/recommendations/time-aware",
        "request_flag": "include_best_time_advisory=true",
        "storage": "Existing JSON reports only; no migration or database writes.",
        "opening_hours_independence": True,
        "ranking_independence": True,
        "automatic_groq_calls": False,
        "deployment_note": "The source implementation is ready; an already-running non-reload FastAPI process requires a separately authorized API restart before the new response field is served.",
    }
    evaluation = {
        "comparison": ["content_baseline", "time_aware_without_advisory", "time_aware_with_advisory"],
        "ranking_expected_stable_when_only_advisory_changes": True,
        "real_world_accuracy_claimed": False,
        "known_limitations": ["No labeled human usefulness study was supplied.", "Historic advisory reports do not retain full source excerpts for independent entailment checks."],
    }
    documents = {
        "stage12_2b_advisory_audit.json": {"generated_at_utc": now, "audits": audits},
        "stage12_2b_evidence_policy.json": policy,
        "stage12_2b_integration_results.json": integration,
        "stage12_2b_research_evaluation.json": evaluation,
        "stage12_2b_final_summary.json": {"status": "ADVISORY_POLICY_IMPLEMENTED", "advisory_reports_audited": len(audits), "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0, "production_api_restarted": False},
    }
    for filename, value in documents.items():
        (REPORT_ROOT / filename).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(documents["stage12_2b_final_summary.json"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
