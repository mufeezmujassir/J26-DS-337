"""Create reproducible blind annotation packages for Stage 12.3D.4."""
from __future__ import annotations
import asyncio, csv, json, time
from datetime import datetime, timezone
from pathlib import Path

from app.database import AsyncSessionLocal
from app.holiday_event.context_scoring import ContextScoreRequest, HolidayEventContextScoringService
from app.recommendation.content_based.schemas import ContentBasedRecommendationRequest
from app.recommendation.content_based.service import ContentBasedRecommendationService
from app.recommendation.evaluation.holiday_event_stage12_3d4 import QUERY_SPECS, deterministic_split, latency_summary, presentation_key

ROOT = Path("data/reports")
POOL = 20

async def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    universe, latencies = [], []
    split = deterministic_split(QUERY_SPECS)
    async with AsyncSessionLocal() as db:
        service = ContentBasedRecommendationService(db)
        context = HolidayEventContextScoringService(db)
        for spec in QUERY_SPECS:
            started = time.perf_counter()
            request = ContentBasedRecommendationRequest(interests=" ".join(spec["interests"]), preferred_district_ids=spec["district_ids"], limit=POOL, candidate_pool_size=POOL)
            response = await service.recommend(request)
            candidates = response.recommendations
            context_response = await context.score(ContextScoreRequest(travel_date=spec["travel_date"], attraction_ids=[item.attraction_id for item in candidates], interests=spec["interests"])) if candidates else None
            context_by_id = {item.attraction_id: item for item in (context_response.scores if context_response else [])}
            latencies.append((time.perf_counter() - started) * 1000)
            for rank, item in enumerate(candidates, start=1):
                ctx = context_by_id.get(item.attraction_id)
                universe.append({"query_id": spec["query_id"], "travel_date": spec["travel_date"], "interests": spec["interests"], "scenario_provenance": "manually_authored_research_scenario_not_real_user_query", "context_expectation": spec["context_expectation"], "split": split[spec["query_id"]], "attraction_id": item.attraction_id, "attraction_name": item.attraction_name, "district_id": item.district_id, "categories": item.matched_preference_evidence.get("category_names", []), "activities": item.matched_preference_evidence.get("activity_names", []), "factual_description": item.ranking_explanation, "baseline_rank": rank, "baseline_score": item.baseline_score, "context_score": None if ctx is None else ctx.context_suitability_score, "context_components": {} if ctx is None else {"holiday": ctx.holiday_score, "poya": ctx.poya_score, "verified_event": ctx.event_score, "interests": ctx.interest_compatibility_score}, "context_confidence": None if ctx is None else ctx.context_confidence, "context_evidence_coverage": None if ctx is None else ctx.evidence_coverage, "context_eligible_features": [] if ctx is None else ctx.eligible_features, "presentation_key": presentation_key(spec["query_id"], item.attraction_id)})
    dataset = {"version": "stage12_3d4_v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "scenario_count": len(QUERY_SPECS), "scenarios": QUERY_SPECS, "split": split, "data_provenance": "manually authored research scenarios; not independently collected tourist behaviour", "postgresql_writes": False, "qdrant_writes": False, "production_ranking_changed": False}
    (ROOT / "stage12_3d4_query_dataset.json").write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    (ROOT / "stage12_3d4_candidate_universe_private.json").write_text(json.dumps({"records": universe, "candidate_pool_size": POOL}, indent=2) + "\n", encoding="utf-8")
    # Private mapping is intentionally separate from templates to avoid rank leakage.
    mapping = [{"query_id": row["query_id"], "presentation_key": row["presentation_key"], "attraction_id": row["attraction_id"]} for row in universe]
    (ROOT / "stage12_3d4_private_presentation_mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    fields = ["annotation_batch_id", "reviewer_id", "query_id", "travel_date", "interests", "attraction_id", "attraction_name", "district_id", "categories", "activities", "factual_description", "cannot_judge", "relevance_0_to_3", "reviewer_explanation"]
    for reviewer in ("R1", "R2"):
        with (ROOT / f"stage12_3d4_{reviewer.lower()}_blind_template.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
            for row in sorted(universe, key=lambda item: (item["query_id"], item["presentation_key"])):
                writer.writerow({"annotation_batch_id": "stage12_3d4_v1", "reviewer_id": reviewer, "query_id": row["query_id"], "travel_date": row["travel_date"], "interests": " | ".join(row["interests"]), "attraction_id": row["attraction_id"], "attraction_name": row["attraction_name"], "district_id": row["district_id"], "categories": " | ".join(row["categories"]), "activities": " | ".join(row["activities"]), "factual_description": row["factual_description"], "cannot_judge": "", "relevance_0_to_3": "", "reviewer_explanation": ""})
    manifest = {"status": "AWAITING_INDEPENDENT_HUMAN_LABELS", "annotation_scale": {"0": "irrelevant", "1": "weakly relevant", "2": "relevant", "3": "highly relevant"}, "candidate_rows_per_reviewer": len(universe), "reviewers_required": 2, "fixed_seed": 12345, "blind_templates": ["stage12_3d4_r1_blind_template.csv", "stage12_3d4_r2_blind_template.csv"], "private_mapping": "stage12_3d4_private_presentation_mapping.json", "human_labels_available": False, "postgresql_writes": False, "qdrant_writes": False, "production_ranking_changed": False}
    (ROOT / "stage12_3d4_annotation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ROOT / "stage12_3d4_latency.json").write_text(json.dumps({"status": "CANDIDATE_GENERATION_LATENCY_RECORDED", "method": "end-to-end read-only baseline retrieval plus context preview per manually authored scenario", "latency": latency_summary(latencies), "sample_size": len(latencies), "postgresql_writes": False, "qdrant_writes": False, "production_ranking_changed": False}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**manifest, "candidate_generation_latency_samples_ms": len(latencies)}, indent=2))

if __name__ == "__main__": asyncio.run(main())
