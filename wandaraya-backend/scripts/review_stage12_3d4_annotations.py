"""Display a blinded Stage 12.3D.4 reviewer batch without hidden scores."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    # Windows cmd commonly uses cp1252; preserve the review flow even when an
    # attraction name contains Sinhala/Tamil characters unsupported by it.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Read-only helper for independent annotation.")
    parser.add_argument("--template", default="data/reports/stage12_3d4_r1_blind_template.csv")
    parser.add_argument("--query-id", help="Show one query only; omit to list query IDs.")
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.template).open(encoding="utf-8", newline="")))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["query_id"]].append(row)
    if not args.query_id:
        for query_id, items in sorted(grouped.items()):
            sample = items[0]
            print(f"{query_id}: date={sample['travel_date']} interests={sample['interests']} candidates={len(items)}")
        return
    items = grouped.get(args.query_id)
    if not items:
        raise SystemExit(f"Unknown query ID: {args.query_id}")
    first = items[0]
    print(f"Query: {first['query_id']}\nDate: {first['travel_date']}\nInterests: {first['interests']}\n")
    for number, row in enumerate(items, start=1):
        print(f"{number}. [{row['attraction_id']}] {row['attraction_name']}")
        print(f"   District: {row['district_id'] or 'unknown'} | Categories: {row['categories'] or 'unknown'} | Activities: {row['activities'] or 'unknown'}")
        print(f"   Existing label: {row['relevance_0_to_3'] or 'blank'} | Cannot judge: {row['cannot_judge'] or 'blank'}")


if __name__ == "__main__":
    main()
