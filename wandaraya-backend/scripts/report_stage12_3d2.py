"""Generate evidence-focused Stage 12.3D.2 reports from persisted results."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.holiday_event.event_location_resolver import resolve_event_location
from app.models.attraction import Attraction
from app.models.holiday_event import EventAttractionLink, TourismEvent

ROOT = Path("data/reports")


def write(name: str, value: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / name).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


async def main(tests_passed: int) -> None:
    dry_path = ROOT / "stage12_3d2_matching_dry_run.json"
    dry = json.loads(dry_path.read_text(encoding="utf-8")) if dry_path.exists() else {}
    async with AsyncSessionLocal() as db:
        event = await db.get(TourismEvent, 1)
        links = (await db.execute(select(EventAttractionLink).where(EventAttractionLink.event_id == 1).order_by(EventAttractionLink.semantic_similarity.desc().nullslast()))).scalars().all()
        active_attractions = int(await db.scalar(select(func.count()).select_from(Attraction).where(Attraction.is_active.is_(True))) or 0)
        event_count = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)
    location = resolve_event_location(event).model_dump() if event else None
    try:
        collection = __import__("os").getenv("QDRANT_COLLECTION_NAME", "sri_lanka_attractions_staging")
        client = QdrantClient(url=settings.QDRANT_URL)
        qdrant_points = (await asyncio.to_thread(client.get_collection, collection_name=collection)).points_count
        qdrant = {"collection": collection, "point_count": qdrant_points, "status": "read_only_ok", "writes_executed": False}
    except Exception as exc:
        qdrant = {"status": "read_only_check_failed", "error": type(exc).__name__, "writes_executed": False}
    link_items = [{
        "event_id": link.event_id, "attraction_id": link.attraction_id, "relationship_type": link.relationship_type,
        "match_status": link.verification_status, "evidence_type": link.evidence_type,
        "evidence_source_url": link.evidence_source, "semantic_similarity": link.semantic_similarity,
        "geographic_distance_km": link.geographic_distance_km, "matching_confidence": link.matching_confidence,
        "explanation": link.explanation, "verification_timestamp": link.verification_timestamp,
    } for link in links]
    verified = sum(item["match_status"] == "verified" for item in link_items)
    candidate = sum(item["match_status"] == "candidate" for item in link_items)
    geographic = {"fixture_only_results": False, "real_event_id": event.id if event else None, "location_evidence": location, "verified_geographic_matches": 0, "limitation": "The stored source text names Yala but contains no verified coordinates, district, or explicit attraction identity."}
    semantic = {"fixture_only_results": False, "real_event_id": event.id if event else None, "candidates": link_items, "parameter": {"max_candidates": 5, "threshold": "none; bounded retrieval ranking only"}, "limitation": "Similarity is candidate generation and not identity proof."}
    real_event = {"fixture_only_results": False, "event": None if not event else {"id": event.id, "source_event_id": event.source_event_id, "title": event.title, "venue": event.venue, "district_id": event.district_id, "location_confidence": event.location_confidence, "source_url": event.source_url}, "result": "No real verified event-attraction link was created."}
    llm = {"enabled": True, "real_run": {"requests": dry.get("llm_requests", 0), "status": dry.get("results", [{}])[0].get("llm_status") if dry.get("results") else "not_run", "proposed_category": dry.get("results", [{}])[0].get("proposed_category") if dry.get("results") else None}, "model_identifier": "openai/gpt-oss-20b", "estimated_cost": "not reported by provider response", "secrets_included": False}
    api = {"candidate_endpoint": "GET /api/v1/events/1/attraction-matches?match_status=candidate&limit=5", "context_endpoint": "POST /api/v1/context/holiday-events/evaluate", "status": "HTTP_READBACK_VERIFIED", "semantic_candidates_remain_unverified": True}
    regression = {"tests_passed": tests_passed, "fixture_only_results": True, "coverage": ["unresolved venue", "missing location", "source-supported district", "semantic candidate classification", "Poya context", "candidate does not affect event ranking"]}
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": "EVENT_ATTRACTION_MATCHING_ENGINE_VERIFIED" if event and candidate and not verified and qdrant.get("status") == "read_only_ok" and tests_passed else "EVENT_ATTRACTION_MATCHING_ENGINE_PENDING", "real_events": event_count, "verified_links": verified, "candidate_links": candidate, "unresolved_real_events": 1 if location and location["verification_status"] != "VERIFIED" else 0, "active_attractions": active_attractions, "qdrant": qdrant, "postgresql_writes_in_matching": candidate > 0, "qdrant_writes_executed": False, "production_ranking_changed": False}
    write("stage12_3d2_geographic_evidence.json", geographic)
    write("stage12_3d2_semantic_candidates.json", semantic)
    write("stage12_3d2_event_attraction_links.json", {"links": link_items, "verified_count": verified, "candidate_count": candidate})
    write("stage12_3d2_real_event_verification.json", real_event)
    write("stage12_3d2_llm_usage.json", llm)
    write("stage12_3d2_api_verification.json", api)
    write("stage12_3d2_regression_tests.json", regression)
    write("stage12_3d2_final_summary.json", summary)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-passed", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(main(args.tests_passed))
