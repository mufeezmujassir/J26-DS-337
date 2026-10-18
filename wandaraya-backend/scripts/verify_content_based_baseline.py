"""Run bounded Stage 12.1 verification and write the required reports.

The command performs no database or Qdrant writes.  It has two parts: pure
deterministic ranking checks and, when an API URL is supplied, one read-only
end-to-end POST request through FastAPI, embeddings, Qdrant, and PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.knowledge_base.retrieval.semantic_retriever import SemanticCandidate
from app.recommendation.content_based.schemas import ContentBasedRecommendationRequest
from app.recommendation.content_based.service import ContentBasedRecommendationService, HydratedAttraction


REPORTS = Path("data/reports")


@dataclass
class _Attraction:
    id: int
    name: str
    district_id: int | None
    price_level: int | None


def _record(identifier: int, categories=("Heritage",), activities=("Walking",), district=78, price=2, region=None):
    return HydratedAttraction(
        _Attraction(identifier, f"Fixture {identifier}", district, price), categories, activities, region
    )


def _candidate(identifier: int, score: float = 0.8):
    return SemanticCandidate(identifier, f"Fixture {identifier}", score, "Galle", 78)


def _manual_checks() -> list[dict[str, object]]:
    service = ContentBasedRecommendationService(None)
    checks: list[dict[str, object]] = []

    def check(name: str, assertion) -> None:
        assertion()
        checks.append({"name": name, "status": "passed"})

    request = ContentBasedRecommendationRequest(
        interests="heritage walking",
        preferred_categories=["heritage"],
        preferred_activities=["walking"],
        preferred_district_ids=[78],
    )
    response = service.rank_hydrated(
        request, "heritage walking", [_candidate(2), _candidate(1)], {1: _record(1), 2: _record(2)}
    )
    check("stable_attraction_id_tie_break", lambda: (_ for _ in ()).throw(AssertionError()) if [x.attraction_id for x in response.recommendations] != [1, 2] else None)
    check("category_activity_district_matching", lambda: (_ for _ in ()).throw(AssertionError()) if response.recommendations[0].baseline_score != 0.94 else None)
    missing = service.rank_hydrated(
        ContentBasedRecommendationRequest(interests="heritage", preferred_categories=["heritage"]),
        "heritage", [_candidate(1)], {1: _record(1, categories=())},
    )
    check("missing_soft_metadata_is_unknown", lambda: (_ for _ in ()).throw(AssertionError()) if missing.recommendations[0].category_match_score is not None else None)
    hard = service.rank_hydrated(
        ContentBasedRecommendationRequest(interests="heritage", hard_filters={"max_price_level": 2}),
        "heritage", [_candidate(1)], {1: _record(1, price=None)},
    )
    check("hard_budget_missing_metadata_excluded", lambda: (_ for _ in ()).throw(AssertionError()) if hard.recommendations or hard.excluded_candidate_counts.get("hard_budget_metadata_missing") != 1 else None)
    deduped = service._deduplicate_candidates([_candidate(1, 0.6), _candidate(1, 0.9)])
    check("duplicate_candidate_retains_best_semantic_score", lambda: (_ for _ in ()).throw(AssertionError()) if len(deduped) != 1 or deduped[0].score != 0.9 else None)
    inactive = service.rank_hydrated(
        ContentBasedRecommendationRequest(interests="heritage"), "heritage", [_candidate(1)], {}
    )
    check("missing_hydrated_candidate_excluded", lambda: (_ for _ in ()).throw(AssertionError()) if inactive.excluded_candidate_counts.get("inactive_or_unavailable_postgresql_record") != 1 else None)
    try:
        ContentBasedRecommendationRequest(interests="heritage", limit=4, candidate_pool_size=3)
    except ValueError:
        checks.append({"name": "invalid_candidate_limit_rejected", "status": "passed"})
    else:
        raise AssertionError("invalid candidate pool size was accepted")
    check("baseline_scope_excludes_context_layers", lambda: (_ for _ in ()).throw(AssertionError()) if "weather" not in response.baseline_scope else None)
    region = service.rank_hydrated(
        ContentBasedRecommendationRequest(interests="heritage", preferred_regions=["Southern Province"]),
        "heritage", [_candidate(1)], {1: _record(1, region="Southern Province")},
    )
    check("verified_region_preference_matching", lambda: (_ for _ in ()).throw(AssertionError()) if region.recommendations[0].region_match_score != 1 else None)
    return checks


def _live_smoke(api_url: str) -> dict[str, object]:
    payload = {
        "interests": "heritage attractions and walking in Galle",
        "preferred_district_ids": [78],
        "limit": 3,
        "candidate_pool_size": 15,
    }
    start = time.perf_counter()
    request = Request(
        f"{api_url.rstrip('/')}/api/v1/recommendations/content-based",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=240) as response:
            body = json.loads(response.read().decode("utf-8"))
            status = response.status
    except (URLError, TimeoutError, ValueError) as exc:
        return {"status": "failed", "error": str(exc), "postgresql_writes_executed": False, "qdrant_writes_executed": False}
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    result_ids = [item["attraction_id"] for item in body.get("recommendations", [])]
    return {
        "status": "passed" if status == 200 and result_ids else "failed",
        "http_status": status,
        "latency_ms": elapsed_ms,
        "request": payload,
        "candidate_count": body.get("candidates_retrieved"),
        "result_attraction_ids": result_ids,
        "score_configuration_version": body.get("score_configuration_version"),
        "baseline_scope": body.get("baseline_scope"),
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=None, help="Optional already-running FastAPI URL for one read-only smoke test.")
    args = parser.parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks = _manual_checks()
    smoke = _live_smoke(args.api_url) if args.api_url else {"status": "not_run"}
    implementation = {
        "stage": "12.1",
        "status": "CONTENT_BASELINE_TESTED" if smoke.get("status") != "passed" else "CONTENT_BASELINE_VERIFIED_END_TO_END",
        "endpoint": "POST /api/v1/recommendations/content-based",
        "retrieval": "existing SemanticAttractionRetriever and existing configured Qdrant collection",
        "metadata": "read-only PostgreSQL hydration of active attractions, categories, and available activities",
        "hard_filter_policy": "exclude candidates when requested hard-filter metadata is absent or does not match",
        "region_policy": "province preferences are resolved only through stored districts.province values",
        "score": "shifted cosine similarity plus available metadata preference scores with dynamic weight normalization",
        "excluded_dimensions": ["weather", "holiday", "seasonality", "time_of_day", "group_emotion", "itinerary_optimization"],
        "database_writes": False,
        "qdrant_writes": False,
    }
    tests = {"runner": "bounded_stdlib_verifier", "passed": len(checks), "failed": 0, "skipped": 0, "checks": checks, "pytest_note": "pytest is not installed in the active backend container; pytest test files are included but were not executed."}
    final = {
        "status": implementation["status"],
        "manual_checks_passed": len(checks),
        "api_smoke_status": smoke.get("status"),
        "reports": [
            "stage12_1_content_based_implementation.json",
            "stage12_1_ranking_evaluation.json",
            "stage12_1_api_smoke_test.json",
            "stage12_1_test_results.json",
            "stage12_1_final_summary.json",
        ],
        "limitations": [
            "Offline ranking metrics use a controlled fixture and are not real-world quality claims.",
            "This baseline is not the final five-layer Context Re-Ranker.",
        ],
        "postgresql_writes_executed": False,
        "qdrant_writes_executed": False,
    }
    for name, content in {
        "stage12_1_content_based_implementation.json": implementation,
        "stage12_1_api_smoke_test.json": smoke,
        "stage12_1_test_results.json": tests,
        "stage12_1_final_summary.json": final,
    }.items():
        (REPORTS / name).write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
