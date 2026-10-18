"""Prepare a bounded, review-only Google Places district-resolution queue.

No network, PostgreSQL, or Qdrant access occurs here.  It turns C.2
quarantined records into the exact schema consumed by the existing Gate 5D
runner, while deliberately excluding locality-only candidates from a false
identity claim.
"""
from __future__ import annotations

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_remaining_quarantined_actions.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def build_queue(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in records:
        source_id = str(item.get("source_attraction_id") or "")
        conflicts = set(item.get("conflicts") or [])
        if not source_id or source_id in seen or "missing_verified_district" not in conflicts:
            continue
        name, url = item.get("official_name"), item.get("official_source_url")
        if not name or not url:
            continue
        seen.add(source_id)
        result.append({
            "external_source_id": source_id,
            "attraction_name": name,
            "source_url": url,
            "reason": "gate5e2c2_missing_verified_district",
            "district": None,
            "city": None,
            "existing_google_place_id": item.get("google_place_id"),
            "previous_identity_assessment": item.get("identity_assessment"),
            "requires_physical_attraction_candidate": True,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default="data/reports/stage_10_1_3e_gate5e2c2_district_lookup_queue.json")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    queue = build_queue(payload.get("records", []))
    output = Path(args.output)
    result = {"records": queue, "mode": "prepared_offline", "network_requests": 0, "postgresql_writes": False, "qdrant_writes": False}
    write_json(output, result)
    print(json.dumps({"mode": "prepared_offline", "records": len(queue), "queue_sha256": sha256(output.read_bytes()).hexdigest(), "output": str(output), "network_requests": 0, "postgresql_writes": False, "qdrant_writes": False}, indent=2))


if __name__ == "__main__":
    main()
