"""Bounded, evidence-aware event-attraction candidate matching."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.holiday_event.event_attraction_matcher import EventAttractionMatcher
from app.models.holiday_event import EventAttractionLink, TourismEvent


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> dict:
    if args.execute and not args.confirm_execute:
        raise SystemExit("--execute requires --confirm-execute")
    if args.enable_llm and not args.confirm_llm:
        raise SystemExit("--enable-llm requires --confirm-llm")
    if args.event_id is None and not args.all_events:
        raise SystemExit("select --event-id or --all-events")
    output = Path(args.output)
    async with AsyncSessionLocal() as db:
        statement = select(TourismEvent).order_by(TourismEvent.id)
        if args.event_id is not None:
            statement = statement.where(TourismEvent.id == args.event_id)
        events = (await db.execute(statement.limit(args.max_events))).scalars().all()
        matcher = EventAttractionMatcher(db)
        results = []
        inserted = updated = 0
        for event in events:
            result = await matcher.match_event(event, max_candidates=args.max_candidates, enable_llm=args.enable_llm)
            if args.execute and not result.errors:
                created, changed = await matcher.persist_candidates(result)
                inserted += created
                updated += changed
            results.append(result.model_dump())
        if args.execute:
            await db.commit()
        links = (await db.execute(select(EventAttractionLink))).scalars().all()
        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "execute" if args.execute else "dry_run",
            "events_examined": len(events),
            "candidate_retrieval_count": sum(len(item["candidates"]) for item in results),
            "verified_link_count": sum(link.verification_status == "verified" for link in links),
            "candidate_link_count": sum(link.verification_status == "candidate" for link in links),
            "unresolved_event_count": sum(item["location"]["verification_status"] == "UNRESOLVED" for item in results),
            "llm_requests": sum(item["llm_requests"] for item in results),
            "candidate_links_inserted": inserted,
            "candidate_links_updated": updated,
            "postgresql_writes_executed": bool(args.execute and (inserted or updated)),
            "qdrant_writes_executed": False,
            "results": results,
        }
    _write(output, summary)
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--event-id", type=int)
    selection.add_argument("--all-events", action="store_true")
    parser.add_argument("--max-events", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--enable-llm", action="store_true")
    parser.add_argument("--confirm-llm", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Default; never persists candidate links.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--output", default="data/reports/stage12_3d2_matching_run.json")
    args = parser.parse_args()
    if args.max_events < 1 or args.max_candidates < 1 or args.max_candidates > 50:
        raise SystemExit("--max-events must be positive and --max-candidates must be 1..50")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
