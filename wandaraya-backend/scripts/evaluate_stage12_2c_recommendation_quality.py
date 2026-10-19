"""Read-only Stage 12.2C candidate-recall and advisory-coverage experiment."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.database import AsyncSessionLocal
from app.recommendation.content_based.diagnostics import eligibility_review_flags, requested_metadata_coverage
from app.recommendation.content_based.schemas import ContentBasedHardFilters, ContentBasedRecommendationRequest
from app.recommendation.content_based.service import ContentBasedRecommendationService
from app.recommendation.time_context.advisory import load_advisory_for_attraction


REPORT_ROOT = Path("data/reports")
TARGET_ID = 1
QUERY = "heritage attractions and walking in Galle"


def request(pool: int, strict: bool = False) -> ContentBasedRecommendationRequest:
    return ContentBasedRecommendationRequest(
        interests=QUERY, preferred_district_ids=[78], preferred_categories=["Heritage"],
        # The public baseline deliberately caps this setting at 100.  The
        # 200-candidate case below calls the retriever directly as a bounded
        # diagnostics experiment, without expanding the API contract.
        preferred_activities=["Walking"], limit=5, candidate_pool_size=min(pool, 100),
        hard_filters=ContentBasedHardFilters(district_ids=[78], category_names=["Heritage"]) if strict else ContentBasedHardFilters(),
    )


async def main() -> None:
    experiments = []
    async with AsyncSessionLocal() as db:
        service = ContentBasedRecommendationService(db)
        for pool in (30, 50, 100, 200):
            started = time.perf_counter()
            payload = request(pool)
            retrieval_query = service.build_retrieval_query(payload)
            candidates = service._deduplicate_candidates(await service.retriever.search(db, retrieval_query, pool))
            hydrated = await service._hydrate([item.attraction_id for item in candidates])
            # Full bounded ranking is diagnostic-only; the production service
            # still returns only its configured final limit.
            all_scored = [service._score_candidate(payload, candidate, hydrated[candidate.attraction_id]) for candidate in candidates if candidate.attraction_id in hydrated]
            all_scored.sort(key=lambda item: (-item.baseline_score, item.attraction_id))
            ranked = service.rank_hydrated(payload, retrieval_query, candidates, hydrated)
            target_rank = next((index + 1 for index, item in enumerate(candidates) if item.attraction_id == TARGET_ID), None)
            final_rank = next((index + 1 for index, item in enumerate(all_scored) if item.attraction_id == TARGET_ID), None)
            target_item = next((item for item in all_scored if item.attraction_id == TARGET_ID), None)
            strict_payload = request(pool, strict=True)
            strict_survivors = sum(service._hard_filter_failure(strict_payload, record) is None for record in hydrated.values())
            experiments.append({
                "candidate_pool": pool, "retrieved_candidate_count": len(candidates),
                "target_id": TARGET_ID, "target_in_initial_pool": target_rank is not None,
                "target_semantic_rank": target_rank, "target_in_final_top5": final_rank is not None and final_rank <= 5,
                "target_final_rank_in_bounded_pool": final_rank,
                "target_scoring_components": None if target_item is None else {"baseline_score": target_item.baseline_score, "semantic_relevance_score": target_item.semantic_relevance_score, "category_match_score": target_item.category_match_score, "activity_match_score": target_item.activity_match_score, "district_match_score": target_item.district_match_score, "unavailable_dimensions": target_item.matched_preference_evidence.get("unavailable_dimensions")},
                "hard_filter_survival_count_if_district_and_category_are_strict": strict_survivors,
                "final_top5": [{"id": item.attraction_id, "name": item.attraction_name, "score": item.baseline_score} for item in ranked.recommendations],
                "candidate_missing_category_or_activity_count": sum(not r.category_names or not r.activity_names for r in hydrated.values()),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            })

        # Audit only records actually observed in the bounded largest experiment.
        largest = experiments[-1]
        payload = request(200)
        candidates = service._deduplicate_candidates(await service.retriever.search(db, service.build_retrieval_query(payload), 200))
        hydrated = await service._hydrate([item.attraction_id for item in candidates])
        quality = []
        for candidate in candidates:
            record = hydrated.get(candidate.attraction_id)
            if record is None:
                continue
            flags = eligibility_review_flags(record)
            if flags:
                quality.append({"attraction_id": candidate.attraction_id, "name": candidate.name, "semantic_score": candidate.score, "flags": flags, "categories": list(record.category_names), "activities": list(record.activity_names)})
        target = hydrated.get(TARGET_ID)
        advisory = load_advisory_for_attraction(TARGET_ID)

    now = datetime.now(timezone.utc).isoformat()
    diagnostics = {
        "generated_at_utc": now, "query": QUERY, "target": {"attraction_id": TARGET_ID, "known_plausible_fixture_label": True},
        "experiments": experiments,
        "target_metadata": None if target is None else {"name": target.attraction.name, "district_id": target.attraction.district_id, "categories": list(target.category_names), "activities": list(target.activity_names)},
        "interpretation_boundary": "Fixture relevance is not an independently collected human judgement. No retrieval/ranking production policy was changed.",
    }
    recall = {"generated_at_utc": now, "pools": experiments, "conclusion": "Pool-size results are descriptive only; no unbounded Qdrant scan was performed."}
    quality_report = {"generated_at_utc": now, "scope": "bounded 200-candidate diagnostic pool", "suspicious_records_requiring_human_review": quality, "proposed_policy": {"automatic_exclusion": False, "review_flags": ["name_requires_tourism_eligibility_review", "missing_category_metadata", "missing_activity_metadata", "missing_district_metadata"]}}
    ranking = {"baseline": "content_baseline_v1", "experimental_policy_proposed_only": "content_preference_diagnostics_v1", "proposal": "Evaluate metadata-completeness transparency and an eligibility-review gate on human labels; do not penalize missing metadata as a negative match and do not alter baseline until evaluated.", "ranking_switched": False}
    advisory_report = {"generated_at_utc": now, "target_advisory": advisory, "report_discoverable": advisory["evidence_tier"] != "advisory_unavailable", "ranking_changed_by_advisory": False, "groq_requests": 0}
    summary = {"status": "QUALITY_DIAGNOSTICS_COMPLETED", "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0, "production_ranking_policy_changed": False, "target_in_largest_pool": largest["target_in_initial_pool"], "target_in_largest_final_top5": largest["target_in_final_top5"]}
    reports = {
        "stage12_2c_candidate_diagnostics.json": diagnostics,
        "stage12_2c_candidate_recall_experiments.json": recall,
        "stage12_2c_attraction_quality_audit.json": quality_report,
        "stage12_2c_ranking_comparison.json": ranking,
        "stage12_2c_advisory_coverage.json": advisory_report,
        "stage12_2c_final_summary.json": summary,
    }
    for filename, body in reports.items():
        (REPORT_ROOT / filename).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
