"""Build the offline Gate 5B.2 catalogue seed manifest."""
from __future__ import annotations
import json
from pathlib import Path
from app.time_context.governance.catalogue_discovery import build_catalogue_seed_manifest


def main() -> None:
    path = Path("data/reports/stage_10_1_3e_gate5b2_catalogue_seed_manifest.json")
    path.write_text(json.dumps(build_catalogue_seed_manifest(), indent=2), encoding="utf-8")
    print(json.dumps({"mode": "offline_review_only", "network_requests": 0, "manifest": str(path)}, indent=2))


if __name__ == "__main__":
    main()
