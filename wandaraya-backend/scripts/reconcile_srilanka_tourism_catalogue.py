"""Run Gate 5C read-only catalogue-to-KB reconciliation."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
from app.time_context.governance.catalogue_reconciliation import load_existing_attractions, reconcile_registry, validate_catalogue_registry, write_reconciliation_reports


async def run(args) -> dict:
    registry_path = Path(args.registry)
    if not registry_path.is_file():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_validation = validate_catalogue_registry(registry)
    existing = await load_existing_attractions()
    results = reconcile_registry(registry=registry, existing=existing)
    reports = write_reconciliation_reports(results=results, registry_path=registry_path, reports_dir=Path(args.reports_dir), batch_id=args.batch_id, existing_count=len(existing), registry_validation=registry_validation)
    return {"mode": "read_only_reconciliation", "network_requests": 0, "reports": {key: str(value) for key, value in reports.items()},
            "existing_kb_active_attractions": len(existing), "discovered_records": len(results), "postgresql_writes": False, "qdrant_writes": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="data/reports/stage_10_1_3e_gate5b2_catalogue_all_batches_v2_attraction_registry.json")
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--batch-id", default="all_batches_v2")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
