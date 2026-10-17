"""Run Gate 5D Google Places identity verification in offline or explicit live mode."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.time_context.governance.catalogue_reconciliation import load_existing_attractions
from app.time_context.governance.google_places_reconciliation import Gate5DSettings, process_queue, write_gate5d_reports


async def run(args: argparse.Namespace) -> dict:
    if args.live and not (args.execute and args.confirm_execute):
        raise PermissionError("live Google Places execution requires --live --execute --confirm-execute")
    if args.live and args.max_records > 25:
        raise ValueError("live execution is limited to 25 records per batch; use bounded batches")
    queue_path = Path(args.queue)
    if not queue_path.is_file():
        raise FileNotFoundError(f"Google Places queue not found: {queue_path}")
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("queue JSON must contain a records list")
    selected = records[args.offset: args.offset + args.max_records]
    settings = Gate5DSettings(max_records=args.max_records, max_candidates=args.max_candidates,
                              request_interval_seconds=args.request_interval_seconds, max_retries=args.max_retries,
                              include_details=args.include_details)
    existing = await load_existing_attractions()
    client = None
    if args.live:
        # Imported only for an explicitly authorized live call, so offline validation
        # works without requiring an API key and cannot accidentally construct a client.
        from app.knowledge_base.connectors.google_places import GooglePlacesConnector
        client = GooglePlacesConnector()
    results, usage = await process_queue(queue=selected, existing=existing, settings=settings, client=client, live=args.live)
    reports = write_gate5d_reports(results=results, usage=usage, queue_path=queue_path, reports_dir=Path(args.reports_dir), batch_id=args.batch_id)
    return {"mode": usage["mode"], "queue_records": len(records), "offset": args.offset, "processed_records": len(results),
            "network_requests": usage["network_requests"], "postgresql_writes": False, "qdrant_writes": False,
            "reports": {key: str(value) for key, value in reports.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_google_places_enrichment_queue.json")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--batch-id", default="pilot_01")
    parser.add_argument("--max-records", type=int, default=5)
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--request-interval-seconds", type=float, default=1.0)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--include-details", action="store_true")
    parser.add_argument("--live", action="store_true", help="requires --execute --confirm-execute; never default")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args()
    if args.offset < 0: parser.error("--offset must be non-negative")
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
