"""Controlled Stage 12.3C ingestion CLI. Network and persistence need --execute."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.database import AsyncSessionLocal
from app.holiday_event.ingestion import HolidayEventIngestionService
from app.holiday_event.repository import HolidayEventRepository
from app.holiday_event.source_access import load_terms_reviews


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("calendar_sri_lanka", "lanka_events"))
    parser.add_argument("--terms-policy", help="Local JSON file containing documented terms-review evidence")
    parser.add_argument("--event-horizon-months", type=int, default=3)
    parser.add_argument("--max-event-details", type=int, default=50)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--enable-llm", action="store_true", help="Opt in to Groq fallback only for incomplete permitted event-detail pages.")
    parser.add_argument("--confirm-llm", action="store_true", help="Required together with --enable-llm before any Groq request.")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    if args.execute and not args.confirm_execute:
        raise SystemExit("--execute requires --confirm-execute")
    if args.enable_llm and not args.confirm_llm:
        raise SystemExit("--enable-llm requires --confirm-llm")
    if args.enable_llm and not args.execute:
        raise SystemExit("--enable-llm requires --execute")
    reviews = load_terms_reviews(args.terms_policy)
    async with AsyncSessionLocal() as session:
        return await HolidayEventIngestionService(HolidayEventRepository(session)).run(
            args.source, dag_id=f"manual_{args.source}_ingestion", terms_review=reviews.get(args.source),
            execute=args.execute, event_horizon_months=args.event_horizon_months, max_event_details=args.max_event_details,
            enable_llm=args.enable_llm,
        )


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    result_text = json.dumps(result, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result_text + "\n", encoding="utf-8")
    print(result_text)


if __name__ == "__main__":
    main()
